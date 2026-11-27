"""Private Garmin source archive, FIT streams, incremental sync and SQLite backups."""
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import fcntl
import plistlib
import sys
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import re
from uuid import uuid4
import zipfile
import zlib
from zoneinfo import ZoneInfo

from imports import sport
from store import encode, now

MAX_FIT_BYTES = 64 * 1024 * 1024
SDK_VERSION = "21.222.0"
SCHEMA = """
CREATE TABLE IF NOT EXISTS tracker_originals(
    athlete TEXT NOT NULL, kind TEXT NOT NULL, source_id TEXT NOT NULL,
    content BLOB NOT NULL, PRIMARY KEY(athlete,kind,source_id));
CREATE TABLE IF NOT EXISTS tracker_fit(
    athlete TEXT NOT NULL, activity_id TEXT NOT NULL, digest TEXT NOT NULL,
    detail BLOB NOT NULL, PRIMARY KEY(athlete,activity_id));
CREATE TABLE IF NOT EXISTS tracker_fit_status(
    athlete TEXT NOT NULL, activity_id TEXT NOT NULL, status TEXT NOT NULL,
    checked_at TEXT NOT NULL, PRIMARY KEY(athlete,activity_id));
"""


def _encoded(value):
    return zlib.compress(encode(value).encode(), 4)


def _schema(store):
    with store.db() as db:
        db.executescript(SCHEMA)


def _instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _matching(row, candidates):
    """Refuse fuzzy joins. Exact start, discipline and close timer time identify a leg."""
    start = _instant(row["startTime"])
    return [a for a in candidates if a["sport"] == row["sport"]
            and abs((_instant(a["startTime"]) - start).total_seconds()) <= 2
            and abs(a["durationSeconds"] - row["durationSeconds"]) <= max(8, .02 * row["durationSeconds"])]


def archive_summaries(store, aid, records, normalized):
    _schema(store)
    with store.db() as db:
        db.executemany("INSERT OR REPLACE INTO tracker_originals VALUES(?,?,?,?)",
                       ((aid, "garmin-summary", str(r["activityId"]), _encoded(r))
                        for r in records if r.get("activityId") is not None))
        provisional = [json.loads(r[0]) for r in db.execute(
            "SELECT payload FROM activities WHERE athlete=? AND source='garmin' AND source_id LIKE 'fit-%'", (aid,))]
        # A manually imported file may have arrived before the API summary.
        for old in provisional:
            matches = _matching(old, normalized)
            if len(matches) == 1:
                target = matches[0]["id"]
                db.execute("INSERT OR IGNORE INTO tracker_fit SELECT athlete,?,digest,detail FROM tracker_fit WHERE athlete=? AND activity_id=?",
                           (target, aid, old["id"]))
                db.execute("DELETE FROM tracker_fit WHERE athlete=? AND activity_id=?", (aid, old["id"]))
                db.execute("DELETE FROM activities WHERE athlete=? AND source='garmin' AND source_id=?", (aid, old["sourceId"]))


def archive_wellness(store, aid, records):
    _schema(store)
    with store.db() as db:
        db.executemany("INSERT OR REPLACE INTO tracker_originals VALUES(?,?,?,?)",
                       ((aid, "garmin-"+kind, raw["calendarDate"], _encoded(raw)) for kind,raw in records))


