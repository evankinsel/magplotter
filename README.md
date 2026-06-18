MagPlotter is a magnetometer data processing pipeline that converts raw CSV sensor logs into structured engineering analysis, visualizations, and per-experiment reports.

It is designed for magnetometer characterization workflows in experimental and research environments, where raw magnetic field data must be cleaned, analyzed, and summarized efficiently.

MagPlotter supports:

-Noise filtering and spike removal from raw sensor readings
-Cleaning and validation of magnetometer CSV logs
-Magnetic field vector analysis (Bx, By, Bz, magnitude)
-Heading computation using circular statistics from XY field components
-Statistical characterization (mean, variance, drift, noise metrics)
-Automated generation of engineering-grade plots and summaries
-Organized per-run output directories for reproducible analysis

Each CSV file is processed into a self-contained output package containing plots, statistical summaries, and structured reports.

## Quick Start

### 1. Install

```bash
# Clone or navigate to the magplotter directory
cd /path/to/magplotter

# Create and activate virtual environment (optional but recommended)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Prepare Your Data

Export magnetometer readings as a CSV with columns:
```
time,mx,my,mz
```

Example:
```csv
time,mx,my,mz
0.0,10.5,20.3,5.2
0.1,10.6,20.2,5.3
0.2,10.4,20.4,5.1
...
```

**Units:** Any consistent units (µT, Gauss, arbitrary counts). MagPlotter doesn't enforce units—just be consistent.

### 3. Process Your Data

**Option A: One-time processing (process all incoming CSVs)**
```bash
python main.py
```

**Option B: Continuous watching (auto-process as files arrive)**
```bash
python main.py --watch
```

**Option C: Process a specific folder**
```bash
python main.py /path/to/project
python main.py /path/to/project --watch
```

### 4. Find Your Results

For each input CSV, a dedicated output folder is created:

```
output/
└── run_name/
    ├── raw_data.csv              # Original input (copy)
    ├── cleaned_data.csv          # Processed data (cleaned)
    ├── cleaned_data.parquet      # Same as above, binary format (fast I/O)
    ├── field_strength_plot.png   # |B| magnitude vs time
    ├── heading_plot.png          # Heading angle vs time
    ├── axes_plot.png             # Individual axes (mx, my, mz) vs time
    ├── summary.json              # Metrics and statistics
    ├── report.txt                # Human-readable report
    └── processing_log.txt        # Processing metadata
```

Your original CSV is archived to `processed/` for bookkeeping.

---

## Project Structure

```
magplotter/
├── main.py                      # CLI entrypoint
├── config/
│   └── settings.json            # Configuration file
├── src/
│   ├── __init__.py
│   ├── file_manager.py          # File discovery and folder management
│   └── report_generator.py      # Human-readable report generation
├── sensor_lab/
│   ├── __init__.py
│   ├── clean.py                 # CSV parsing and cleaning
│   ├── analysis.py              # Physics calculations and metrics
│   ├── viz.py                   # Plot generation
│   ├── processor.py             # Orchestration: ties everything together
│   └── watcher.py               # File system watching (legacy)
├── incoming/                    # Drop CSV files here
├── processed/                   # Archive of processed CSVs
├── output/                      # Per-run output folders
├── requirements.txt             # Python dependencies
└── README.md
```

---

## Data Format

### Minimal CSV Format (Required)

```csv
time,mx,my,mz
0.0,10.5,20.3,5.2
0.1,10.6,20.2,5.3
```

- **time**: Elapsed time (seconds) or arbitrary sequence number
- **mx, my, mz**: Magnetometer readings (any consistent units)

### Robust Parsing

MagPlotter gracefully handles:
- Comment lines (prefixed with `#` or `//`)
- Log lines mixed with data
- Extra columns (ignored)
- Missing or malformed rows (skipped)

Example with comments:
```csv
# BNO055 Calibration Test
# 2024-06-18 10:00 AM
time,mx,my,mz
# Starting measurement
0.0,10.5,20.3,5.2
0.1,10.6,20.2,5.3
# Drift phase
0.2,10.4,20.4,5.1
```

---

## Generated Reports

### summary.json

Complete metrics in JSON format:

