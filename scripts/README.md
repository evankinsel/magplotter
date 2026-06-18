Helper scripts for running and supervising MagPlotter

This folder contains convenience scripts meant for local development and simple deployments.

- `start-watcher.sh`: launches the watcher loop (`python main.py --watch`) and logs output to `logs/watcher.log`. It will auto-restart the watcher if it exits unexpectedly.

Usage:

```
bash scripts/start-watcher.sh
```

Adjust paths or add system service wrappers for production usage.