def sync_daily_health(garmin, aid, first, last):
    """Garmin daily summaries include resting heart rate and Body Battery."""
    store = garmin.store
    _schema(store)
    fields = {"heartRate": {"restingValue": "restingHr"},
              "bodyBattery": {"minValue": "bodyBatteryLow", "maxValue": "bodyBatteryHigh",
                              "latestValue": "bodyBatteryLatest", "chargedValue": "bodyBatteryCharged",
                              "drainedValue": "bodyBatteryDrained"}}
    cursor, rows, originals = first, [], []
    while cursor <= last:
        stop = min(last, cursor + timedelta(days=29))
        reply = garmin.get(aid, "/usersummary-service/v2/dailysummaries",
                           {"startDate": cursor.isoformat(), "endDate": stop.isoformat()})
        if isinstance(reply, dict) and "data" not in reply:
            raise ValueError("Unrecognized Garmin daily-summary response.")
        batch = reply.get("data") if isinstance(reply, dict) else reply
        if batch is not None and not isinstance(batch, list):
            raise ValueError("Unrecognized Garmin daily-summary response.")
        for raw in batch or []:
            day = date.fromisoformat(raw["calendarDate"])
            if not cursor <= day <= stop:
                raise ValueError("Daily summary outside requested window.")
            garmin.check_owner(aid, raw.get("userProfilePk"))
            sid = "daily-summary:" + day.isoformat()
            row = dict(id="garmin:"+sid, sourceId=sid, source="garmin", recordKind="wellness",
                       date=day.isoformat(), method="Garmin daily summary", units={})
            for group, keys in fields.items():
                values = raw.get(group) or {}
                for key, field in keys.items():
                    n = values.get(key)
                    if type(n) not in (int, float) or n < 0:
                        continue
                    if field == "restingHr" and not 0 < n < 300:
                        continue
                    if field in ("bodyBatteryLow", "bodyBatteryHigh", "bodyBatteryLatest") and n > 100:
                        continue
                    row[field] = n
                    row["units"][field] = "bpm" if field == "restingHr" else "points"
            originals.append((aid, "garmin-daily", sid, _encoded(raw)))
            if row["units"]:
                rows.append(row)
        cursor = stop + timedelta(days=1)
    receipt = dict(source="garmin", recordKind="wellness", method="Garmin daily summaries", coverage={"first": first.isoformat(), "last": last.isoformat()},
                   saved=len(rows), complete=True, syncedAt=now())
    if rows:
        receipt = store.ingest(aid, "garmin", rows, receipt, hashlib.sha256(_encoded(rows)).hexdigest(), "wellness")
    with store.db() as db:
        db.executemany("INSERT OR REPLACE INTO tracker_originals VALUES(?,?,?,?)", originals)
    store.set_provider_sync(aid, "garmin-daily", receipt)
    return receipt


def _sdk(store):
    # Optional official SDK stays outside the shareable plugin and athlete backups.
    import sys
    dependency_dir = str(store.root / "dependencies")
    if Path(dependency_dir, "garmin_fit_sdk").is_dir() and dependency_dir not in sys.path:
        sys.path.append(dependency_dir)
    try:
        from garmin_fit_sdk import Decoder, Stream
    except ImportError:
        raise ValueError("FIT decoding requires Garmin's official SDK. Install garmin-fit-sdk==" + SDK_VERSION
                         + " into this Python environment, or into " + dependency_dir + ".") from None
    return Decoder, Stream


def _unpack(blob):
    if not 0 < len(blob) <= MAX_FIT_BYTES:
        raise ValueError("Original file must be between 1 byte and 64 MiB.")
    if blob[8:12] == b".FIT":
        return blob
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        raise ValueError("Original file is not FIT or a Garmin ZIP containing one FIT file.")
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        files = [i for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith(".fit")]
        if len(files) != 1 or files[0].file_size > MAX_FIT_BYTES:
            raise ValueError("Supply one original FIT per import (64 MiB expanded limit).")
        return z.read(files[0])


def _values(raw, fields):
    result = {}
    for target, keys in fields.items():
        for key in keys.split():
            n = raw.get(key)
            if type(n) in (int, float):
                result[target] = n
                break
    return result


SAMPLES = dict(power="power", hr="heart_rate", speed="enhanced_speed speed", distanceMeters="distance",
               altitudeMeters="enhanced_altitude altitude", cadence="cadence", temperatureC="temperature")
INTERVAL = dict(durationSeconds="total_timer_time total_elapsed_time", elapsedSeconds="total_elapsed_time",
                distanceMeters="total_distance", averagePower="avg_power", averageHr="avg_heart_rate",
                averageSpeed="enhanced_avg_speed avg_speed", normalizedPower="normalized_power")


