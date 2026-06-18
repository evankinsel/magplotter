# MagPlotter

MagPlotter is a magnetometer data processing and spatial field characterization platform. It converts raw CSV sensor logs into structured engineering analysis, visualizations, field maps, and per-run reports.

Designed for experimental and research workflows where raw magnetic field measurements must be cleaned, analyzed, mapped, and summarized in a reproducible format.

---

## Core Capabilities

**Time-Series Analysis**
- Cleans and validates raw magnetometer CSV logs
- Computes field magnitude |B| and per-axis statistics
- Calculates heading using circular statistics
- Generates mean, variance, drift, and noise metrics
- Produces standardized engineering plots

**Spatial Field Mapping** *(automatic when X/Y coordinate columns are detected)*
- Detects spatial coordinate columns automatically (flexible naming)
- Interpolates scattered measurements onto a uniform grid (scipy)
- Generates 2D heatmap, contour map, vector field, and 3D surface plots
- Computes 21 engineering metrics: peak field, uniformity, gradient, magnetic center, symmetry, radial falloff, and more
- Exports interactive HTML maps (Plotly) for zoom/pan/hover inspection

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/evankinsel/magplotter
cd magplotter
pip install -r requirements.txt
```

### 2. Drop CSV files into `incoming/`

```bash
cp your_data.csv incoming/
```

### 3. Run

```bash
# Process all CSVs in incoming/ once
python main.py

# Watch incoming/ and auto-process new files as they arrive
python main.py --watch

# Process a specific project folder
python main.py /path/to/project
```

### 4. Inspect results

```
output/
└── your_data/
    ├── field_strength_plot.png
    ├── heading_plot.png
    ├── axes_plot.png
    ├── field_heatmap.png          # spatial runs only
    ├── field_contours.png         # spatial runs only
    ├── vector_field.png           # spatial runs with Bx/By
    ├── field_surface.png          # spatial runs only
    ├── interactive_heatmap.html   # spatial runs only (requires plotly)
    ├── interactive_surface.html   # spatial runs only (requires plotly)
    ├── field_metrics.json         # spatial runs only
    ├── cleaned_data.csv
    ├── summary.json
    └── report.txt
```

---

## Supported CSV Formats

### Time-Series (sensor log)

```csv
time,mx,my,mz
0.00,12.24,28.08,8.30
0.05,12.16,28.14,8.42
```

Column aliases accepted: `t`, `timestamp`, `x`/`bx`/`mag_x` for mx, etc.

### 2D Field Map

```csv
X,Y,B
0,0,100.2
10,0,95.8
20,0,89.3
```

```csv
X_mm,Y_mm,Bx,By,Bz
0,0,10.1,5.2,2.3
10,0,9.6,4.9,2.1
```

### 3D Field Map

```csv
X,Y,Z,Bmag
0,0,0,100.2
10,0,0,95.8
```

**Spatial column aliases** (case-insensitive):

| Axis | Recognized names |
|------|-----------------|
| X | `x`, `X`, `pos_x`, `position_x`, `x_mm`, `x_cm`, `x_m`, `col_x`, `x_pos`, `posx` |
| Y | `y`, `Y`, `pos_y`, `position_y`, `y_mm`, `y_cm`, `y_m`, `col_y`, `y_pos`, `posy` |
| Z | `z`, `Z`, `pos_z`, `position_z`, `z_mm`, `z_cm`, `z_m`, `col_z`, `z_pos`, `posz` |

**Field column aliases:**

| Type | Recognized names |
|------|-----------------|
| Magnitude | `B`, `Bmag`, `b_mag`, `magnitude`, `field`, `field_strength`, `b_total`, `\|B\|` |
| Components | `Bx`/`By`/`Bz`, `b_x`/`b_y`/`b_z`, `field_x`/`field_y`/`field_z` |

When only vector components are present, magnitude is computed as √(Bx² + By² + Bz²).

MagPlotter also handles comment lines (`#`, `//`), extra columns, and malformed rows gracefully.

---

## Field Mapping

Field mapping runs **automatically** whenever X and Y coordinate columns are detected. No configuration required.

### What gets generated

