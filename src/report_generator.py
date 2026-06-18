"""Report generation helpers for MagPlotter.

Creates a human-readable `report.txt` inside a run folder summarizing
key metrics, notes, and provenance.

Primary function:
    generate_report(summary: Dict[str, Any], run_out_dir: Path) -> Path|None

Security note: this module writes to local output directories. Avoid
writing reports into locations controlled by untrusted users.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _fmt(value: Any, decimals: int = 3) -> str:
    """Format a numeric value or return 'N/A'."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def _write_field_map_section(fh, fm: Dict[str, Any]) -> None:
    """Append the FIELD MAP SUMMARY block to an open report file."""
    fh.write("\n\nFIELD MAP SUMMARY\n")
    fh.write("-" * 40 + "\n")

    schema = fm.get("schema", {})
    fh.write(f"Spatial columns : X={schema.get('x_col')}, Y={schema.get('y_col')}")
    if schema.get("z_col"):
        fh.write(f", Z={schema.get('z_col')}")
    fh.write(f"  (3D={schema.get('is_3d')}, vector={schema.get('has_vector')})\n")

    interp = fm.get("interpolation_method", "N/A")
    grid_shape = fm.get("grid_shape", [0, 0])
    fh.write(f"Interpolation   : {interp}  grid {grid_shape[0]}×{grid_shape[1]}\n\n")

    m = fm.get("metrics", {})
    if not m:
        fh.write("  (metrics not available)\n")
        return

    fh.write(f"Peak Field      : {_fmt(m.get('peak_field_strength'))} µT\n")
    fh.write(f"Average Field   : {_fmt(m.get('average_field_strength'))} µT\n")
    fh.write(f"Minimum Field   : {_fmt(m.get('minimum_field_strength'))} µT\n")
    fh.write(f"Std Deviation   : {_fmt(m.get('field_std'))} µT\n")
    fh.write(f"Uniformity      : {_fmt(m.get('field_uniformity_pct'), 1)} %\n")

    hot = m.get("hot_spot") or {}
    fh.write(
        f"Hot Spot        : ({_fmt(hot.get('x'))}, {_fmt(hot.get('y'))})  "
        f"B={_fmt(hot.get('B'))} µT\n"
    )

    mc = m.get("magnetic_center") or {}
    fh.write(f"Magnetic Center : ({_fmt(mc.get('x'))}, {_fmt(mc.get('y'))})\n")

    gs = m.get("gradient_stats") or {}
    fh.write(f"Max Gradient    : {_fmt(gs.get('max_gradient'))} µT/mm\n")
    fh.write(f"Mean Gradient   : {_fmt(gs.get('mean_gradient'))} µT/mm\n")
    fh.write(f"Coverage Area   : {_fmt(m.get('coverage_area'))} mm²\n")
    fh.write(f"Coverage        : {_fmt(m.get('coverage_fraction', 0) * 100, 1)} %\n")

    sym = m.get("symmetry_score")
    fh.write(f"Symmetry Score  : {_fmt(sym)}\n")

    files = fm.get("generated_files", [])
    if files:
        fh.write(f"\nGenerated files ({len(files)}):\n")
        for f in files:
            fh.write(f"  {f}\n")


def generate_report(summary: Dict[str, Any], run_out_dir: Path):
    """Write `report.txt` describing the run, time-series metrics, and field map summary."""
    run_out_dir = Path(run_out_dir)
    report_path = run_out_dir / "report.txt"
    run_name = summary.get("run_name", "unknown")
    logger.info("writing report for run: %s -> %s", run_name, report_path)
    try:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write("MagPlotter Run Report\n")
            fh.write("====================\n\n")
            fh.write(f"Run: {run_name}\n")
            fh.write(f"Source path: {summary.get('path')}\n\n")
            fh.write("Time-Series Metrics:\n")
            metrics = summary.get("metrics", {})
            if isinstance(metrics, dict):
                try:
                    fh.write(json.dumps(metrics, indent=2, ensure_ascii=False))
                except Exception:
                    for k, v in metrics.items():
                        fh.write(f"- {k}: {v}\n")
            else:
                fh.write(str(metrics) + "\n")

            # Field mapping section (present only when spatial data was detected)
            fm = summary.get("field_mapping")
            if fm:
                _write_field_map_section(fh, fm)

            fh.write("\n\nNotes:\n")
            notes = summary.get("notes_from_file") or "(none)"
            if isinstance(notes, list):
                fh.write("\n".join(notes))
            else:
                fh.write(str(notes))
            fh.write("\n")
        logger.debug("report written: %s", report_path)
    except Exception:
        logger.exception("failed to write report for run: %s", run_name)
        return None
    return report_path