def _fit_legs(store, content, tz):
    Decoder, Stream = _sdk(store)
    decoder = Decoder(Stream.from_byte_array(content))
    messages, errors = decoder.read()
    if errors:
        raise ValueError("FIT decoder rejected this file; the original may be incomplete.")
    sessions = messages.get("session_mesgs") or []
    if not sessions:
        raise ValueError("FIT contains no activity sessions.")
    digest = hashlib.sha256(content).hexdigest()
    legs = []
    for i, ses in enumerate(sessions):
        begin = _instant(ses["start_time"])
        end = _instant(ses["timestamp"])
        sub_sport = str(ses.get("sub_sport", ""))
        kind = sport(sub_sport) if sport(sub_sport) != "Other" else sport(ses.get("sport"))
        values = _values(ses, INTERVAL)
        duration = values.get("durationSeconds")
        if not duration or duration <= 0 or end < begin:
            raise ValueError("FIT session has no usable timer duration or boundaries.")
        sid = f"fit-{digest}-{i}"
        row = dict(id="garmin:"+sid, sourceId=sid, source="garmin", name=str(ses.get("sport","Activity")).replace("_"," ").title(),
                   sport=kind, date=begin.astimezone(ZoneInfo(tz)).date().isoformat(), startTime=begin.isoformat(),
                   sourceFile="Original FIT", normalization="FIT SDK seconds/meters", **values)
        if len(sessions)>1:
            row["multisportGroup"]="fit:"+digest
        detail = dict(rawAvailable=True, source="Original FIT", samples=[], laps=[], lengths=[],
                      poolLengthMeters=ses.get("pool_length"), subSport=sub_sport)
        for raw in messages.get("record_mesgs", []):
            if raw.get("timestamp") is None:
                continue
            t = _instant(raw["timestamp"])
            if begin <= t <= end and (i==len(sessions)-1 or t < _instant(sessions[i+1]["start_time"])):
                detail["samples"].append(dict(timestamp=t.isoformat(), elapsedSeconds=(t-begin).total_seconds(), **_values(raw,SAMPLES)))
        for message, target in [("lap_mesgs","laps"),("length_mesgs","lengths")]:
            for raw in messages.get(message, []):
                if raw.get("start_time") is None or raw.get("timestamp") is None:
                    continue
                start, finish = _instant(raw["start_time"]), _instant(raw["timestamp"])
                if begin <= start <= finish <= end:
                    interval = dict(startTime=start.isoformat(), endTime=finish.isoformat(), startSeconds=(start-begin).total_seconds(), **_values(raw,INTERVAL))
                    if target=="lengths":
                        interval.update(type=raw.get("length_type"),stroke=raw.get("swim_stroke"))
                    detail[target].append(interval)
        detail["samples"].sort(key=lambda r:r["elapsedSeconds"])
        for key in ("laps","lengths"):
            detail[key].sort(key=lambda r:r["startSeconds"])
        moving_lengths=[x for x in detail["lengths"] if x.get("type")=="active" and x.get("durationSeconds")]
        if moving_lengths:
            detail["activeSwimSeconds"]=sum(x["durationSeconds"] for x in moving_lengths)
        legs.append((row,detail))
    return legs


def _import_bytes(store, aid, blob, requested_id=None):
    athlete=store.athlete(aid)
    original=_unpack(blob)
    digest=hashlib.sha256(original).hexdigest()
    _schema(store)
    legs=_fit_legs(store, original, athlete["timezone"])
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        existing=[json.loads(x[0]) for x in db.execute("SELECT payload FROM activities WHERE athlete=? AND source='garmin'",(aid,))]
        target=next((r for r in existing if r["id"]==requested_id), None)
        if requested_id and not target:
            raise ValueError("Download does not correspond to a stored Garmin activity.")
        matched=[]
        for row, detail in legs:
            # Parent files can contain several legs; attach only the requested child.
            if target and len(legs)>1 and not _matching(row,[target]):
                continue
            candidates = [target] if target else _matching(row,existing)
            if len(candidates)>1:
                raise ValueError("Multiple Garmin summaries match this FIT leg. Select the intended activity explicitly.")
            if candidates:
                activity=candidates[0]
            else:
                activity=row
                db.execute("INSERT INTO activities VALUES(?,?,?,?,?)",(aid,"garmin",row["sourceId"],encode(row),digest))
                existing.append(row)
            current=db.execute("SELECT digest FROM tracker_fit WHERE athlete=? AND activity_id=?",(aid, activity["id"])).fetchone()
            if current and current[0]!=digest and not requested_id:
                raise ValueError("A different original is already attached to this activity.")
            db.execute("INSERT OR REPLACE INTO tracker_fit VALUES(?,?,?,?)",(aid,activity["id"],digest,_encoded(detail)))
            db.execute("DELETE FROM tracker_fit_status WHERE athlete=? AND activity_id=?",(aid,activity["id"]))
            matched.append(activity["id"])
        if not matched:
            raise ValueError("Original multisport file could not be associated with this leg.")
        db.execute("INSERT OR IGNORE INTO tracker_originals VALUES(?,?,?,?)",(aid,"fit",digest,original))
    return {"ids":matched,"activities":len(matched),"sha256":digest,"source":"Original FIT"}


