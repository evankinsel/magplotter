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

    # Save cleaned CSV for provenance
    cleaned_csv_path = run_out_dir / f"{csv_path.stem}_cleaned.csv"
    try:
        df.to_csv(cleaned_csv_path, index=False)
    except Exception:
        pass

    # Plots
    plot_magnitude(df, str(run_out_dir / f"{csv_path.stem}_B.png"))
    plot_axes(df, str(run_out_dir / f"{csv_path.stem}_noise.png"))
    plot_heading(df, str(run_out_dir / f"{csv_path.stem}_heading.png"))

    # JSON summary
    summary_path = run_out_dir / f"{csv_path.stem}_summary.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    # Move raw CSV to processed
    try:
        dst = processed_dir / csv_path.name
        shutil.move(str(csv_path), str(dst))
    except Exception:
        # if move fails, ignore — don't crash
        pass

    return summary
