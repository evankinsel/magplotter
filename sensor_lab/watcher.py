"""
Watchdog-based watcher: monitor the incoming directory and process new CSV files as they appear.

Usage:
    python -m sensor_lab.watcher /path/to/project_root

Runs forever:
  - processes any CSVs already sitting in incoming/ on startup
  - watches for new files via watchdog
  - auto-restarts the observer thread if it dies unexpectedly

The shell script scripts/start-watcher.sh wraps this in an outer crash-restart
loop so the whole process is also restarted if Python itself exits.

Security note: watcher processes files found in `incoming/`. Treat
incoming files as untrusted and run watchers with least privilege; do
not run the watcher as an elevated user in hostile environments.
"""
import logging
import time
import sys
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Timer

from .processor import process_file

logger = logging.getLogger(__name__)


class StableFileHandler(FileSystemEventHandler):
    """
    Wait until file size is stable for `stability_seconds` before processing.
    Prevents partial-write problems with files still being written.
    """

    def __init__(self, base_dir: Path, stability_seconds: float = 1.0):
        self.base_dir = base_dir
        self.stability_seconds = stability_seconds
        self._timers: dict = {}

    def on_created(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() == ".csv":
            logger.info("CSV detected: %s", p.name)
            self._schedule_check(p)

    def on_modified(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() == ".csv":
            self._schedule_check(p)

    def _schedule_check(self, p: Path):
        if p in self._timers:
            self._timers[p].cancel()

        last_size = p.stat().st_size if p.exists() else -1

        def _check():
            self._timers.pop(p, None)
            if not p.exists():
                logger.warning("file disappeared before processing: %s", p.name)
                return
            new_size = p.stat().st_size
            if new_size != last_size:
                logger.debug("file still changing, rescheduling: %s", p.name)
                self._schedule_check(p)
                return
            logger.info("file stable, processing: %s", p.name)
            try:
                process_file(str(p), base_dir=str(self.base_dir))
                logger.info("processing complete: %s", p.name)
            except Exception:
                logger.exception("error processing %s", p.name)

        t = Timer(self.stability_seconds, _check)
        self._timers[p] = t
        t.start()


def _start_observer(base: Path, incoming: Path) -> Observer:
    handler = StableFileHandler(base)
    obs = Observer()
    obs.schedule(handler, str(incoming), recursive=False)
    obs.start()
    return obs


def run_watcher(project_root: str = "."):
    from src.logger import setup_logging
    base = Path(project_root).resolve()
    setup_logging(log_dir=base / "logs")

    incoming = base / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    logger.info("watcher starting — project root: %s", base)

    # Process any CSVs already sitting in incoming/ before we start watching
    existing = sorted(incoming.glob("*.csv")) + sorted(incoming.glob("*.CSV"))
    if existing:
        logger.info("%d file(s) found on startup — processing before watching", len(existing))
        for p in existing:
            logger.info("processing existing file: %s", p.name)
            try:
                process_file(str(p), base_dir=str(base))
                logger.info("done: %s", p.name)
            except Exception:
                logger.exception("error processing %s", p.name)

    observer = _start_observer(base, incoming)
    logger.info("watching %s for new CSV files", incoming)
    print(f"[watcher] watching {incoming} for new CSV files ... press Ctrl-C to stop", flush=True)

    try:
        while True:
            time.sleep(1.0)
            if not observer.is_alive():
                logger.warning("observer thread died — restarting")
                try:
                    observer.stop()
                except Exception:
                    pass
                observer = _start_observer(base, incoming)
    except KeyboardInterrupt:
        logger.info("shutdown requested")
    finally:
        observer.stop()
        observer.join()
        logger.info("watcher stopped")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    run_watcher(root)