def import_fit(store, aid, path, activity_id=None):
    path=Path(path).expanduser()
    if not path.is_file() or path.stat().st_size>MAX_FIT_BYTES:
        raise ValueError("FIT file missing or exceeds 64 MiB.")
    return _import_bytes(store, aid, path.read_bytes(), activity_id)


def activity_details(store, aid, ids=None):
    store.athlete(aid)
    _schema(store)
    with store.db() as db:
        if ids is None:
            rows=db.execute("SELECT activity_id,detail FROM tracker_fit WHERE athlete=?",(aid,))
            return {r[0]:json.loads(zlib.decompress(r[1])) for r in rows}
        result={}
        unique=list(dict.fromkeys(ids))
        for i in range(0,len(unique),400):
            batch=unique[i:i+400]
            marks=",".join("?" for _ in batch)
            rows=db.execute("SELECT activity_id,detail FROM tracker_fit WHERE athlete=? AND activity_id IN ("+marks+")",(aid,*batch))
            result.update((r[0],json.loads(zlib.decompress(r[1]))) for r in rows)
        return result


def activity_detail(store, aid, activity_id):
    return activity_details(store,aid,[activity_id]).get(activity_id,{"rawAvailable":False,"source":"summary only","samples":[],"laps":[],"lengths":[]})


def _detail_backlog(store, aid, first, last):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).isoformat()
    with store.db() as db:
        rows=db.execute("""SELECT a.payload FROM activities a
          LEFT JOIN tracker_fit f ON f.athlete=a.athlete AND f.activity_id='garmin:'||a.source_id
          LEFT JOIN tracker_fit_status s ON s.athlete=a.athlete AND s.activity_id='garmin:'||a.source_id
          WHERE a.athlete=? AND a.source='garmin' AND f.digest IS NULL
            AND (s.status IS NULL OR s.status!='Original unavailable' OR s.checked_at<?)
            AND json_extract(a.payload,'$.date') BETWEEN ? AND ?
          ORDER BY json_extract(a.payload,'$.startTime') DESC""",(aid,cutoff,first.isoformat(),last.isoformat()))
        return [r for x in rows if (r:=json.loads(x[0]))["sourceId"].isdigit()]


def sync_tracker(garmin, aid, days=None, detail_limit=12):
    """Serialize imports from the local dashboard and an optional scheduled worker."""
    store=garmin.store
    store.athlete(aid)
    prefs=store.source_preferences(aid)
    garmin_pref=next((p for p in prefs if p["provider"]=="garmin"),None)
    manual=any(p["provider"]=="manual" and p["enabled"] for p in prefs)
    if (garmin_pref and (not garmin_pref["enabled"] or garmin_pref["mode"]!="native")) or (manual and not garmin_pref):
        raise ValueError("Enable the Garmin connection in source preferences to sync.")
    lockfile=store.root/("tracker-sync-"+hashlib.sha256(aid.encode()).hexdigest()[:24]+".lock")
    with lockfile.open("a") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return {"complete":False,"status":"already syncing","datasets":{}}
        prior=store.provider_sync(aid,"garmin-tracker") or {}
        wait_until=prior.get("retryAfter")
        if wait_until and datetime.fromisoformat(wait_until)>datetime.now(timezone.utc):
            return {"complete":False,"status":"waiting for Garmin rate limit","retryAfter":wait_until,"datasets":{}}
        return _sync_tracker(garmin,aid,days,detail_limit)


