"""
Watchdog-based watcher: monitor the incoming directory and process new CSV files.

Design notes — how stability checking and deduplication work
------------------------------------------------------------
FileProcessor uses a per-path generation counter (_seq) instead of storing timer
references.  When schedule() is called for a path that already has a pending timer,
the generation is bumped; the old timer fires, sees a stale generation, and aborts
without touching the file.  No explicit timer cancellation is required, which
eliminates the race between timer creation (outside the lock) and timer storage
(inside the lock) that existed in the previous _timers dict approach.

State held per FileProcessor instance:
    _seq       – path → current generation int.  Presence means a stability check
                 is pending.  Absence means the path is either idle or in-flight.
    _in_flight – paths currently inside process_file().
    _failed    – paths that raised SchemaValidationError; these are permanently
                 broken inputs that should never be re-queued.

stat() calls are always performed outside the lock.  The lock only protects the
in-memory dicts and sets — never blocks on filesystem I/O.

Observer/poll strategy:
    1. Scan incoming/ at startup so files dropped while the watcher was off are caught.
    2. watchdog observer for low-latency event detection.
    3. If the observer dies or was never available, fall back to polling.
    4. Restart the observer up to MAX_OBSERVER_RESTARTS times before switching
       permanently to polling.

Usage:
    python -m sensor_lab.watcher /path/to/project_root
"""

import logging
import sys
import time
from pathlib import Path
from threading import Lock, Timer

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 3.0
STABILITY_SECONDS = 1.0
MAX_OBSERVER_RESTARTS = 3


