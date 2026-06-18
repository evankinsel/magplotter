"""Simple file management helpers for MagPlotter CLI.

Functions to list incoming CSVs and ensure output folders exist.

Public functions:
    list_csv_files(incoming_dir: Path) -> List[Path]
    ensure_dirs(base_dir: Path, incoming: str = "incoming", processed: str = "processed", output: str = "output")

Security note: these helpers create directories and list files. When
integrating into multi-user systems, run with appropriate permissions
and avoid exposing output folders to untrusted writers.
"""
from pathlib import Path
from typing import List


def list_csv_files(incoming_dir: Path) -> List[Path]:
    incoming_dir.mkdir(parents=True, exist_ok=True)
    return sorted([p for p in incoming_dir.iterdir() if p.suffix.lower() == ".csv" and p.is_file()])


def ensure_dirs(base_dir: Path, incoming: str = "incoming", processed: str = "processed", output: str = "output"):
    (base_dir / incoming).mkdir(parents=True, exist_ok=True)
    (base_dir / processed).mkdir(parents=True, exist_ok=True)
    (base_dir / output).mkdir(parents=True, exist_ok=True)
