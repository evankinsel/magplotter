"""
Top-level processing orchestration: takes a CSV path, runs cleaning, metrics, plotting,
saves JSON summary, and moves the raw CSV to processed directory.
"""
import json
import os
from pathlib import Path
import shutil
from typing import Optional

from .clean import parse_raw_csv
from .analysis import compute_all_metrics
from .viz import plot_magnitude, plot_axes, plot_heading
import sys
import importlib

# Import report generator from the new src package if available. Provide a no-op fallback.
try:
    report_mod = importlib.import_module("src.report_generator")
    generate_report = report_mod.generate_report
except Exception:
    try:
        report_mod = importlib.import_module("..src.report_generator", package=__package__)
        generate_report = report_mod.generate_report
    except Exception:
        def generate_report(summary, run_out_dir):
            return None


def load_run_notes(csv_path: Path) -> Optional[str]:
    # Look for a sibling notes file like run_001_notes.txt or run_001.txt
    candidates = [
        csv_path.with_name(csv_path.stem + "_notes.txt"),
        csv_path.with_name(csv_path.stem + ".txt"),
    ]
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return None
    return None


def process_file(
    csv_path: str,
    base_dir: str = ".",
    incoming_dir_name: str = "incoming",
    processed_dir_name: str = "processed",
    output_dir_name: str = "output/runs",
) -> dict:
    csv_path = Path(csv_path)
    base = Path(base_dir)
    processed_dir = base / processed_dir_name
    output_runs_dir = base / output_dir_name
    processed_dir.mkdir(parents=True, exist_ok=True)
    output_runs_dir.mkdir(parents=True, exist_ok=True)

    # Parse
    df, header_comments = parse_raw_csv(str(csv_path))
    metrics = compute_all_metrics(df)
    notes_txt = load_run_notes(csv_path)
    # compose summary
    summary = {
        "run_name": csv_path.name,
        "path": str(csv_path),
        "metrics": metrics,
        "notes_from_file": notes_txt,
        "header_comments": header_comments,
    }

    # Prepare output directory per run
    run_out_dir = output_runs_dir / csv_path.stem
    run_out_dir.mkdir(parents=True, exist_ok=True)

    # Save a copy of the raw CSV for provenance
    try:
        raw_copy = run_out_dir / "raw_data.csv"
        shutil.copy(str(csv_path), str(raw_copy))
    except Exception:
        raw_copy = None

    # Save cleaned CSV for provenance (standardized name)
    cleaned_csv_path = run_out_dir / "cleaned_data.csv"
    try:
        df.to_csv(cleaned_csv_path, index=False)
    except Exception:
        pass

    # Also save Parquet for faster I/O and future analysis (requires pyarrow)
    try:
        cleaned_parquet = run_out_dir / "cleaned_data.parquet"
        df.to_parquet(cleaned_parquet, index=False)
    except Exception:
        # ignore if parquet write not available
        cleaned_parquet = None

    # Plots
    # Standardized plot names
    try:
        plot_magnitude(df, str(run_out_dir / "field_strength_plot.png"))
    except Exception:
        pass
    try:
        plot_heading(df, str(run_out_dir / "heading_plot.png"))
    except Exception:
        pass
    # keep an axes/combined plot for debugging
    try:
        plot_axes(df, str(run_out_dir / "axes_plot.png"))
    except Exception:
        pass

    # JSON summary
    # JSON summary (standardized name)
    summary_path = run_out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    # Generate a human-readable report.txt and processing log
    try:
        generate_report(summary, run_out_dir)
    except Exception:
        pass
    try:
        log_path = run_out_dir / "processing_log.txt"
        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write("Processed by sensor_lab.processor\n")
            logf.write(f"source: {csv_path}\n")
            logf.write(f"cleaned_csv: {cleaned_csv_path}\n")
            logf.write(f"summary: {summary_path}\n")
    except Exception:
        pass

    # If this run looks like an 'old' dataset, also mirror outputs under output/old/runs
    try:
        if "old" in csv_path.name.lower() or "old" in str(csv_path.parent).lower():
            alt_out_base = base / "output" / "old" / "runs"
            alt_run_out = alt_out_base / csv_path.stem
            alt_run_out.mkdir(parents=True, exist_ok=True)
            # copy cleaned csv and parquet if present, plus summary and plots
            try:
                if cleaned_csv_path.exists():
                    shutil.copy(str(cleaned_csv_path), str(alt_run_out / cleaned_csv_path.name))
            except Exception:
                pass
            try:
                if cleaned_parquet is not None and cleaned_parquet.exists():
                    shutil.copy(str(cleaned_parquet), str(alt_run_out / cleaned_parquet.name))
            except Exception:
                pass
            try:
                shutil.copy(str(summary_path), str(alt_run_out / summary_path.name))
            except Exception:
                pass
            # copy plots if they exist
            for plot_name in ["field_strength_plot.png", "heading_plot.png", "axes_plot.png"]:
                p = run_out_dir / plot_name
                try:
                    if p.exists():
                        shutil.copy(str(p), str(alt_run_out / p.name))
                except Exception:
                    pass
    except Exception:
        pass

    # Move raw CSV to processed
    try:
        dst = processed_dir / csv_path.name
        shutil.move(str(csv_path), str(dst))
    except Exception:
        # if move fails, ignore — don't crash
        pass

    return summary
