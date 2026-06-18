Sensor processing modules

This package contains the core data-processing logic for MagPlotter. It is intentionally self-contained so other front-ends (CLI, web UI) can reuse it.

Contents:

- `clean.py` — robust CSV parsing and cleaning. Produces a `pandas.DataFrame` with columns `time, mx, my, mz`.
- `analysis.py` — physics-based metrics (axis statistics, |B| metrics, heading/circular stats, noise metric).
- `viz.py` — plotting helpers that save PNG files for magnitude, axes, and heading.
- `processor.py` — orchestration: calls the other modules to parse, analyze, plot, and save outputs.
- `watcher.py` — a simple watchdog-based file watcher (alternate watcher implementation used by CLI).

Public API:

Import `sensor_lab.processor.process_file(path, base_dir=...)` to process a single CSV and produce an output folder with `summary.json`, plots, and `report.txt`.
