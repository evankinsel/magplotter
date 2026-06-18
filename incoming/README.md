Incoming data folder

Drop raw CSV files here for processing by MagPlotter. Files should have a `.csv` extension and contain at minimum the columns: `time,mx,my,mz`.

Examples:

```
incoming/experiment_001.csv
incoming/experiment_002.csv
```

Tip: you can place a `*.txt` notes file next to a CSV to attach human notes to the run (the processor will include this in the `summary.json`).
