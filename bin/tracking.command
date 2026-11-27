#!/bin/sh
set -eu
exec python3 "$(dirname "$0")/../server/tracker_web.py" "$@"
