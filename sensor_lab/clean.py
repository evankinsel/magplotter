"""
CSV cleaning utilities: parse messy CSVs, extract numeric rows, and return a pandas DataFrame with columns:
time, mx, my, mz

Robust to logs, corrupted rows, comments, and missing metadata.

Functions:
    parse_raw_csv(path, comment_prefixes=("#","//")) -> (DataFrame, header_comments)

Security note: this module performs defensive parsing and treats all
input as untrusted. It only converts the first four fields to floats and
skips any non-numeric or malformed rows; it will not evaluate or execute
file contents.
"""
from typing import Tuple, List
import csv
import io
import re
import numpy as np
import pandas as pd


def parse_raw_csv(path: str, comment_prefixes=("#", "//")) -> Tuple[pd.DataFrame, List[str]]:
    """
    Open a CSV that may contain startup logs or comment lines.
    Returns (clean_df, header_comments)
    - clean_df: DataFrame with float columns time, mx, my, mz (may be empty)
    - header_comments: list of comment lines found before data (kept as notes)
    
    Parsing strategy:
    1. Try the strict parser: use csv.reader and attempt to convert the first
       four fields of each row to floats (time, mx, my, mz). This preserves
       behavior for well-formed files.
    2. If the strict parse fails for a row, fall back to a flexible regex-based
       numeric extractor. Flatten the row into a string, split on common
       separators, filter tokens using a float-safe regex, and collect numeric
       tokens.
       - If the row yields 4+ numeric tokens: interpret them as time, x, y, z
       - If the row yields exactly 3 numeric tokens: interpret them as x, y, z
         and synthesize a sample index as the "time" value (so output always
         has four columns suitable for plotting).
       - Otherwise skip the row.
    """
    header_comments = []
    rows = []

    # precompile regexes for performance
    # matches floats, integers, and scientific notation (signed allowed)
    numeric_re = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
    # timestamps like HH:MM or HH:MM:SS -> remove these before tokenizing
    timestamp_re = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")

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
                # if csv.reader can't parse the line at all, fallback to raw line tokenization
                parsed = [line]

            # Accept rows that have at least 4 columns and are numeric for first 4
            if len(parsed) >= 4:
                # try convert first four to floats (strict path)
                try:
                    t, mx, my, mz = parsed[0:4]
                    t_f = float(t)
                    mx_f = float(mx)
                    my_f = float(my)
                    mz_f = float(mz)
                    rows.append((t_f, mx_f, my_f, mz_f))
                    continue
                except Exception:
                    # fall through to flexible parsing below
                    pass

            # FLEXIBLE FALLBACK PARSING
            # Flatten the parsed fields into a single string so we can handle
            # coordinates that appear in a single cell ("123, 456, 789"),
            # space/tab-separated values, or mixed rows with extra text.
            flat = " ".join(parsed) if parsed else line

            # remove obvious timestamps so their numeric parts aren't confused
            flat = timestamp_re.sub(" ", flat)

            # split on common separators: commas, tabs, semicolons, pipes, or whitespace
            tokens = re.split(r"[,\t;|]+|\s+", flat.strip())

            nums = []
            for tok in tokens:
                if not tok:
                    continue
                # only accept tokens that are purely numeric (per numeric_re)
                if numeric_re.fullmatch(tok):
                    try:
                        nums.append(float(tok))
                    except Exception:
                        # If conversion fails for any reason, ignore token
                        continue

            # Decide how to interpret the numeric tokens found
            if len(nums) >= 4:
                # treat as: time, x, y, z (extra numbers ignored)
                t_f, mx_f, my_f, mz_f = nums[0], nums[1], nums[2], nums[3]
                rows.append((float(t_f), float(mx_f), float(my_f), float(mz_f)))
            elif len(nums) == 3:
                # no explicit time found: synthesize a monotonically increasing
                # sample index as the time so output shape remains consistent
                t_f = float(len(rows))
                mx_f, my_f, mz_f = nums[0], nums[1], nums[2]
                rows.append((t_f, float(mx_f), float(my_f), float(mz_f)))
            else:
                # fewer than 3 numeric values -> skip row
                continue

    df = pd.DataFrame(rows, columns=["time", "mx", "my", "mz"])
    # If times are not strictly increasing or not starting at zero, keep as-is; user experiments vary
    # sort by time in case device logs scrambled
    if not df.empty:
        df = df.sort_values("time").reset_index(drop=True)
    return df, header_comments
