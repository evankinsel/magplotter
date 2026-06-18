"""
CSV cleaning utilities: parse messy CSVs, extract numeric rows, and return a pandas DataFrame with columns:
time, mx, my, mz

Robust to logs, corrupted rows, comments, missing metadata, alternate column names,
and rows where all values are wrapped in a single outer quoted field.

Functions:
    parse_raw_csv(path, comment_prefixes=("#","//")) -> (DataFrame, header_comments)

Security note: this module performs defensive parsing and treats all
input as untrusted. It only converts the first four fields to floats and
skips any non-numeric or malformed rows; it will not evaluate or execute
file contents.
"""
from typing import Tuple, List
import csv
import re
import pandas as pd


# Maps common column name variants to canonical names used by the rest of the pipeline.
# Add more aliases here as new sensor formats are encountered.
COLUMN_ALIASES = {
    "time": "time", "t": "time", "timestamp": "time", "sample": "time", "idx": "time",
    "mx": "mx", "x": "mx", "bx": "mx", "mag_x": "mx", "field_x": "mx", "x_nt": "mx",
    "my": "my", "y": "my", "by": "my", "mag_y": "my", "field_y": "my", "y_nt": "my",
    "mz": "mz", "z": "mz", "bz": "mz", "mag_z": "mz", "field_z": "mz", "z_nt": "mz",
}


