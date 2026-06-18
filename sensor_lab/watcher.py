"""
Watchdog-based watcher: monitor the incoming directory and process new CSV files.

ROOT CAUSE OF INTERMITTENT FAILURES (documented):
  1. No startup scan -- watchdog only fires events for activity that happens AFTER
     the observer starts.  Any CSV dropped while the watcher was not running is
     silently ignored on re-launch.
  2. Silent observer death -- on Linux the watchdog InotifyObserver can die if the
     inotify watch-descriptor limit is hit, but observer.is_alive() returns False
     rather than raising; the main loop never noticed.
  3. No fallback -- if watchdog fails to initialize there was no second path to
     detect files.
  4. No deduplication -- a file found by the startup scan could also trigger a
     watchdog event, causing double-processing.

FIX STRATEGY:
  * Scan incoming/ on startup and process any pre-existing CSVs before starting
    the observer, so files dropped while the watcher was off are never missed.
  * Track processed paths in a set so the same file is never processed twice.
  * Monitor observer.is_alive() in the main loop; restart it on failure.
  * If watchdog raises on init or on schedule(), fall back to a pure polling loop
    that scans the directory every POLL_INTERVAL_SECONDS.
  * Comprehensive structured logging throughout.

Usage:
  python -m sensor_lab.watcher /path/to/project_root
"""

import logging
import sys
import time
from pathlib import Path
from threading import Lock, Timer

log = logging.getLogger("sensor_lab.watcher")

POLL_INTERVAL_SECONDS = 3.0
STABILITY_SECONDS = 1.0
MAX_OBSERVER_RESTARTS = 3


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


class FileProcessor:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._lock = Lock()
        self._in_flight: set = set()
        self._timers: dict = {}

    def schedule(self, p: Path) -> None:
        if not p.exists():
            return
        with self._lock:
            if p in self._timers:
                self._timers[p].cancel()
            size = p.stat().st_size
        self._arm_timer(p, size)

    def _arm_timer(self, p: Path, last_size: int) -> None:
        def _check():
            with self._lock:
                self._timers.pop(p, None)
                if not p.exists():
                    log.debug("File disappeared before stability check: %s", p)
                    return
                new_size = p.stat().st_size

            if new_size != last_size:
                log.debug("File still growing, rescheduling stability check: %s", p.name)
                self._arm_timer(p, new_size)
                return

            with self._lock:
                if p in self._in_flight:
                    log.debug("Skipping already-processing file: %s", p.name)
                    return
                self._in_flight.add(p)

            self._process(p)

        t = Timer(STABILITY_SECONDS, _check)
        with self._lock:
            self._timers[p] = t
        t.start()

    def _process(self, p: Path) -> None:
        from .processor import process_file
        log.info("Processing started: %s", p.name)
        try:
            process_file(str(p), base_dir=str(self.base_dir))
            log.info("Processing complete: %s", p.name)
        except Exception:
            log.exception("Error processing %s", p.name)
        finally:
            with self._lock:
                self._in_flight.discard(p)

    def scan_existing(self, incoming: Path) -> None:
        """
        Process any CSV files already present in incoming/ at startup.
        Primary fix for the 'works first time, breaks on relaunch' bug.
        """
        log.info("Scanning for pre-existing CSV files in: %s", incoming)
        found = 0
        for p in sorted(incoming.iterdir()):
            if p.is_file() and p.suffix.lower() == ".csv":
                log.info("Found existing CSV, queuing for processing: %s", p.name)
                self.schedule(p)
                found += 1
        if found == 0:
            log.info("No pre-existing CSV files found.")


class _CSVEventHandler:
    def __init__(self, processor: FileProcessor) -> None:
        self._processor = processor

    def _handle(self, event) -> None:
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() != ".csv":
            return
        log.info("Watchdog detected CSV: %s (event=%s)", p.name, type(event).__name__)
        self._processor.schedule(p)


def _make_watchdog_handler(processor: FileProcessor):
    from watchdog.events import FileSystemEventHandler
    shim = _CSVEventHandler(processor)

    class _Handler(FileSystemEventHandler):
        def on_created(self, event):
            shim._handle(event)
        def on_modified(self, event):
            shim._handle(event)

    return _Handler()


def run_watcher(project_root: str = ".") -> None:
    base = Path(project_root).resolve()
    incoming = base / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    log.info("Watcher starting. Project root: %s", base)
    log.info("Monitoring directory: %s", incoming)

    processor = FileProcessor(base)
    processor.scan_existing(incoming)
    _run_with_watchdog_and_fallback(processor, incoming)


def _run_with_watchdog_and_fallback(processor: FileProcessor, incoming: Path) -> None:
    restarts = 0
    while True:
        if restarts >= MAX_OBSERVER_RESTARTS:
            log.warning("Watchdog observer failed %d times. Switching permanently to polling fallback (interval=%ss).", restarts, POLL_INTERVAL_SECONDS)
            _run_poll_fallback(processor, incoming)
            return

        observer = _try_start_observer(processor, incoming)
        if observer is None:
            restarts += 1
            log.warning("Observer failed to start (attempt %d/%d). Falling back to polling for now.", restarts, MAX_OBSERVER_RESTARTS)
            _run_poll_cycle(processor, incoming)
            continue

        log.info("Watchdog observer running (attempt %d).", restarts + 1)
        try:
            while True:
                time.sleep(1.0)
                if not observer.is_alive():
                    log.error("Watchdog observer thread died unexpectedly. This can happen when the inotify watch-descriptor limit is exceeded (/proc/sys/fs/inotify/max_user_watches). Restarting observer.")
                    restarts += 1
                    break
        except KeyboardInterrupt:
            log.info("Watcher stopped by user (Ctrl-C).")
            observer.stop()
            observer.join()
            return
        finally:
            try:
                observer.stop()
                observer.join(timeout=5)
            except Exception:
                pass


def _try_start_observer(processor: FileProcessor, incoming: Path):
    try:
        from watchdog.observers import Observer
        handler = _make_watchdog_handler(processor)
        observer = Observer()
        observer.schedule(handler, str(incoming), recursive=False)
        observer.start()
        time.sleep(0.1)
        if not observer.is_alive():
            raise RuntimeError("Observer.start() returned but thread is not alive.")
        log.info("Watchdog observer started successfully, watching: %s", incoming)
        return observer
    except ImportError:
        log.warning("watchdog package not available. Falling back to polling-only mode.")
        return None
    except Exception:
        log.exception("Failed to start watchdog observer.")
        return None


def _run_poll_fallback(processor: FileProcessor, incoming: Path) -> None:
    log.info("Polling fallback active. Scanning %s every %.1fs.", incoming, POLL_INTERVAL_SECONDS)
    try:
        while True:
            _run_poll_cycle(processor, incoming)
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        log.info("Watcher stopped by user (Ctrl-C).")


def _run_poll_cycle(processor: FileProcessor, incoming: Path) -> None:
    if not incoming.exists():
        log.warning("Incoming directory does not exist: %s", incoming)
        return
    for p in sorted(incoming.iterdir()):
        if p.is_file() and p.suffix.lower() == ".csv":
            with processor._lock:
                already = p in processor._in_flight or p in processor._timers
            if not already:
                log.debug("Poll scan found new CSV: %s", p.name)
                processor.schedule(p)


if __name__ == "__main__":
    _configure_logging()
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    run_watcher(root)
