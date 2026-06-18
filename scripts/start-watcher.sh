#!/bin/bash
# Start the MagPlotter watcher service
# This script keeps the watcher running and auto-restarts it if it crashes

# Usage:
#   bash scripts/start-watcher.sh
#
# Security note: this script runs the Python watcher in a loop. Do not
# run it as root on multi-user systems; prefer a dedicated service user
# and rotate logs to avoid unbounded growth.

MAGPLOTTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${MAGPLOTTER_DIR}/logs/watcher.log"
mkdir -p "${MAGPLOTTER_DIR}/logs"

echo "Starting MagPlotter Watcher..."
echo "Logging to: ${LOG_FILE}"
echo "Container: $(hostname)"
echo "Time: $(date)" >> "${LOG_FILE}"

cd "${MAGPLOTTER_DIR}"

# Run watcher with auto-restart on crash
while true; do
    python3 main.py --watch >> "${LOG_FILE}" 2>&1
    echo "[$(date)] Watcher stopped, restarting in 5 seconds..." >> "${LOG_FILE}"
    sleep 5
done