| File | Contents |
|------|----------|
| `field_heatmap.png` | 2D magnitude heatmap (viridis, measurement points overlaid) |
| `field_contours.png` | Filled contours with labels, peak (+) and minimum (×) marked |
| `vector_field.png` | Quiver arrows over magnitude background (when Bx/By available) |
| `field_surface.png` | 3D surface — height encodes \|B\| |
| `interactive_heatmap.html` | Plotly heatmap with zoom/pan/hover |
| `interactive_surface.html` | Plotly 3D surface with rotation |
| `field_metrics.json` | Full characterization metrics (see below) |

### Field metrics (`field_metrics.json`)

| Metric | Description |
|--------|-------------|
| `peak_field_strength` | Maximum \|B\| on the grid (µT) |
| `average_field_strength` | Mean \|B\| across valid grid cells |
| `minimum_field_strength` | Minimum \|B\| on the grid |
| `field_std` / `field_variance` | Statistical spread of field values |
| `field_uniformity_pct` | (1 − std/mean) × 100 — 100% = perfectly uniform |
| `hot_spot` | Location and value of peak field |
| `cold_spot` | Location and value of minimum field |
| `magnetic_center` | \|B\|-weighted centroid of the field distribution |
| `gradient_stats` | Max/mean gradient magnitude and peak gradient location |
| `uniform_region_fraction` | Fraction of scan area where B ≥ mean − std |
| `coverage_area` / `coverage_fraction` | Area and fraction of scan with valid data |
| `field_distribution_histogram` | 20-bin histogram of field values |
| `radial_falloff_profile` | Mean B vs distance from magnetic center |
| `symmetry_score` | 0–1 field symmetry estimate (1 = perfectly symmetric) |

### Example report section

```
FIELD MAP SUMMARY
----------------------------------------
Spatial columns : X=X_mm, Y=Y_mm  (3D=False, vector=True)
Interpolation   : linear  grid 100×100

Peak Field      : 100.200 µT
Average Field   : 92.829 µT
Minimum Field   : 82.100 µT
Std Deviation   : 3.433 µT
Uniformity      : 96.3 %
Hot Spot        : (0.000, 0.000)  B=100.200 µT
Magnetic Center : (9.820, 9.894)
Max Gradient    : 1.405 µT/mm
Mean Gradient   : 0.681 µT/mm
Coverage Area   : 408.122 mm²
Symmetry Score  : 0.942
```

### Configuration (`config/config.yaml`)

```yaml
field_mapping:
  enabled: true

  interpolation:
    method: linear          # nearest | linear | cubic
    grid_resolution: 100    # grid points per axis [10–1000]

  heatmap:
    enabled: true
    colormap: viridis

  contour:
    enabled: true
    levels: 15

  vector_field:
    enabled: true
    density: 20             # quiver arrows per axis
    normalize: false        # true = direction only, false = length encodes strength

  surface:
    enabled: true

  interactive:
    enabled: true           # requires: pip install plotly
```

If the file is absent, all features default to enabled with sensible values.

---

## Project Structure

```
magplotter/
├── main.py                        # CLI entrypoint (batch or --watch)
├── config/
│   ├── settings.json              # Basic directory config
│   └── config.yaml                # Field mapping config
├── src/
│   ├── file_manager.py            # File discovery and folder management
│   ├── report_generator.py        # report.txt generation
│   └── field_mapping/             # Spatial field mapping subsystem
│       ├── __init__.py            # Orchestrator: run_field_mapping()
│       ├── detector.py            # Coordinate/field column detection
│       ├── interpolator.py        # scipy griddata → uniform grid
│       ├── heatmap.py             # 2D magnitude heatmap
│       ├── contour.py             # Filled contour map
│       ├── vectorfield.py         # Quiver vector field
│       ├── surface.py             # 3D surface plot
│       ├── metrics.py             # Engineering characterization metrics
│       └── export.py              # Plotly interactive HTML
├── sensor_lab/
│   ├── clean.py                   # CSV parsing and cleaning
│   ├── analysis.py                # Physics metrics and circular statistics
│   ├── viz.py                     # Time-series plot generation
│   ├── processor.py               # Pipeline orchestrator
│   └── watcher.py                 # File system watching
├── tests/
│   ├── test_detector.py
│   ├── test_interpolator.py
│   ├── test_heatmap.py
│   └── test_metrics.py
├── incoming/                      # Drop CSV files here
├── processed/                     # Archive of processed CSVs
├── output/                        # Per-run output folders
└── requirements.txt
```

### Pipeline

