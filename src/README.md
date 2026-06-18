Support utilities and report generation

The `src` package holds small helper modules used by the CLI and processing pipeline.

- `file_manager.py` — filesystem helpers (ensure directories, list CSV files).
- `report_generator.py` — write a human-readable `report.txt` from the JSON summary produced by `processor.py`.

These modules are deliberately lightweight and meant to be easy to reuse in other scripts.
