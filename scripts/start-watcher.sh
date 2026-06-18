#!/bin/bash
# Start the MagPlotter watcher service
# This script keeps the watcher running and auto-restarts it if it crashes

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
    python main.py --watch >> "${LOG_FILE}" 2>&1
    echo "[$(date)] Watcher stopped, restarting in 5 seconds..." >> "${LOG_FILE}"
    sleep 5
done
