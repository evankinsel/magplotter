"""
Simple CLI to process all current CSVs in `incoming/` (non-watcher mode).

Usage:
    python run_processor.py /path/to/project_root

This small helper is intended for quick one-off processing in environments
where the watcher is not required. It calls `sensor_lab.processor.process_file`
for each CSV in `incoming/`.

Security note: treat input files as untrusted. This script only parses
numeric CSV fields and will not execute code from input files.
"""
import logging
import sys
from pathlib import Path

from src.logger import setup_logging
from sensor_lab.processor import process_file

if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    setup_logging(log_dir=base / "logs")
    logger = logging.getLogger(__name__)

    incoming = base / "incoming"
    if not incoming.exists():
        logger.error("no incoming directory at %s", incoming)
        sys.exit(1)

    csvs = [p for p in incoming.iterdir() if p.is_file() and p.suffix.lower() == ".csv"]
    logger.info("found %d CSV file(s) in %s", len(csvs), incoming)

    for p in csvs:
        logger.info("processing: %s", p.name)
        try:
            process_file(str(p), base_dir=str(base))
            logger.info("done: %s", p.name)
        except Exception:
            logger.exception("failed to process: %s", p.name)
