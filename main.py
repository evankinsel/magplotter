#!/usr/bin/env python3
"""MagPlotter CLI - scan `incoming/`, process CSV files, and write organized output.

Usage:
    python main.py                      # process all CSVs in incoming/ once
    python main.py --watch              # watch incoming/ forever, auto-process new files
    python main.py /path/to/project     # process in a specific folder
    python main.py /path/to/project --watch  # watch a specific folder

This module provides a simple command-line entrypoint for batch or
watcher-based processing. It delegates actual work to `sensor_lab.processor`
and `sensor_lab.watcher`.

Security note: input CSV files are treated as untrusted data. The CLI
parses numeric fields only and does not execute code from input files.
Exercise normal operational caution when running in multi-user or
networked environments.
"""
import logging
import sys
import argparse
from pathlib import Path

from src.logger import setup_logging
from sensor_lab.processor import process_file
from sensor_lab.watcher import run_watcher
from src.file_manager import list_csv_files, ensure_dirs

logger = logging.getLogger(__name__)


def _print_header():
    print("=================================")
    print("MagPlotter")
    print("Magnetometer Data Processing Tool")
    print("=================================")
    print()


def process_csvs_once(base: Path):
    """Scan incoming/ and process all CSVs once."""
    incoming = base / "incoming"
    output = base / "output"

    ensure_dirs(base)

    logger.info("scanning incoming folder: %s", incoming)

    csvs = list_csv_files(incoming)
    n = len(csvs)
    logger.info("found %d CSV file(s)", n)

    print()
    print(f"Found {n} CSV file{'' if n==1 else 's'}.")
    if n == 0:
        print("Nothing to do. Place CSV files into the incoming/ folder and re-run.")
        return 0

    print()
    print("Processing:")
    failures = []
    for p in csvs:
        try:
            process_file(str(p), base_dir=str(base), output_dir_name="output")
            print(f"✓ {p.name}")
        except Exception as e:
            logger.exception("failed to process %s", p.name)
            print(f"✗ {p.name}  ({e})")
            failures.append((p.name, str(e)))

    print()
    print("Processing complete.")
    print()
    print("Results saved to:")
    print(output)
    logger.info("batch processing complete — results in %s", output)

    if failures:
        print()
        print("Some files failed to process:")
        for name, err in failures:
            print(f"- {name}: {err}")

    return 0


def main(project_root: str = ".", watch: bool = False):
    base = Path(project_root).resolve()
    setup_logging(log_dir=base / "logs")

    _print_header()
    logger.info("MagPlotter starting — root: %s, watch=%s", base, watch)

    if watch:
        run_watcher(str(base))
        return 0
    else:
        return process_csvs_once(base)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MagPlotter batch processor")
    parser.add_argument("root", nargs="?", default=".", help="Project root (default: .)")
    parser.add_argument("--watch", action="store_true", help="Watch incoming/ forever and auto-process new files")
    args = parser.parse_args()
    raise SystemExit(main(args.root, args.watch))