def _sync_tracker(garmin, aid, days, detail_limit):
    """Sources checkpoint independently. Repeating an interrupted request fills missing files."""
    from garmin import GarminError
    store=garmin.store
    athlete=store.athlete(aid)
    _schema(store)
    today=datetime.now(ZoneInfo(athlete["timezone"])).date()
    prev=store.provider_sync(aid,"garmin")
    if days is None:
        last=prev.get("coverage",{}).get("last") if prev else None
        days=min(730,max(7,(today-date.fromisoformat(last)).days+3)) if last else 28
    if type(days) is not int or not 1<=days<=730 or type(detail_limit) is not int or not 0<=detail_limit<=100:
        raise ValueError("Choose 1–730 activity days and 0–100 original files per sync.")
    first=today-timedelta(days=days-1)
    if not garmin.status(aid)["connected"]:
        raise ValueError("Connect Garmin first.")
    report={"datasets":{},"startedAt":now(),"complete":True}
    datasets=report["datasets"]
    with garmin.lock:
        wellness_days=min(days,90)
        for name, fetch in (
            ("activities",lambda:garmin.sync(aid,days)),
            ("sleepHrv",lambda:garmin.sync_wellness(aid,wellness_days)),
            ("dailyHealth",lambda:sync_daily_health(garmin,aid,today-timedelta(days=wellness_days-1),today))):
            try:
                datasets[name]={"status":"succeeded","receipt":fetch()}
            except (GarminError,ValueError,KeyError,TypeError) as err:
                datasets[name]={"status":"failed","message":str(err)}
                report["complete"]=False
                if getattr(err,"status",None)==429:
                    report["retryAfter"]=err.retry_after or (datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()
                if getattr(err,"status",None) in (401,403,429):
                    break
        if detail_limit and datasets.get("activities",{}).get("status")=="succeeded" and len(datasets)==3 and "retryAfter" not in report:
            detail={"status":"succeeded","downloaded":0,"unavailable":0,"errors":[]}
            datasets["originalFiles"]=detail
            try:
                _sdk(store)
                backlog=_detail_backlog(store,aid,first,today)
                for r in backlog[:detail_limit]:
                    try:
                        blob=garmin.get(aid,"/download-service/files/activity/"+r["sourceId"],binary=True)
                        if not blob:
                            raise GarminError("Garmin has no original file for this activity.",404)
                        _import_bytes(store,aid,blob,r["id"])
                        detail["downloaded"]+=1
                    except (GarminError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as err:
                        if isinstance(err,GarminError) and err.status != 404:
                            raise
                        with store.db() as db:
                            db.execute("INSERT OR REPLACE INTO tracker_fit_status VALUES(?,?,?,?)",(aid,r["id"],"Original unavailable",now()))
                        detail["unavailable"]+=1
                        detail["errors"].append({"activityId":r["id"],"message":str(err)})
                detail["remainingInWindow"]=len(_detail_backlog(store,aid,first,today))
                if detail["unavailable"] or detail["remainingInWindow"]:
                    detail["status"]="partial"
                    report["complete"]=False
            except (GarminError,ValueError) as err:
                if getattr(err,"status",None)==429:
                    report["retryAfter"]=err.retry_after or (datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()
                detail.update(status="partial",message=str(err))
                report["complete"]=False
        report["finishedAt"]=now()
        store.set_provider_sync(aid,"garmin-tracker",report)
    return report


def backup(store):
    """One consistent, private database snapshot including original files, without credentials."""
    out=store.root/"backups"
    out.mkdir(mode=0o700,exist_ok=True)
    path=out/("tracker-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid4().hex[:8]+".sqlite3")
    descriptor,tmpname=tempfile.mkstemp(dir=out)
    os.close(descriptor)
    tmp=Path(tmpname)
    try:
        with store.db() as source, closing(sqlite3.connect(tmp)) as dest:
            source.backup(dest)
            if dest.execute("PRAGMA quick_check").fetchone()[0]!="ok":
                raise ValueError("Database backup did not pass integrity check.")
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)
    return {"path":str(path),"bytes":path.stat().st_size,"includes":"All athletes and original files in this local database. Credentials excluded."}


def restore(backup_path, destination):
    """Restore into a new directory; never replace a running athlete store."""
    source=Path(backup_path).expanduser().resolve(strict=True)
    dest=Path(destination).expanduser().resolve()
    if dest.exists():
        raise ValueError("Choose a new restore directory; existing data cannot be overwritten.")
    with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("Backup failed its database integrity check.")
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"athletes","plans","activities","wellness","imports"}<=tables:
            raise ValueError("Unsupported athlete database backup.")
        dest.mkdir(mode=0o700)
        path=dest/"athletes.sqlite3"
        try:
            descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            os.close(descriptor)
            with closing(sqlite3.connect(path)) as target:
                db.backup(target)
        except BaseException:
            path.unlink(missing_ok=True)
            dest.rmdir()
            raise
    return {"directory":str(dest),"database":str(path),"restored":True}


def export_json(store, aid, include_originals=False):
    """One athlete's portable snapshot, read consistently and written incrementally."""
    import base64
    store.athlete(aid)
    _schema(store)
    folder=store.root/"exports"/aid
    folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=folder/("tracking-"+uuid4().hex[:12]+".json")
    tables={"athletes":("athlete","id"),"activities":("activities","athlete"),
            "wellness":("wellness","athlete"),"plans":("planVersions","athlete"),
            "active":("activePlan","athlete"),"data_sources":("sourcePreferences","athlete"),
            "provider_sync_status":("sourceReceipts","athlete"),"imports":("imports","athlete"),
            "checkins":("checkins","athlete"),"tracking_notes":("trackingNotes","athlete"),
            "tracker_fit":("originalFileDetails","athlete"),"tracker_fit_status":("fileStatus","athlete")}
    if include_originals:
        tables["tracker_originals"]=("originals","athlete")
    counts={}
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=folder,delete=False) as out:
        tmp=Path(out.name)
    try:
        with tmp.open("w",encoding="utf-8") as out, store.db() as db:
            db.execute("BEGIN")
            out.write('{"schema":"forge226.tracking.v1","exportedAt":'+encode(now())+',"athleteId":'+encode(aid))
            available={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table,(key,owner_column) in tables.items():
                out.write(","+encode(key)+":[")
                count=0
                if table in available:
                    for item in db.execute("SELECT * FROM "+table+" WHERE "+owner_column+"=?",(aid,)):
                        row=dict(item)
                        for k,v in tuple(row.items()):
                            if k in ("profile","payload","receipt","state","validation","value") and isinstance(v,str):
                                row[k]=json.loads(v)
                            elif isinstance(v,bytes):
                                if table=="tracker_originals" and row["kind"]=="fit":
                                    row[k]={"encoding":"base64","bytes":base64.b64encode(v).decode("ascii")}
                                else:
                                    row[k]=json.loads(zlib.decompress(v))
                        if count:
                            out.write(",")
                        out.write(encode(row))
                        count+=1
                counts[key]=count
                out.write("]")
            out.write("}")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)
    return {"path":str(path),"bytes":path.stat().st_size,"includesOriginals":include_originals,"counts":counts}


def schedule_template(store, aid, at, detail_limit=12):
    """Create an opt-in LaunchAgent template without enabling a schedule."""
    store.athlete(aid)
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d",at) or not 0<=detail_limit<=100:
        raise ValueError("Choose a local time HH:MM and 0–100 original files per sync.")
    hour,minute=map(int,at.split(":"))
    label="local.forge226.sync."+hashlib.sha256(aid.encode()).hexdigest()[:16]
    folder=store.root/"schedules"
    folder.mkdir(mode=0o700,exist_ok=True)
    path=folder/(label+".plist")
    spec={"Label":label,
          "ProgramArguments":[sys.executable,str(Path(__file__).resolve()),"--data-dir",str(store.root),
                              "sync",aid,"--files",str(detail_limit)],
          "StartCalendarInterval":{"Hour":hour,"Minute":minute},
          "ProcessType":"Background","ThrottleInterval":900}
    with tempfile.NamedTemporaryFile(dir=folder,delete=False) as out:
        plistlib.dump(spec,out)
        tmp=Path(out.name)
    try:
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)
    return {"path":str(path),"label":label,"configuredTime":at,"installed":False,
            "note":"Template only. Enable deliberately using launchctl after choosing the intended schedule."}


