# Garmin data and private backups

The local Tracking dashboard reads SQLite. **Sync Garmin** downloads new activity summaries, sleep, HRV, resting HR, Body Battery and available original files into that store. The default sync revisits at least the last seven days for late changes (28 days on a fresh account). Up to 12 original files per pass are decoded. Importing a FIT manually and then syncing its matching Garmin summary counts one session. Multi-sport files preserve separate legs. Recorded data depends on your device; a missing field remains unknown.

For FIT parsing, use Python 3.10+ with Garmin’s official `garmin-fit-sdk==21.222.0`. It can be installed in the Python environment running the plugin, or in the private data directory:

```sh
python3 -m pip install --target "$HOME/Library/Application Support/Forge226Work/dependencies" garmin-fit-sdk==21.222.0
```

Run commands from the installed plugin folder. Replace ATHLETE with the local ID from Forge226's athlete list. The optional global `--data-dir DIRECTORY` selects a different private store and must precede the subcommand.

| Command | Result |
|---|---|
| `python3 server/tracker_import.py sync ATHLETE` | Incremental sync. Each dataset reports a receipt or a failure; recent successful evidence stays available. |
| `python3 server/tracker_import.py sync ATHLETE --days 90 --files 60` | Explicit backfill. Repeat to continue filling files in that window. Activity windows support 1–730 days; wellness supports the most recent 90. |
| `python3 server/tracker_import.py fit ATHLETE activity.fit` | Import one activity FIT, or a ZIP containing one FIT. One file can have multiple sport sessions. |
| `python3 server/tracker_import.py export-json ATHLETE` | Portable JSON for one athlete, including normalized readings, versions, thresholds, check-ins, laps, streams, source receipts and tracking notes. `--originals` also embeds original FIT bytes in base64 and source payloads. |
| `python3 server/tracker_import.py backup` | Consistent SQLite snapshot of all athletes, plan versions, notes, readings and archived original files. |
| `python3 server/tracker_import.py restore BACKUP.sqlite3 NEW_DIRECTORY` | Check snapshot integrity and restore to a new directory. Select this directory when launching the plugin. Existing stores are preserved. |

Exports and backups contain private training and wellness records. Credentials are separate; a restored installation needs its own source connection. Keep backup copies in a private location. JSON is a portable data export; use the SQLite snapshot to restore a working installation.

## Optional daily sync on macOS

The dashboard can run offline, and the manual sync is always available. To prepare a daily sync **at a time you choose**, run:

```sh
python3 server/tracker_import.py schedule-template ATHLETE --at HH:MM
```

This writes a launchd property-list file into the private store's schedules folder. Place the plugin at a stable path before generating the template. When you want to enable it, copy the generated plist to `~/Library/LaunchAgents/`, then run `launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/LABEL.plist"` using the actual generated filename. To disable it, run `launchctl bootout "gui/$(id -u)/LABEL"` and remove that plist from LaunchAgents. The schedule runs under the signed-in macOS user. The Mac must be available and online to retrieve data.

Scheduled and interactive tracker syncs share one per-athlete lock. On a Garmin rate limit, the tracker records the next eligible attempt, using Garmin's Retry-After header where supplied. The next successful sync fills missing files; it never replaces missing evidence with zero. A request for an unavailable original is recorded privately and checked again after seven days. Garmin credentials and tokens are never included in launchd configuration.
