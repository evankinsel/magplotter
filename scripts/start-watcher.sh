#!/bin/bash
# Start the MagPlotter watcher service
# This script keeps the watcher running and auto-restarts it if it crashes.
#
# Usage:
#   bash scripts/start-watcher.sh
#
# Security note: this script runs the Python watcher in a loop. Do not
# run it as root on multi-user systems; prefer a dedicated service user.
# Log rotation for watcher.log is handled by Python's RotatingFileHandler
# (5 MB per file, 3 backups) — no external logrotate config needed.

MAGPLOTTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${MAGPLOTTER_DIR}/logs/watcher.log"
mkdir -p "${MAGPLOTTER_DIR}/logs"

# Emit a structured log line matching Python's log format:
#   YYYY-MM-DD HH:MM:SS,mmm | LEVEL    | shell.watcher | message
_log() {
    local level="$1"
    local msg="$2"
    printf '%s | %-8s | shell.watcher | %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S,%3N')" "${level}" "${msg}" \
        >> "${LOG_FILE}"
}

_log INFO "watcher service starting — host: $(hostname), dir: ${MAGPLOTTER_DIR}"

cd "${MAGPLOTTER_DIR}"

attempt=0
while true; do
    attempt=$((attempt + 1))
    _log INFO "launching python watcher (attempt ${attempt})"
    python3 main.py --watch >> "${LOG_FILE}" 2>&1
    exit_code=$?
    _log WARNING "watcher process exited (code=${exit_code}) — restarting in 5 s"
    sleep 5
done
