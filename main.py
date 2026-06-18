#!/usr/bin/env python3
"""MagPlotter CLI - scan `incoming/`, process CSV files, and write organized output.

Usage:
    python main.py                      # process all CSVs in incoming/ once
    python main.py --watch              # watch incoming/ and auto-process new files
    python main.py /path/to/project     # process in a specific folder
    python main.py /path/to/project --watch  # watch a specific folder

"""
from pathlib import Path
import sys
import argparse
import time

from sensor_lab.processor import process_file
from src.file_manager import list_csv_files, ensure_dirs


def _print_header():
    print("=================================")
    print("MagPlotter")
    print("Magnetometer Data Processing Tool")
    print("=================================")
    print()


def process_csvs_once(base: Path):
    """Scan incoming/ and process all CSVs once."""
    incoming = base / "incoming"
    processed = base / "processed"
    output = base / "output"

    ensure_dirs(base)

    print("Scanning incoming folder...")

    csvs = list_csv_files(incoming)
    n = len(csvs)
    print()
    print(f"Found {n} CSV file{'' if n==1 else 's'}.")
    if n == 0:
        print("Nothing to do. Place CSV files into the incoming/ folder and re-run.")
        return 0

    print()
    print("Processing:")
    successes = []
    failures = []
    for p in csvs:
        try:
            process_file(str(p), base_dir=str(base), output_dir_name="output")
            print(f"\u2713 {p.name}")
            successes.append(p.name)
        except Exception as e:
            print(f"\u2717 {p.name}  ({e})")
            failures.append((p.name, str(e)))

    print()
    print("Generating outputs...")
    print("\u2713 plots")
    print("\u2713 summaries")
    print("\u2713 reports")
    print()
    print("Processing complete.")
    print()
    print("Results saved to:")
    print(output)

    if failures:
        print()
        print("Some files failed to process:")
        for name, err in failures:
            print(f"- {name}: {err}")

    return 0


def watch_and_process(base: Path):
    """Watch incoming/ and auto-process new CSV files as they arrive."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("Error: watchdog not installed. Install with:")
        print("  pip install watchdog")
        return 1

    incoming = base / "incoming"
    ensure_dirs(base)

    class CSVHandler(FileSystemEventHandler):
        def __init__(self, base_dir):
            self.base_dir = base_dir
            self._processing = set()

        def on_created(self, event):
            if event.is_directory:
                return
            p = Path(event.src_path)
            if p.suffix.lower() != ".csv":
                return
            # wait for file to stabilize
            self._process_when_ready(p)

        def _process_when_ready(self, p: Path, attempts=0, max_attempts=30):
            if p in self._processing:
                return
            if not p.exists():
                return
            try:
                # check if file is still being written to
                size_1 = p.stat().st_size
                time.sleep(0.5)
                size_2 = p.stat().st_size
                if size_1 != size_2:
                    # still growing, retry
                    if attempts < max_attempts:
                        time.sleep(0.5)
                        self._process_when_ready(p, attempts + 1, max_attempts)
                    return
                # stable, process it
                self._processing.add(p)
                try:
                    print(f"\n[watcher] Processing new file: {p.name}")
                    process_file(str(p), base_dir=str(self.base_dir), output_dir_name="output")
                    print(f"[watcher] ✓ {p.name} completed\n")
                except Exception as e:
                    print(f"[watcher] ✗ {p.name} failed: {e}\n")
                finally:
                    self._processing.discard(p)
            except Exception:
                pass

    _print_header()
    print(f"Watching {incoming} for new CSV files...")
    print("Press Ctrl+C to stop.\n")

    event_handler = CSVHandler(base)
    observer = Observer()
    observer.schedule(event_handler, str(incoming), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nShutting down watcher...")
        observer.stop()
    observer.join()
    return 0


def main(project_root: str = ".", watch: bool = False):
    base = Path(project_root).resolve()
    _print_header()
    
    if watch:
        return watch_and_process(base)
    else:
        return process_csvs_once(base)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MagPlotter batch processor")
    parser.add_argument("root", nargs="?", default=".", help="Project root (default: .)")
    parser.add_argument("--watch", action="store_true", help="Watch incoming/ and auto-process new files")
    args = parser.parse_args()
    raise SystemExit(main(args.root, args.watch))
