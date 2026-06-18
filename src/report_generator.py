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


def generate_report(summary: Dict[str, Any], run_out_dir: Path):
    """Write a short `report.txt` describing the run and key metrics."""
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
            fh.write("Metrics:\n")
            metrics = summary.get("metrics", {})
            if isinstance(metrics, dict):
                try:
                    fh.write(json.dumps(metrics, indent=2, ensure_ascii=False))
                except Exception:
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
        logger.debug("report written: %s", report_path)
    except Exception:
        logger.exception("failed to write report for run: %s", run_name)
        return None
    return report_path
