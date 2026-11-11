# Use Forge226 inside the current desktop chat

Use this only when registered Forge226 tools are absent from the current chat
and the host permits local code execution with a persistent input/output session.
This is a direct client of the SAME bundled engine, not a new chat, secondary
agent or separate database. Normal host execution/network/file permissions and
athlete account consent still apply. Never use it to work around a denied tool,
disabled integration, denied permission or administrator restriction.

## Assistant-operated setup

1. Locate the reviewed package (supplied folder or installed source) and Python
   3.10+. Read its launcher and server before execution if not already reviewed.
   Start `python3 /absolute/path/to/forge226/bin/chat-session.py` with the host's
   persistent interactive execution facility; retain the returned process/session
   ID. In Codex use exec_command with tty=true and a short initial yield. Do not
   tell the athlete to type commands, start another chat or supply a handoff.
2. Send newline-delimited JSON-RPC messages through that session's stdin. First
   initialize, then list tools and call status. Example messages:

   ```json
   {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"forge226-same-chat","version":"1"}}}
   {"jsonrpc":"2.0","id":2,"method":"tools/list"}
   {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"forge226_status","arguments":{}}}
   ```

   In Codex send input with write_stdin using the retained session_id. Parse
   responses by request ID and inspect result.isError before claiming success.
   Use unique IDs for subsequent messages. Read the actual returned tool schemas
   and use tools/call with the same names/arguments described in data-tools.md.
   No credentials are accepted as tool arguments. Do not put secrets into stdin,
   shell commands or chat; private keys/app credentials go into the existing
   loopback setup form only.
3. Call list_athletes, select the intended existing athlete, then get_context and
   get_plan as appropriate. Use the reported storage location; never create a
   second data directory to bypass a lock or fabricate a successful fresh start.
   Continue with the answers already collected in THIS chat. An existing saved
   intake file may be read in place; the athlete need not reattach it.
4. For a chosen connection, call the existing garmin_connect/strava_connect and
   present its private setup URL. Keep this process and its stdin open while the
   athlete completes setup in their browser. Do not close the process after
   printing the URL, run setup as a short-lived one-shot, or wait in a blocking
   loop while the person is entering details. Continue this chat after they
   return; call status and perform the requested initial sync with the same
   process. Never claim live setup success based on a mock test.
5. Use the same process for imports, analysis, drafts, authorized activation and
   dashboard export. All existing checks and version controls apply. The assistant
   handles protocol details and shows ordinary coaching language to the athlete.

## Recovery and limits

If the process has stopped, restart it against the same store, resume the saved
athlete and issue a fresh private setup link if needed. Prior verified account
credentials and athlete state are persisted. Do not restart onboarding.

The engine allows one process per store to protect credentials. If another
connection owns it, report that specific conflict; use an accessible existing
connection or arrange a normal same-chat reconnect/stop of that session with
appropriate authorization. Do not kill unknown processes, silently switch
storage, or bypass locks.

If the host cannot keep a local process alive, or execution is denied, explain
that exact limitation and keep coaching in this chat using manual answers or
supported files. Mark a requested live connection pending. Do not promise local
API access in a hosted/browser-only environment, call absent tools, or tell the
athlete that a new chat is required by this coaching package. Tool availability
is a host capability, not an athlete-intake requirement.


## Large plans and process conflicts
The interactive launcher disables canonical terminal line limits while running and restores terminal settings on exit. This prevents long profile/calendar JSON requests from being silently truncated. Host input-size restrictions still apply. If a request is too large for the host, stop the owned session cleanly and feed a prepared JSON-RPC file through the same engine/store under normal permissions; do not bypass version checks with direct database writes. Never include credentials in such files. Do not stop a setup server while the athlete is completing authorization.

The lock records the owner's PID and start time for diagnosis. This is advisory metadata, not permission to terminate that PID. Re-check the owner before any authorized restart. A stale metadata file does not mean the lock is held; use the actual OS lock result.
