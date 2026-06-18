"""Centralized logging configuration for MagPlotter.

Call `setup_logging(log_dir)` once at application startup. Every module
then gets its own logger via `logging.getLogger(__name__)`, which inherits
the handlers configured here.

Console: INFO and above
File (logs/magplotter.log): DEBUG and above
"""
import logging
import sys
from pathlib import Path

_FMT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(log_dir: Path = None) -> None:
    """Configure root logger with console + file handlers. Idempotent."""
    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(logging.DEBUG)
    formatter = logging.Formatter(_FMT)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    root.addHandler(ch)

    if log_dir is None:
        log_dir = Path("logs")
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(log_dir / "magplotter.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Suppress noisy third-party DEBUG output from libraries we don't own
    for noisy in ("matplotlib", "PIL", "urllib3", "watchdog"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