class FileProcessor:
    """Thread-safe file stability checker and dispatcher.

    Multiple threads (watchdog callbacks, poll cycle, timer threads) call schedule()
    concurrently.  The generation counter makes races benign: whichever timer fires
    last simply finds a stale generation and returns immediately.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._lock = Lock()
        self._seq: dict = {}        # path -> current generation int
        self._in_flight: set = set()
        self._failed: set = set()   # paths with permanent schema failures

    def schedule(self, p: Path) -> None:
        """Enqueue p for a file-size stability check.

        Safe to call from any thread.  Re-schedules an already-pending path by
        bumping its generation — the old timer becomes a no-op when it fires.
        """
        with self._lock:
            if p in self._failed:
                logger.debug("skipping permanently-failed file: %s", p.name)
                return
            if p in self._in_flight:
                logger.debug("file already in flight, deferring: %s", p.name)
                return
            gen = self._seq.get(p, 0) + 1
            self._seq[p] = gen

        # stat() outside the lock — no filesystem I/O under the mutex
        try:
            size = p.stat().st_size
        except OSError:
            with self._lock:
                if self._seq.get(p) == gen:
                    self._seq.pop(p, None)
            return

        self._arm_timer(p, size, gen)

    def _arm_timer(self, p: Path, last_size: int, gen: int) -> None:
        """Start a one-shot timer that checks size stability after STABILITY_SECONDS.

        The closure captures gen.  On firing it compares gen against the current
        _seq value; a mismatch means schedule() was called again and this timer
        is stale — it returns immediately without touching _in_flight.
        """
        def _check() -> None:
            # stat() outside the lock
            try:
                new_size = p.stat().st_size
            except OSError:
                new_size = None

            with self._lock:
                if self._seq.get(p) != gen:
                    # A newer schedule() call superseded us — nothing to do
                    return
                if new_size is None:
                    logger.debug("file disappeared before stability check: %s", p)
                    self._seq.pop(p, None)
                    return
                if new_size != last_size:
                    # File is still growing — bump generation and reschedule
                    next_gen = gen + 1
                    self._seq[p] = next_gen
                    next_size = new_size
                    claim = False
                else:
                    # Stable — claim the file for processing
                    self._seq.pop(p, None)
                    self._in_flight.add(p)
                    next_gen = None
                    next_size = None
                    claim = True

            if not claim:
                logger.debug(
                    "file still growing (%d → %d bytes), rescheduling: %s",
                    last_size, next_size, p.name,
                )
                self._arm_timer(p, next_size, next_gen)
            else:
                self._process(p)

        t = Timer(STABILITY_SECONDS, _check)
        t.daemon = True
        t.start()

    def _process(self, p: Path) -> None:
        from .processor import process_file
        from .clean import SchemaValidationError
        logger.info("processing started: %s", p.name)
        try:
            process_file(str(p), base_dir=str(self.base_dir))
            logger.info("processing complete: %s", p.name)
        except SchemaValidationError as exc:
            logger.error(
                "permanent schema failure for %s — will not retry: %s",
                p.name, exc,
            )
            with self._lock:
                self._failed.add(p)
        except Exception:
            logger.exception("error processing %s — may retry on next event", p.name)
        finally:
            with self._lock:
                self._in_flight.discard(p)

    def scan_existing(self, incoming: Path) -> None:
        """Queue any CSV files already present in incoming/ at startup."""
        logger.info("scanning for pre-existing CSV files in: %s", incoming)
        found = 0
        for p in sorted(incoming.iterdir()):
            if p.is_file() and p.suffix.lower() == ".csv":
                logger.info("found existing CSV, queuing: %s", p.name)
                self.schedule(p)
                found += 1
        if found == 0:
            logger.info("no pre-existing CSV files found")


class _CSVEventHandler:
    def __init__(self, processor: FileProcessor) -> None:
        self._processor = processor

    def _handle(self, event) -> None:
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() != ".csv":
            return
        logger.info("watchdog detected CSV: %s (event=%s)", p.name, type(event).__name__)
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
    from src.logger import setup_logging
    base = Path(project_root).resolve()
    setup_logging(log_dir=base / "logs")

    incoming = base / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    logger.info("watcher starting — project root: %s", base)
    logger.info("monitoring directory: %s", incoming)

    processor = FileProcessor(base)
    processor.scan_existing(incoming)
    _run_with_watchdog_and_fallback(processor, incoming)


def _run_with_watchdog_and_fallback(processor: FileProcessor, incoming: Path) -> None:
    restarts = 0
    while True:
        if restarts >= MAX_OBSERVER_RESTARTS:
            logger.warning(
                "watchdog observer failed %d times — switching permanently to polling "
                "(interval=%.1fs)",
                restarts, POLL_INTERVAL_SECONDS,
            )
            _run_poll_fallback(processor, incoming)
            return

        observer = _try_start_observer(processor, incoming)
        if observer is None:
            restarts += 1
            logger.warning(
                "observer failed to start (attempt %d/%d) — polling this cycle",
                restarts, MAX_OBSERVER_RESTARTS,
            )
            _run_poll_cycle(processor, incoming)
            continue

        logger.info("watchdog observer running (attempt %d)", restarts + 1)
        try:
            while True:
                time.sleep(1.0)
                if not observer.is_alive():
                    logger.error(
                        "watchdog observer thread died unexpectedly — this can happen "
                        "when the inotify watch-descriptor limit is exceeded "
                        "(/proc/sys/fs/inotify/max_user_watches). Restarting."
                    )
                    restarts += 1
                    break
        except KeyboardInterrupt:
            logger.info("watcher stopped by user (Ctrl-C)")
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
        logger.info("watchdog observer started successfully, watching: %s", incoming)
        return observer
    except ImportError:
        logger.warning("watchdog package not available — polling-only mode")
        return None
    except Exception:
        logger.exception("failed to start watchdog observer")
        return None


def _run_poll_fallback(processor: FileProcessor, incoming: Path) -> None:
    logger.info(
        "polling fallback active — scanning %s every %.1fs",
        incoming, POLL_INTERVAL_SECONDS,
    )
    try:
        while True:
            _run_poll_cycle(processor, incoming)
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("watcher stopped by user (Ctrl-C)")


def _run_poll_cycle(processor: FileProcessor, incoming: Path) -> None:
    if not incoming.exists():
        logger.warning("incoming directory does not exist: %s", incoming)
        return
    for p in sorted(incoming.iterdir()):
        if p.is_file() and p.suffix.lower() == ".csv":
            with processor._lock:
                pending = (
                    p in processor._seq
                    or p in processor._in_flight
                    or p in processor._failed
                )
            if not pending:
                logger.debug("poll scan found new CSV: %s", p.name)
                processor.schedule(p)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    run_watcher(root)
