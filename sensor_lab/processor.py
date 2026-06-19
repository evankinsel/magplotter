"""
Top-level processing orchestration: takes a CSV path, runs cleaning, metrics, plotting,
saves JSON summary, and moves the raw CSV to processed directory.

Public API:
    process_file(csv_path, base_dir=..., incoming_dir_name=..., processed_dir_name=..., output_dir_name=...)

This module coordinates the pipeline steps (parse -> analyze -> plot -> save).
It attempts to be robust: non-fatal failures in optional outputs (Parquet,
plots) are ignored so processing of other runs continues.

Security note: input files are treated as untrusted data. The processor
reads numeric fields only and never executes content from input CSVs.
"""
import json
import logging
import importlib
import time
from pathlib import Path
import shutil
from typing import Optional

from .clean import parse_raw_csv
from .analysis import compute_all_metrics
from .viz import plot_magnitude, plot_axes, plot_heading

# Field mapping is an optional subsystem — import at module level so the
# ImportError surfaces clearly during development rather than silently at runtime.
try:
    from src.field_mapping import run_field_mapping, load_config as _load_fm_config
    _FIELD_MAPPING_AVAILABLE = True
except Exception as _fm_import_err:
    _FIELD_MAPPING_AVAILABLE = False
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "field mapping subsystem unavailable: %s", _fm_import_err
    )

logger = logging.getLogger(__name__)

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
    candidates = [
        csv_path.with_name(csv_path.stem + "_notes.txt"),
        csv_path.with_name(csv_path.stem + ".txt"),
    ]
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                logger.warning("could not read notes file: %s", p)
                return None
    return None


def process_file(
    csv_path: str,
    base_dir: str = ".",
    incoming_dir_name: str = "incoming",
    processed_dir_name: str = "processed",
    output_dir_name: str = "output",
) -> dict:
    csv_path = Path(csv_path)
    base = Path(base_dir)
    processed_dir = base / processed_dir_name
    output_runs_dir = base / output_dir_name
    processed_dir.mkdir(parents=True, exist_ok=True)
    output_runs_dir.mkdir(parents=True, exist_ok=True)

    run_name = csv_path.stem
    logger.info("starting pipeline — run: %s, source: %s", run_name, csv_path)
    t_start = time.monotonic()

    # Parse
    logger.info("parsing CSV: %s", csv_path.name)
    df, header_comments = parse_raw_csv(str(csv_path))
    logger.info("parsed %d rows from %s", len(df), csv_path.name)

    # Analyze
    logger.info("computing metrics — run: %s", run_name)
    metrics = compute_all_metrics(df)
    logger.debug("metrics: samples=%d, B_mean=%s", metrics.get("num_samples"), metrics.get("B_mean"))

    notes_txt = load_run_notes(csv_path)
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
    logger.debug("output directory: %s", run_out_dir)

    # Save a copy of the raw CSV for provenance
    try:
        raw_copy = run_out_dir / "raw_data.csv"
        shutil.copy(str(csv_path), str(raw_copy))
        logger.debug("raw CSV archived to: %s", raw_copy)
    except Exception:
        logger.warning("could not archive raw CSV for run: %s", run_name)
        raw_copy = None

    # Save cleaned CSV
    cleaned_csv_path = run_out_dir / "cleaned_data.csv"
    try:
        df.to_csv(cleaned_csv_path, index=False)
        logger.debug("cleaned CSV saved: %s", cleaned_csv_path)
    except Exception:
        logger.warning("could not save cleaned CSV for run: %s", run_name)

    # Save Parquet
    cleaned_parquet = None
    try:
        cleaned_parquet = run_out_dir / "cleaned_data.parquet"
        df.to_parquet(cleaned_parquet, index=False)
        logger.debug("Parquet saved: %s", cleaned_parquet)
    except Exception:
        logger.debug("Parquet save skipped (pyarrow unavailable?) for run: %s", run_name)
        cleaned_parquet = None

    # Plots
    logger.info("generating plots — run: %s", run_name)
    try:
        plot_magnitude(df, str(run_out_dir / "field_strength_plot.png"))
    except Exception:
        logger.warning("field_strength plot failed for run: %s", run_name)
    try:
        plot_heading(df, str(run_out_dir / "heading_plot.png"))
    except Exception:
        logger.warning("heading plot failed for run: %s", run_name)
    try:
        plot_axes(df, str(run_out_dir / "axes_plot.png"))
    except Exception:
        logger.warning("axes plot failed for run: %s", run_name)

    # Field mapping (runs only when spatial coordinate columns are detected)
    if _FIELD_MAPPING_AVAILABLE:
        logger.info("field mapping: attempting for run: %s", run_name)
        try:
            fm_config = _load_fm_config(base_dir=base)
            fm_result = run_field_mapping(
                str(csv_path),
                output_dir=run_out_dir,
                base_dir=base,
                config=fm_config,
            )
            if fm_result is not None:
                summary["field_mapping"] = fm_result
                logger.info(
                    "field mapping: complete — %d file(s) generated",
                    len(fm_result.get("generated_files", [])),
                )
            else:
                logger.debug("field mapping: no spatial data detected — skipped for run: %s", run_name)
        except Exception:
            logger.warning("field mapping failed for run: %s", run_name, exc_info=True)

    # JSON summary
    summary_path = run_out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    logger.debug("summary JSON saved: %s", summary_path)

    # Report
    try:
        generate_report(summary, run_out_dir)
    except Exception:
        logger.warning("report generation failed for run: %s", run_name)

    # Processing log
    try:
        log_path = run_out_dir / "processing_log.txt"
        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write("Processed by sensor_lab.processor\n")
            logf.write(f"source: {csv_path}\n")
            logf.write(f"cleaned_csv: {cleaned_csv_path}\n")
            logf.write(f"summary: {summary_path}\n")
    except Exception:
        logger.warning("could not write processing_log.txt for run: %s", run_name)

    # Move raw CSV to processed
    try:
        dst = processed_dir / csv_path.name
        shutil.move(str(csv_path), str(dst))
        logger.info("archived to processed: %s -> %s", csv_path.name, dst)
    except Exception:
        logger.warning("could not move %s to processed directory", csv_path.name)

    duration = time.monotonic() - t_start
    logger.info("pipeline complete — run: %s, duration: %.2fs, output: %s",
                run_name, duration, run_out_dir)

    return summary
