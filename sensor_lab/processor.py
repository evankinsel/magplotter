"""
Pipeline orchestrator: executes the five-stage sensor processing pipeline and handles
all file I/O (reading, writing, archiving).

Pipeline stages (each a pure function — no embedded file I/O):
    1. Ingestion / Cleaning  — parse_raw_csv         (sensor_lab.clean)
    2. Transformation        — transform_sensor_data  (sensor_lab.transform)
    3. Analysis              — compute_all_metrics    (sensor_lab.analysis)
    4. Visualisation         — render_magnitude /
                               render_axes /
                               render_heading         (sensor_lab.viz)

All I/O (saving figures, writing JSON/CSV, archiving the raw file) is consolidated
in process_file().  Stages are called in sequence and their outputs passed explicitly
between them.  A SchemaValidationError from the ingestion boundary propagates to the
caller unchanged; all other stage failures are caught and logged so that processing
of the next file can continue.

Public API:
    process_file(csv_path, base_dir, incoming_dir_name, processed_dir_name, output_dir_name)
"""
import importlib
import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt

from .clean import parse_raw_csv
from .transform import transform_sensor_data
from .analysis import compute_all_metrics
from .viz import render_magnitude, render_axes, render_heading

try:
    from src.field_mapping import (
        run_field_mapping,
        load_config as _load_fm_config,
        read_spatial_csv as _read_fm_csv,
    )
    _FIELD_MAPPING_AVAILABLE = True
except Exception as _fm_import_err:
    _FIELD_MAPPING_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "field mapping subsystem unavailable: %s", _fm_import_err
    )

logger = logging.getLogger(__name__)

try:
    report_mod = importlib.import_module("src.report_generator")
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


def _save_figure(fig: plt.Figure, path: Path, label: str) -> None:
    try:
        fig.savefig(str(path))
        logger.info("%s saved: %s", label, path)
    except Exception:
        logger.warning("%s save failed: %s", label, path)
    finally:
        plt.close(fig)


