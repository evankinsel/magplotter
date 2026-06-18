"""Simple file management helpers for MagPlotter CLI.

Functions to list incoming CSVs and ensure output folders exist.

Public functions:
    list_csv_files(incoming_dir: Path) -> List[Path]
    ensure_dirs(base_dir: Path, incoming: str = "incoming", processed: str = "processed", output: str = "output")

Security note: these helpers create directories and list files. When
integrating into multi-user systems, run with appropriate permissions
and avoid exposing output folders to untrusted writers.
"""
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def list_csv_files(incoming_dir: Path) -> List[Path]:
    incoming_dir.mkdir(parents=True, exist_ok=True)
    files = sorted([p for p in incoming_dir.iterdir() if p.suffix.lower() == ".csv" and p.is_file()])
    logger.debug("found %d CSV file(s) in %s", len(files), incoming_dir)
    return files


def ensure_dirs(base_dir: Path, incoming: str = "incoming", processed: str = "processed", output: str = "output"):
    for name in (incoming, processed, output):
        d = base_dir / name
        d.mkdir(parents=True, exist_ok=True)
        logger.debug("ensured directory: %s", d)
