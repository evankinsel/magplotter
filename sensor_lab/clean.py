"""
CSV cleaning utilities: parse messy CSVs, extract numeric rows, and return a pandas DataFrame with columns:
time, mx, my, mz

Robust to logs, corrupted rows, comments, and missing metadata.
"""
from typing import Tuple, List
import csv
import io
import numpy as np
import pandas as pd


def parse_raw_csv(path: str, comment_prefixes=("#", "//")) -> Tuple[pd.DataFrame, List[str]]:
    """
    Open a CSV that may contain startup logs or comment lines.
    Returns (clean_df, header_comments)
    - clean_df: DataFrame with float columns time, mx, my, mz (may be empty)
    - header_comments: list of comment lines found before data (kept as notes)
    """
    header_comments = []
    rows = []
    with open(path, "r", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if any(stripped.startswith(pref) for pref in comment_prefixes):
                header_comments.append(stripped)
                continue
            # try to parse CSV fields
            # handle files where header may appear: "time,mx,my,mz"
            # use csv.reader on that line only to be robust to commas inside logs
            try:
                parsed = next(csv.reader([line]))
            except Exception:
                continue
            # Accept rows that have at least 4 columns and are numeric for first 4
            if len(parsed) < 4:
                # may contain lines like "BNO starting" -> skip
                continue
            # try convert first four to floats
            try:
                t, mx, my, mz = parsed[0:4]
                t_f = float(t)
                mx_f = float(mx)
                my_f = float(my)
                mz_f = float(mz)
                rows.append((t_f, mx_f, my_f, mz_f))
            except Exception:
                # non-numeric row (malformed) -> skip gracefully
                continue
    df = pd.DataFrame(rows, columns=["time", "mx", "my", "mz"])
    # If times are not strictly increasing or not starting at zero, keep as-is; user experiments vary
    # sort by time in case device logs scrambled
    if not df.empty:
        df = df.sort_values("time").reset_index(drop=True)
    return df, header_comments