def process_file(
    csv_path: str,
    base_dir: str = ".",
    incoming_dir_name: str = "incoming",
    processed_dir_name: str = "processed",
    output_dir_name: str = "output",
) -> dict:
    """
    Run the full pipeline for one CSV file.

    Stage execution order:
        1. Ingest + Clean  — parse_raw_csv (raises SchemaValidationError on bad input)
        2. Transform       — transform_sensor_data
        3. Analyze         — compute_all_metrics
        4. Visualize       — render_magnitude / render_axes / render_heading
        5. I/O             — save figures, JSON summary, report, processing log; archive raw CSV

    Returns the summary dict written to summary.json.
    """
    csv_path = Path(csv_path)
    base = Path(base_dir)
    processed_dir = base / processed_dir_name
    output_runs_dir = base / output_dir_name
    processed_dir.mkdir(parents=True, exist_ok=True)
    output_runs_dir.mkdir(parents=True, exist_ok=True)

    run_name = csv_path.stem
    run_ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    run_id = f"{run_name}_{run_ts}"
    logger.info("pipeline starting — run_id: %s, source: %s", run_id, csv_path)
    t_start = time.monotonic()

    # ── Stage 1: Ingestion + Cleaning ─────────────────────────────────────────
    # SchemaValidationError propagates to caller; bad inputs are rejected here.
    logger.info("stage 1 [ingest+clean]: %s", csv_path.name)
    df, header_comments = parse_raw_csv(str(csv_path))
    logger.info("stage 1 complete: %d rows", len(df))

    # ── Stage 2: Transformation ───────────────────────────────────────────────
    logger.info("stage 2 [transform]: run=%s", run_name)
    df = transform_sensor_data(df)
    logger.debug("stage 2 complete: columns=%s", sorted(df.columns.tolist()))

    # ── Stage 3: Analysis ─────────────────────────────────────────────────────
    logger.info("stage 3 [analyze]: run=%s", run_name)
    metrics = compute_all_metrics(df)
    logger.debug("stage 3 complete: B_mean=%s, samples=%s", metrics.get("B_mean"), metrics.get("num_samples"))

    # ── Stage 4: Visualisation ────────────────────────────────────────────────
    logger.info("stage 4 [visualize]: run=%s", run_name)
    figures = {
        "field_strength_plot.png": render_magnitude(df),
        "heading_plot.png": render_heading(df),
        "axes_plot.png": render_axes(df),
    }
    logger.debug("stage 4 complete: %d figures rendered", len(figures))

    # ── Stage 5: I/O ─────────────────────────────────────────────────────────
    run_out_dir = output_runs_dir / run_id
    run_out_dir.mkdir(parents=True, exist_ok=True)

    notes_txt = load_run_notes(csv_path)
    summary = {
        "run_name": csv_path.name,
        "run_id": run_id,
        "run_timestamp": run_ts,
        "path": str(csv_path),
        "metrics": metrics,
        "notes_from_file": notes_txt,
        "header_comments": header_comments,
    }

    # Archive raw CSV
    try:
        shutil.copy(str(csv_path), str(run_out_dir / "raw_data.csv"))
    except Exception:
        logger.warning("could not archive raw CSV for run: %s", run_name)

    # Save cleaned + transformed CSV
    try:
        df.to_csv(run_out_dir / "cleaned_data.csv", index=False)
    except Exception:
        logger.warning("could not save cleaned CSV for run: %s", run_name)

    # Save Parquet (optional — silently skipped when pyarrow is absent)
    try:
        df.to_parquet(run_out_dir / "cleaned_data.parquet", index=False)
    except Exception:
        logger.debug("Parquet save skipped for run: %s", run_name)

    # Save figures
    for filename, fig in figures.items():
        _save_figure(fig, run_out_dir / filename, filename)

    # Field mapping (optional subsystem — skipped when spatial columns absent)
    if _FIELD_MAPPING_AVAILABLE:
        logger.info("field mapping: attempting for run: %s", run_name)
        try:
            fm_config = _load_fm_config(base_dir=base)
            # Read the spatial CSV here (all columns preserved) so run_field_mapping
            # receives a DataFrame — file I/O stays in the orchestrator.
            fm_df = _read_fm_csv(str(csv_path))
            if fm_df is not None:
                fm_result = run_field_mapping(
                    fm_df,
                    output_dir=run_out_dir,
                    config=fm_config,
                )
                if fm_result is not None:
                    summary["field_mapping"] = fm_result
                    logger.info(
                        "field mapping: complete — %d file(s) generated",
                        len(fm_result.get("generated_files", [])),
                    )
                else:
                    logger.debug("field mapping: no spatial data — skipped for run: %s", run_name)
            else:
                logger.debug("field mapping: could not read spatial CSV — skipped for run: %s", run_name)
        except Exception:
            logger.warning("field mapping failed for run: %s", run_name, exc_info=True)

    # JSON summary
    summary_path = run_out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    # Report
    try:
        generate_report(summary, run_out_dir)
    except Exception:
        logger.warning("report generation failed for run: %s", run_name)

    # Processing log
    try:
        with open(run_out_dir / "processing_log.txt", "w", encoding="utf-8") as logf:
            logf.write("Processed by sensor_lab.processor\n")
            logf.write(f"source: {csv_path}\n")
            logf.write(f"summary: {summary_path}\n")
    except Exception:
        logger.warning("could not write processing_log.txt for run: %s", run_name)

    # Move raw CSV to processed
    try:
        shutil.move(str(csv_path), str(processed_dir / csv_path.name))
        logger.info("archived: %s -> %s/", csv_path.name, processed_dir)
    except Exception:
        logger.warning("could not move %s to processed/", csv_path.name)

    duration = time.monotonic() - t_start
    logger.info(
        "pipeline complete — run_id: %s, duration: %.2fs, output: %s",
        run_id, duration, run_out_dir,
    )
    return summary
