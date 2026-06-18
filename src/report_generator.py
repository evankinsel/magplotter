"""Report generation helpers for MagPlotter.

Creates a human-readable `report.txt` inside a run folder summarizing
key metrics, notes, and provenance.
"""
from pathlib import Path
from typing import Any, Dict
import json


def generate_report(summary: Dict[str, Any], run_out_dir: Path):
    """Write a short `report.txt` describing the run and key metrics.

    summary: dict as produced by `sensor_lab.processor.process_file`
    run_out_dir: Path to the run output folder
    """
    run_out_dir = Path(run_out_dir)
    report_path = run_out_dir / "report.txt"
    try:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write("MagPlotter Run Report\n")
            fh.write("====================\n\n")
            fh.write(f"Run: {summary.get('run_name')}\n")
            fh.write(f"Source path: {summary.get('path')}\n\n")
            fh.write("Metrics:\n")
            metrics = summary.get("metrics", {})
            if isinstance(metrics, dict):
                try:
                    fh.write(json.dumps(metrics, indent=2, ensure_ascii=False))
                except Exception:
                    # Fallback to simple print
                    for k, v in metrics.items():
                        fh.write(f"- {k}: {v}\n")
            else:
                fh.write(str(metrics) + "\n")
            fh.write("\nNotes:\n")
            notes = summary.get("notes_from_file") or "(none)"
            if isinstance(notes, list):
                fh.write("\n".join(notes))
            else:
                fh.write(str(notes))
            fh.write("\n")
    except Exception:
        return None
    return report_path