```
CSV
 └─ Validation & Cleaning     (sensor_lab/clean.py)
     └─ Time-Series Analysis  (sensor_lab/analysis.py)
         └─ TS Plots          (sensor_lab/viz.py)
             └─ Field Mapping (src/field_mapping/)  ← skipped if no X/Y columns
                 └─ Report    (src/report_generator.py)
                     └─ Archive to processed/
```

---

## Understanding the Metrics

### Time-Series Metrics

**Field Magnitude** — `|B| = √(mx² + my² + mz²)`

- `B_mean` — average field strength
- `B_std` — variation (noise floor indicator)
- `B_drift` — change from first to last sample (±0 = stable)

**Heading** — `θ = arctan2(my, mx)` using circular statistics

- `heading_mean_deg` — dominant compass direction (0–360°)
- `heading_std_deg` — angular stability (smaller = steadier)

**Noise Metric** — mean standard deviation across all three axes; smaller = quieter sensor.

### Spatial Field Metrics

**Uniformity** — `(1 − σ/μ) × 100%`. 100% means a perfectly flat field; lower values indicate a non-uniform distribution.

**Magnetic Center** — the |B|-weighted centroid. Differs from geometric center when the field is asymmetric — useful for locating the effective source position.

**Gradient** — computed via numpy on the interpolated grid. High gradient regions have rapidly changing field strength; important for applications sensitive to field uniformity.

**Symmetry Score** — compares each grid cell against its 180°-rotated counterpart through the magnetic center. Score of 1.0 = perfectly symmetric.

**Radial Falloff** — mean |B| in radial bands from the magnetic center. Reveals whether the field follows a dipole-like 1/r³ decay or a more complex profile.

---

## Examples

### Process a time-series run

```bash
cp lab_run_20240618.csv incoming/
python main.py
cat output/lab_run_20240618/report.txt
```

### Process a spatial field map

```bash
cp magnet_scan.csv incoming/   # columns: X_mm, Y_mm, Bmag
python main.py
open output/magnet_scan/field_heatmap.png
open output/magnet_scan/interactive_heatmap.html
cat output/magnet_scan/field_metrics.json
```

### Continuous monitoring

```bash
python main.py --watch
# In another terminal:
cp new_scan.csv incoming/
# Watcher detects and processes automatically
```

### Batch process multiple experiments

```bash
cp ~/experiments/*.csv incoming/
python main.py
# Each produces its own output/ subfolder
```

---

## Troubleshooting

**"Found 0 CSV files"** — ensure files are in `incoming/` with a `.csv` extension.

**Field mapping not running** — check that your CSV has X and Y columns (any of the supported aliases). Run `python main.py` and look for the `detector:` log line.

**Plots don't generate on a headless server:**
```bash
export MPLBACKEND=Agg
python main.py
```

**Interactive HTML not generated** — install Plotly:
```bash
pip install plotly
```

**Sparse data warning / high NaN fraction** — fewer than ~10 measurement points spread across the scan area will produce a poor interpolation. Switch to `method: nearest` in `config/config.yaml` for sparse datasets.

**CSV parsing errors** — MagPlotter skips malformed rows automatically. If all rows are skipped, check that at least 3–4 numeric columns are present.

---

## Testing

```bash
python -m pytest tests/ -v
# 60 tests: detector, interpolator, heatmap/contour/surface/vectorfield, metrics
```

---

## Architecture Notes

- **Independent field mapping reader** — `src/field_mapping` reads the raw CSV directly (bypassing `sensor_lab/clean.py`'s column aliasing) to preserve all spatial columns.
- **Non-destructive integration** — field mapping is a try/except block in `processor.py`; any failure skips mapping and continues the rest of the pipeline.
- **Extensible schema** — `FieldSchema` captures all detected column names; adding new column aliases only requires updating the pattern lists in `detector.py`.
- **Designed for future expansion** — the architecture is ready for 3D volumetric reconstruction, live sensor streaming, Hall sensor characterization, motor/Halbach array mapping, and AS5600/BNO055 integration.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `numpy`, `pandas` | Data handling |
| `matplotlib` | All static plots |
| `scipy` | Spatial interpolation (field mapping) |
| `plotly` | Interactive HTML exports (optional) |
| `watchdog` | File system watching (`--watch` mode) |
| `pyarrow` | Parquet output |
| `pyyaml` | `config/config.yaml` parsing |
| `pytest` | Test suite |

---

## License

See `LICENSE`.
