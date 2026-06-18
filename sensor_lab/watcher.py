"""
Watchdog-based watcher: monitor the incoming directory and process new CSV files as they appear.

Usage:
    python -m sensor_lab.watcher /path/to/project_root

This module provides a stable-file watcher that waits for file-size
stability before invoking `sensor_lab.processor.process_file` to avoid
processing partially written files.

Security note: watcher processes files found in `incoming/`. Treat
incoming files as untrusted and run watchers with least privilege; do
not run the watcher as an elevated user in hostile environments.
"""
import time
import sys
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from threading import Timer

from .processor import process_file


class StableFileHandler(FileSystemEventHandler):
    """
    When a new file is created, wait until file size is stable for `stability_seconds`
    before processing. This avoids partial-write problems.
    """

    def __init__(self, base_dir: Path, incoming_dir: Path, stability_seconds: float = 1.0):
        self.base_dir = base_dir
        self.incoming_dir = incoming_dir
        self.stability_seconds = stability_seconds
        self._timers = {}

    def on_created(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() != ".csv":
            return
        # schedule stable-check
        self._schedule_check(p)

    def on_modified(self, event):
        # also handle modification events
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() != ".csv":
            return
        self._schedule_check(p)

    def _schedule_check(self, p: Path):
        # cancel existing timer
        if p in self._timers:
            self._timers[p].cancel()

        last_size = p.stat().st_size if p.exists() else -1

        def _check():
            if not p.exists():
                return
            new_size = p.stat().st_size
            if new_size == last_size:
                # stable -> process
                try:
                    print(f"[watcher] processing stable file: {p}")
                    process_file(str(p), base_dir=str(self.base_dir))
                    print(f"[watcher] done: {p.name}")
                except Exception as e:
                    print(f"[watcher] error processing {p}: {e}")
                finally:
                    self._timers.pop(p, None)
            else:
                # reschedule with updated size
                self._timers.pop(p, None)
                self._schedule_check(p)

        t = Timer(self.stability_seconds, _check)
        self._timers[p] = t
        t.start()


def run_watcher(project_root: str = "."):
    base = Path(project_root).resolve()
    incoming = base / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    event_handler = StableFileHandler(base, incoming)
    observer = Observer()
    observer.schedule(event_handler, str(incoming), recursive=False)
    observer.start()
    print(f"[watcher] watching {incoming} ... press Ctrl-C to stop")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    run_watcher(root)