def parse_raw_csv(path: str, comment_prefixes=("#", "//")) -> Tuple[pd.DataFrame, List[str]]:
    """
    Open a CSV that may contain startup logs or comment lines.
    Returns (clean_df, header_comments)
    - clean_df: DataFrame with float columns time, mx, my, mz (may be empty)
    - header_comments: list of comment lines found before data (kept as notes)

    Parsing strategy:
    1. Unwrap quoted rows: if csv.reader returns a single field whose contents
       contain commas or tabs (e.g. each row is stored as "0.01,12.4,-5.2,9.8"),
       re-parse the inner string so downstream logic sees individual fields.
    2. Detect header rows: if the first non-comment row contains non-numeric text
       in all fields, treat it as a header and build a column alias map so
       alternate names (x/y/z, bx/by/bz, mag_x/mag_y/mag_z, etc.) are accepted.
    3. Strict parse: attempt to convert the first four fields directly to floats.
    4. Flexible fallback: flatten the row, strip timestamps, tokenize on any
       separator, collect numeric tokens, and interpret as:
         - 4+ tokens -> time, x, y, z
         - 3 tokens  -> synthesized index as time, x, y, z
         - <3 tokens -> skip row
    """
    header_comments: List[str] = []
    rows: List[Tuple[float, float, float, float]] = []

    # Matches floats, ints, and scientific notation (signed allowed)
    numeric_re = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
    # Timestamps like HH:MM or HH:MM:SS -> strip before tokenizing
    timestamp_re = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")

    # Populated if/when a header row is detected; maps canonical name -> column index
    header_map: dict | None = None

    def _unwrap_if_single_quoted_field(parsed: List[str]) -> List[str]:
        """
        If csv.reader returned exactly one field and that field contains
        commas or tabs, the entire row was probably quoted as a single value.
        Re-parse the inner content to recover individual columns.
        """
        if len(parsed) == 1:
            inner = parsed[0].strip()
            if "," in inner or "\t" in inner:
                try:
                    return next(csv.reader([inner]))
                except Exception:
                    pass
        return parsed

    def _try_strict(fields: List[str]) -> Tuple[float, float, float, float] | None:
        """Try to read the first four fields as (time, mx, my, mz). Returns None on failure."""
        if len(fields) >= 4:
            try:
                return (float(fields[0]), float(fields[1]), float(fields[2]), float(fields[3]))
            except (ValueError, TypeError):
                pass
        return None

    def _flexible_extract(parsed: List[str], raw_line: str) -> List[float]:
        """Flatten, strip timestamps, tokenize, and return all numeric tokens found."""
        flat = " ".join(parsed) if parsed else raw_line
        flat = timestamp_re.sub(" ", flat)
        tokens = re.split(r"[,\t;|]+|\s+", flat.strip())
        nums: List[float] = []
        for tok in tokens:
            if tok and numeric_re.fullmatch(tok):
                try:
                    nums.append(float(tok))
                except Exception:
                    continue
        return nums

    with open(path, "r", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if any(stripped.startswith(pref) for pref in comment_prefixes):
                header_comments.append(stripped)
                continue

            try:
                parsed = next(csv.reader([line]))
            except Exception:
                parsed = [line]

            # Step 1: unwrap single-field quoted rows
            parsed = _unwrap_if_single_quoted_field(parsed)

            # Step 2: header detection (only on first non-comment row if no header yet)
            if header_map is None:
                non_empty = [f.strip() for f in parsed if f.strip()]
                all_text = non_empty and all(not numeric_re.fullmatch(f) for f in non_empty)
                if all_text and len(non_empty) >= 3:
                    header_map = {}
                    for i, col in enumerate(parsed):
                        canonical = COLUMN_ALIASES.get(col.strip().lower())
                        if canonical:
                            header_map[canonical] = i
                    continue  # this row is a header, not data

            # Step 3: strict parse
            result = _try_strict(parsed)
            if result:
                rows.append(result)
                continue

            # Step 4: flexible fallback
            nums = _flexible_extract(parsed, line)
            if len(nums) >= 4:
                rows.append((nums[0], nums[1], nums[2], nums[3]))
            elif len(nums) == 3:
                # No explicit time: synthesize a monotonically increasing sample index
                rows.append((float(len(rows)), nums[0], nums[1], nums[2]))
            # else: fewer than 3 numeric values -> skip row

    df = pd.DataFrame(rows, columns=["time", "mx", "my", "mz"])
    if not df.empty:
        df = df.sort_values("time").reset_index(drop=True)

    # Fallback: some CSVs use ISO timestamp strings (e.g. "2026-01-01T12:00:00") with
    # named columns like timestamp,x_nt,y_nt,z_nt. If the numeric parse produced no rows,
    # try a pandas-based parse that converts timestamps to seconds from first sample.
    if df.empty:
        try:
            df_raw = pd.read_csv(path, comment=list(comment_prefixes)[0])
        except Exception:
            df_raw = None

        if df_raw is not None and not df_raw.empty:
            cols_lower = {c.lower(): c for c in df_raw.columns}
            time_col = None
            for candidate in ("time", "timestamp", "date", "datetime"):
                if candidate in cols_lower:
                    time_col = cols_lower[candidate]
                    break

            axis_map = {}
            for candidate, key in [("mx", "mx"), ("my", "my"), ("mz", "mz"),
                                   ("x_nt", "mx"), ("y_nt", "my"), ("z_nt", "mz")]:
                if candidate in cols_lower:
                    axis_map[key] = cols_lower[candidate]

            if time_col is not None and all(k in axis_map for k in ("mx", "my", "mz")):
                try:
                    times = pd.to_datetime(df_raw[time_col], errors="coerce")
                    if times.isna().all():
                        times = pd.to_datetime(df_raw[time_col].astype(str).str.strip(), errors="coerce")
                    if not times.isna().all():
                        t0 = times.dropna().iloc[0]
                        time_seconds = (times - t0).dt.total_seconds().astype(float)
                        mx = pd.to_numeric(df_raw[axis_map["mx"]], errors="coerce")
                        my = pd.to_numeric(df_raw[axis_map["my"]], errors="coerce")
                        mz = pd.to_numeric(df_raw[axis_map["mz"]], errors="coerce")
                        df = pd.DataFrame({"time": time_seconds, "mx": mx, "my": my, "mz": mz})
                        df = df.dropna().reset_index(drop=True)
                except Exception:
                    pass

    return df, header_comments