```json
{
  "run_name": "experiment_01.csv",
  "path": "/path/to/incoming/experiment_01.csv",
  "metrics": {
    "axis_stats": {
      "mx": {"mean": 10.5, "std": 0.3, "min": 9.8, "max": 11.2, "drift": 0.4},
      "my": {"mean": 20.3, "std": 0.25, ...},
      "mz": {"mean": 5.1, "std": 0.2, ...}
    },
    "B_mean": 23.42,
    "B_std": 0.015,
    "B_drift": -0.02,
    "heading_mean_deg": 62.48,
    "heading_std_deg": 0.35,
    "noise_metric": 0.25,
    "num_samples": 1000,
    "time_span_s": 99.9
  },
  "notes_from_file": null,
  "header_comments": [...]
}
```

### report.txt

Human-readable summary:

```
MagPlotter Run Report
====================

Run: experiment_01.csv
Source path: /path/to/incoming/experiment_01.csv

Metrics:
{...JSON metrics...}

Notes:
(none)
```

### Plots

- **field_strength_plot.png**: Magnetic field magnitude |B| = √(mx² + my² + mz²) vs time
- **heading_plot.png**: Heading angle (degrees) = arctan2(my, mx) vs time, with circular statistics
- **axes_plot.png**: Individual magnetometer axes (mx, my, mz) vs time

---

## Examples

### Example 1: Process One Experiment

```bash
# Prepare
cp ~/Downloads/test_run_20240618.csv incoming/

# Process
python main.py

# Inspect
cat output/test_run_20240618/summary.json
open output/test_run_20240618/field_strength_plot.png  # on macOS
# or
xdg-open output/test_run_20240618/field_strength_plot.png  # on Linux
```

### Example 2: Batch Process Multiple Experiments

```bash
# Prepare (copy multiple files)
cp ~/experiment_data/*.csv incoming/

# Process all at once
python main.py

# Each gets its own output folder:
# output/experiment_01/
# output/experiment_02/
# output/experiment_03/
# ...
```

### Example 3: Continuous Monitoring

```bash
# Start the watcher
python main.py --watch

# In another terminal, drop new files:
cp new_data.csv incoming/

# Watcher automatically detects and processes them
# [watcher] Processing new file: new_data.csv
# [watcher] ✓ new_data.csv completed
```

### Example 4: Process in a Non-Standard Location

```bash
# Process a specific folder
python main.py /home/user/magnetometer_lab

# Watch that folder
python main.py /home/user/magnetometer_lab --watch
```

---

## Understanding the Metrics

### Field Strength (|B|)

The magnitude of the magnetic field vector:

$$|B| = \sqrt{m_x^2 + m_y^2 + m_z^2}$$

- **B_mean**: Average field strength
- **B_std**: Field strength variation (noise)
- **B_drift**: Change from start to end (±0 is good; large values suggest sensor drift or environment change)

### Heading

The compass direction computed from the XY plane:

$$\theta = \arctan2(m_y, m_x)$$

Returns 0–360°. Uses **circular statistics** (mean and std dev are computed on the unit circle, not linearly).

- **heading_mean_deg**: Most common direction
- **heading_std_deg**: Direction stability (smaller is steadier)

### Noise Metric

Average standard deviation across all three axes:

$$\text{noise} = \frac{1}{3}(\sigma_{mx} + \sigma_{my} + \sigma_{mz})$$

Indicates sensor noise or environmental variation. Smaller is quieter.

### Drift

Per-axis change from first to last sample:

$$\text{drift} = \text{value}_{\text{final}} - \text{value}_{\text{initial}}$$

Reveals long-term sensor drift. Should be ~0 for stable measurements.

---

## Troubleshooting

### "No CSV files found"

**Problem**: `python main.py` reports "Found 0 CSV files."

**Solution**: Ensure your CSV files are in the `incoming/` folder with `.csv` extension:
```bash
ls incoming/
# Should show your .csv files
```

### Plots Don't Generate

**Problem**: PNG files are missing from output folder.

**Likely cause**: Missing matplotlib or graphical backend.

**Solution**:
```bash
pip install matplotlib
```

If using a headless system, ensure matplotlib is configured:
```bash
export MPLBACKEND=Agg
python main.py
```

### Watcher Not Detecting New Files

**Problem**: `--watch` mode runs but doesn't process new files.

**Likely cause**: watchdog not installed.

