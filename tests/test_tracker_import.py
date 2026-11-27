"""Data-integrity regressions tested with synthetic records only."""
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"server"))
from store import Store
from tracker_import import activity_detail, archive_summaries, backup, import_fit, restore, sync_daily_health, sync_tracker, _unpack
from garmin import GarminError


class Daily:
    def __init__(self,store):
        self.store=store
    def get(self,aid,path,params):
        return {"data":[{"userProfilePk":123,"calendarDate":params["startDate"],
                         "heartRate":{"restingValue":45},"bodyBattery":{"minValue":8,"maxValue":77,"latestValue":30}}]}
    def check_owner(self,aid,user):
        assert user==123


class TrackerImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/"store")
        self.aid=self.store.create("Example","UTC")["id"]

    def test_daily_dedup_and_backup_restore(self):
        end=date(2025,1,1)
        for i in range(2):
            r=sync_daily_health(Daily(self.store),self.aid,end,end)
            self.assertEqual(r["saved"],1)
        wellness=self.store.wellness(self.aid)
        self.assertEqual(len(wellness),1)
        self.assertEqual(wellness[0]["restingHr"],45)
        self.assertEqual(wellness[0]["bodyBatteryLow"],8)
        self.assertNotIn("bodyBatteryCharged",wellness[0])
        artifact=backup(self.store)
        out=Path(self.tmp.name)/"recovered"
        restore(artifact["path"],out)
        self.assertEqual(Store(out).wellness(self.aid),wellness)
        self.assertEqual((out/"athletes.sqlite3").stat().st_mode&0o777,0o600)
        self.assertFalse((out/"credentials").exists())
        with self.assertRaisesRegex(ValueError,"new restore directory"):
            restore(artifact["path"],out)

    def test_archive_rejects_multi_fit_without_partial_writes(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as z:
            z.writestr("a.fit",b"first")
            z.writestr("b.fit",b"second")
        with self.assertRaisesRegex(ValueError,"one original"):
            _unpack(stream.getvalue())

    def test_synthetic_multisport_fit_survives_repeat_and_later_api_summary(self):
        try:
            from garmin_fit_sdk import Encoder,Profile
        except ImportError:
            self.skipTest("Optional garmin-fit-sdk is required to exercise FIT decoding.")
        start=1100000000
        encoder=Encoder()
        def write(kind,**values):
            encoder.write_mesg({"mesg_num":Profile["mesg_num"][kind],**values})
        write("FILE_ID",type="activity",manufacturer="development",time_created=start)
        for index,discipline in enumerate(["cycling","running"]):
            t=start+300*index
            write("RECORD",timestamp=t,heart_rate=130,power=180)
            write("RECORD",timestamp=t+10,heart_rate=135,power=190)
            write("LAP",message_index=index,start_time=t,timestamp=t+299,total_timer_time=299,total_distance=1000)
            write("SESSION",message_index=index,start_time=t,timestamp=t+299,total_timer_time=299,total_distance=1000,sport=discipline,
                  first_lap_index=index,num_laps=1)
        write("ACTIVITY",timestamp=start+599,num_sessions=2,total_timer_time=598)
        path=Path(self.tmp.name)/"example.fit"
        path.write_bytes(encoder.close())
        for _ in range(2):
            result=import_fit(self.store,self.aid,path)
            self.assertEqual(result["activities"],2)
        rows=self.store.activities(self.aid)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["multisportGroup"],rows[1]["multisportGroup"])
        for row in rows:
            detail=activity_detail(self.store,self.aid,row["id"])
            self.assertEqual([x["power"] for x in detail["samples"]],[180,190])
            self.assertEqual(len(detail["laps"]),1)
        mapped=dict(rows[0],id="garmin:100",sourceId="100",name="API name")
        self.store.ingest(self.aid,"garmin",[mapped],{},"digest")
        archive_summaries(self.store,self.aid,[{"activityId":100}],[mapped])
        self.assertEqual(len(self.store.activities(self.aid)),2)
        self.assertEqual(len(activity_detail(self.store,self.aid,mapped["id"])["laps"]),1)
        import_fit(self.store,self.aid,path)
        self.assertEqual(len(self.store.activities(self.aid)),2)
        copy=restore(backup(self.store)["path"],Path(self.tmp.name)/"fit-restored")
        self.assertEqual(activity_detail(Store(copy["directory"]),self.aid,mapped["id"]),activity_detail(self.store,self.aid,mapped["id"]))

    def test_interrupted_daily_health_preserves_previous_receipt(self):
        start=date(2025,1,1)
        g=Daily(self.store)
        sync_daily_health(g,self.aid,start,start)
        baseline=self.store.provider_sync(self.aid,"garmin-daily")
        get=g.get
        def flaky(aid,path,params):
            if params["startDate"]!=start.isoformat():
                raise GarminError("rate limit",429)
            return get(aid,path,params)
        with patch.object(g,"get",flaky):
            with self.assertRaises(GarminError):
                sync_daily_health(g,self.aid,start,start+timedelta(days=32))
        self.assertEqual(self.store.provider_sync(self.aid,"garmin-daily"),baseline)
        self.assertEqual(len(self.store.wellness(self.aid)),1)


if __name__=="__main__":
    unittest.main()
