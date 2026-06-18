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
import sys
from pathlib import Path
from sensor_lab.processor import process_file

if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    incoming = base / "incoming"
    if not incoming.exists():
        print(f"No incoming directory at {incoming}")
        sys.exit(1)
    for p in incoming.iterdir():
        if p.is_file() and p.suffix.lower() == ".csv":
            print("Processing", p)
            summary = process_file(str(p), base_dir=str(base))
            print("Saved summary for", p.name)