if __name__=="__main__":
    import argparse
    from store import Store
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir",help="Private Forge226 data directory")
    commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("backup")
    j=commands.add_parser("export-json");j.add_argument("athlete");j.add_argument("--originals",action="store_true")
    j=commands.add_parser("schedule-template");j.add_argument("athlete");j.add_argument("--at",required=True);j.add_argument("--files",type=int,default=12)
    r=commands.add_parser("restore");r.add_argument("backup");r.add_argument("destination")
    f=commands.add_parser("fit");f.add_argument("athlete");f.add_argument("path")
    s=commands.add_parser("sync");s.add_argument("athlete");s.add_argument("--days",type=int);s.add_argument("--files",type=int,default=12)
    args=parser.parse_args()
    if args.command=="restore":
        result=restore(args.backup,args.destination)
    else:
        store=Store(args.data_dir)
        if args.command=="backup":
            result=backup(store)
        elif args.command=="export-json":
            result=export_json(store,args.athlete,args.originals)
        elif args.command=="schedule-template":
            result=schedule_template(store,args.athlete,args.at,args.files)
        elif args.command=="fit":
            result=import_fit(store,args.athlete,args.path)
        else:
            from garmin import Garmin
            result=sync_tracker(Garmin(store),args.athlete,args.days,args.files)
    print(json.dumps(result,indent=2))