**Solution**:
```bash
pip install watchdog
```

### CSV Parsing Errors

**Problem**: "Exception processing file..."

**Check**:
1. CSV has at least 4 columns: `time, mx, my, mz`
2. First numeric column is readable as a float
3. File is not being written to (wait before processing)

**If stuck**: Add a `.txt` notes file next to your CSV and try again. Files with notes are logged for debugging.

---

## Architecture & Design

### Module Overview

- **main.py**: CLI entry point. Handles argument parsing and orchestrates one-off or watching modes.
- **sensor_lab/processor.py**: Master orchestrator. Calls clean → analyze → plot → save.
- **sensor_lab/clean.py**: Robust CSV parsing. Strips comments, handles malformed rows.
- **sensor_lab/analysis.py**: Physics computations. Circular statistics, magnitude, heading, noise.
- **sensor_lab/viz.py**: Matplotlib plotting. Three standard visualizations.
- **src/report_generator.py**: Writes human-readable `report.txt`.
- **src/file_manager.py**: Folder discovery and management.
- **config/settings.json**: Configuration (currently minimal; extensible).

### Design Principles

1. **Separation of Concerns**: Each module has a single responsibility.
2. **Reusability**: Core logic in `sensor_lab` is independent of the CLI; future GUIs can reuse it.
3. **Robustness**: Graceful handling of malformed data, comments, and edge cases.
4. **Clarity**: Clear naming, docstrings, and modular structure.
5. **Extensibility**: Easy to add new analyses, output formats, or visualizations.

### Future Phases

**Phase 2 (Current)**: Automatic folder watching with `--watch` flag.

**Phase 3**: Desktop GUI wrapping the processing logic, allowing users to:
- Browse and select input files
- Configure processing options
- View plots inline
- Export reports

The backend is already designed to support this; only the GUI layer needs to be added.

---

## Performance Notes

- **CSV Parsing**: O(n) per file (n = number of rows)
- **Analysis**: O(n) per file
- **Plotting**: ~1–2 seconds per plot (depends on matplotlib and system)
- **Typical 1000-row file**: Processes in <5 seconds end-to-end

For very large files (100K+ rows), consider:
- Downsampling in the CSV before ingestion
- Using the Parquet output for repeat analysis

---

## Contributing & Extending

To add a new analysis metric:

1. Add a function in `sensor_lab/analysis.py`
2. Call it from `compute_all_metrics()`
3. It will automatically appear in `summary.json`

To add a new plot type:

1. Add a function in `sensor_lab/viz.py`
2. Call it from `sensor_lab/processor.py`
3. Configure naming convention and save path

To customize reports:

1. Edit `src/report_generator.py`
2. Modify `generate_report()` to include new fields or formatting

---

## License

See `LICENSE` file.

---

## Support & Questions

For issues, feature requests, or questions, open an issue on GitHub or contact the maintainer.

---

**Last Updated**: June 2024
**Version**: 2.0 (Refactored)
- **"No incoming directory found"**: Make sure you placed your CSV in `incoming/`.
- **"ModuleNotFoundError"**: Run `pip install -r requirements.txt` first.
- **Plots look weird**: Check that your X, Y, Z columns have valid numbers. The pipeline skips rows with missing X or Y.

### Automation: Watch for new files (optional)
To automatically process new CSVs as they arrive:
```bash
python -m sensor_lab.watcher /path/to/magplotter
```
Leave this running. Any CSV you add to `incoming/` will be processed automatically.

GitHub & Version Control
------------------------
**Important: Local changes are NOT automatically pushed to GitHub.**

To save your work:
```bash
cd /path/to/magplotter
git status                  # see what changed
git add -A                  # stage all changes
git commit -m "Updated processor for Parquet + old data mirroring"
git push origin main        # push to GitHub
```

If you made changes on a branch (e.g., `Sensor_lab/clean.py`), push that branch:
```bash
git push origin Sensor_lab/clean.py
```

Notes
-----
- CSVs can include comment lines (start with # or //), logs, or malformed rows — those are ignored.
- Optional notes files: `run_001_notes.txt` or `run_001.txt` (sibling to the CSV) will be attached to the JSON summary.
- Heading uses circular statistics (so wrap-around is handled properly).
- Parquet format is ~2x faster than CSV for large datasets and takes less disk space.
