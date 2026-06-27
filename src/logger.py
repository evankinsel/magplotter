"""Centralized logging configuration for MagPlotter.

Call `setup_logging(log_dir)` once at application startup. Every module
then gets its own logger via `logging.getLogger(__name__)`, which inherits
the handlers configured here.

Console: INFO and above
File (logs/magplotter.log): DEBUG and above, rotated at 5 MB (3 backups)
Per-run file: use add_run_file_handler / remove_run_file_handler
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FMT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_MAX_BYTES = 5 * 1024 * 1024   # 5 MB per log file
_BACKUP_COUNT = 3


def setup_logging(log_dir: Path = None) -> None:
    """Configure root logger with console + rotating file handlers. Idempotent."""
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

    fh = RotatingFileHandler(
        log_dir / "magplotter.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Suppress noisy third-party DEBUG output from libraries we don't own
    for noisy in ("matplotlib", "PIL", "urllib3", "watchdog"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def add_run_file_handler(log_path: Path) -> logging.FileHandler:
    """Attach a FileHandler writing DEBUG+ to log_path for the duration of one run.

    Returns the handler so the caller can pass it to remove_run_file_handler.
    """
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT))
    logging.getLogger().addHandler(fh)
    return fh


def remove_run_file_handler(fh: logging.FileHandler) -> None:
    """Flush, close, and detach a handler created by add_run_file_handler."""
    try:
        fh.flush()
        fh.close()
    finally:
        logging.getLogger().removeHandler(fh)
