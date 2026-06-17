# Sensor Lab Pipeline (magnetometer)

Overview
--------
Lightweight pipeline to convert raw magnetometer CSVs into cleaned data, physics metrics (including heading), PNG plots, and per-run JSON summaries. Supports optional notes files and a watchdog file-watcher to automate processing.

Project layout
- incoming/         # drop raw run_NNN.csv here
- processed/        # processed raw CSVs moved here
- output/runs/      # per-run subfolders containing summaries, plots, cleaned CSV

Quick start
-----------
1. Install:
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

2. Run one-off processing (process all CSVs in incoming):
   python run_processor.py /path/to/project_root

3. Run watcher to auto-process new files:
   python -m sensor_lab.watcher /path/to/project_root

Notes
-----
- CSVs can include comment lines (start with # or //), logs, or malformed rows — those are ignored.
- Optional notes files: `run_001_notes.txt` or `run_001.txt` (sibling to the CSV) will be attached to the JSON summary.
- Heading uses circular statistics (so wrap-around is handled properly).
