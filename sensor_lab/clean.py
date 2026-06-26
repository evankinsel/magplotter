"""
CSV cleaning utilities: parse messy CSVs, extract numeric rows, and return a pandas DataFrame with columns:
time, mx, my, mz, [heading — when reported by the sensor]

Robust to logs, corrupted rows, comments, missing metadata, alternate column names,
rows where all values are wrapped in a single outer quoted field, and
key:value pair formats (e.g. "13:26:05.144 -> X:-12.3 Y:4.5 Z:-6.7 Heading:120.0 Row:0").

Functions:
    parse_raw_csv(path, comment_prefixes=("#","//")) -> (DataFrame, header_comments)
    validate_sensor_df(df) -> None   raises SchemaValidationError on invalid schema

Security note: this module performs defensive parsing and treats all
input as untrusted. It only converts recognised fields to floats and
skips any non-numeric or malformed rows; it will not evaluate or execute
file contents.
"""
import csv
import logging
import re
from types import MappingProxyType
from typing import Mapping, Tuple, List

import pandas as pd

logger = logging.getLogger(__name__)


class SchemaValidationError(ValueError):
    """Raised when a parsed DataFrame is missing required sensor columns or has invalid types."""


# All four columns are required after ingestion. time is always synthesised by the
# parser (row index if not present in the source), so its absence here means the
# file yielded zero parseable rows.
REQUIRED_SENSOR_COLUMNS = frozenset({"time", "mx", "my", "mz"})


def validate_sensor_df(df: pd.DataFrame) -> None:
    """
    Validate that df satisfies the sensor schema contract.

    Raises SchemaValidationError on any of:
    - DataFrame is completely empty (no rows and no columns)
    - One or more of time / mx / my / mz is absent
    - A required column is non-numeric
    - A required column is entirely NaN
    - No row has complete (non-NaN) values across all required columns
    """
    if df.empty and len(df.columns) == 0:
        raise SchemaValidationError(
            "No sensor data was parsed — the DataFrame has no rows or columns. "
            "Verify the CSV contains numeric magnetometer readings (mx/my/mz or equivalent)."
        )

    missing = REQUIRED_SENSOR_COLUMNS - set(df.columns)
    if missing:
        raise SchemaValidationError(
            f"Required sensor column(s) missing after ingestion: {sorted(missing)}. "
            f"Columns present: {sorted(df.columns.tolist())}. "
            "Expected columns: time, mx (Bx), my (By), mz (Bz)."
        )

    for col in REQUIRED_SENSOR_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            sample = df[col].dropna().head(3).tolist()
            raise SchemaValidationError(
                f"Column '{col}' must be numeric but contains non-numeric values: {sample}. "
                "Ensure all sensor columns are floating-point values."
            )
        if df[col].isna().all():
            raise SchemaValidationError(
                f"Column '{col}' is entirely NaN — no valid sensor readings found. "
                "Check the input CSV for corrupt or missing data in this column."
            )

    complete_rows = df[sorted(REQUIRED_SENSOR_COLUMNS)].dropna().shape[0]
    if complete_rows == 0:
        raise SchemaValidationError(
            "No rows with complete sensor readings found. "
            "Every row has at least one NaN across time/mx/my/mz after parsing. "
            "Check the input CSV for structural issues."
        )


# Maps common column name variants to canonical names used by the rest of the pipeline.
# Wrapped in MappingProxyType so module-level mutation is caught at runtime rather than
# silently altering alias resolution for all subsequent parse calls.
COLUMN_ALIASES: Mapping[str, str] = MappingProxyType({
    "time": "time", "t": "time", "timestamp": "time", "sample": "time", "idx": "time",
    "mx": "mx", "x": "mx", "bx": "mx", "mag_x": "mx", "field_x": "mx", "x_nt": "mx",
    "my": "my", "y": "my", "by": "my", "mag_y": "my", "field_y": "my", "y_nt": "my",
    "mz": "mz", "z": "mz", "bz": "mz", "mag_z": "mz", "field_z": "mz", "z_nt": "mz",
    "heading": "heading", "hdg": "heading", "azimuth": "heading",
    "yaw": "heading", "compass": "heading", "bearing": "heading",
})

# key:value pairs — key starts with a letter/underscore, value is a signed float/int
_KV_RE = re.compile(r"\b([A-Za-z_]\w*):\s*([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)")
# wall-clock timestamp HH:MM:SS[.fractional]
_WALL_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?\b")


def _wall_time_to_sec(line: str) -> "float | None":
    """Return seconds-since-midnight for the first HH:MM:SS[.sss] token in line, or None."""
    m = _WALL_TIME_RE.search(line)
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    frac = float("0." + m.group(4)) if m.group(4) else 0.0
    return h * 3600 + mi * 60 + s + frac


def _extract_kv(line: str) -> dict:
    """
    Extract key:value pairs from a line using COLUMN_ALIASES for name resolution.
    Unrecognised keys (e.g. Row) and the 'time' alias are silently ignored —
    time is handled separately via the wall-clock timestamp in the line.
    Returns a dict of {canonical_name: float}.
    """
    result = {}
    for key, val_str in _KV_RE.findall(line):
        canonical = COLUMN_ALIASES.get(key.lower())
        if canonical and canonical != "time":
            try:
                result[canonical] = float(val_str)
            except ValueError:
                pass
    return result


def parse_raw_csv(path: str, comment_prefixes=("#", "//")) -> Tuple[pd.DataFrame, List[str]]:
    """
    Open a CSV that may contain startup logs or comment lines.
    Returns (clean_df, header_comments)
    - clean_df: DataFrame with float columns time, mx, my, mz (and optionally heading)
    - header_comments: list of comment lines found before data (kept as notes)

    Parsing strategy (tried in order, first match wins):
    1. Unwrap quoted rows: if csv.reader returns a single field whose contents
       contain commas or tabs (e.g. each row is stored as "0.01,12.4,-5.2,9.8"),
       re-parse the inner string so downstream logic sees individual fields.
    2. Detect header rows: if the first non-comment row contains non-numeric text
       in all fields, treat it as a header and build a column alias map so
       alternate names (x/y/z, bx/by/bz, mag_x/mag_y/mag_z, etc.) are accepted.
    3. Strict parse: attempt to convert the first four fields directly to floats.
    4. Key:value extraction: look for key:value pairs (e.g. X:-12.3 Y:4.5 Z:-6.7
       Heading:120.0) using COLUMN_ALIASES. Wall-clock timestamps (HH:MM:SS[.sss])
       are converted to seconds relative to the first such timestamp seen.
       Unrecognised keys such as Row are ignored. The heading column is included
       when present.
    5. Flexible fallback: flatten the row, strip timestamps, tokenize on any
       separator, collect numeric tokens, and interpret as:
         - 4+ tokens -> time, mx, my, mz
         - 3 tokens  -> synthesized index as time, mx, my, mz
         - <3 tokens -> skip row
    """
    logger.info("parsing: %s", path)
    header_comments: List[str] = []
    rows: List[dict] = []
    t0_abs: "float | None" = None  # first wall-clock time seen (seconds since midnight)

    # Matches floats, ints, and scientific notation (signed allowed)
    numeric_re = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$")
    # Timestamps like HH:MM or HH:MM:SS -> strip before tokenizing in flexible path
    timestamp_re = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")

    # Populated if/when a header row is detected; maps canonical name -> column index
    header_map: "dict | None" = None
    skipped_rows = 0

    def _unwrap_if_single_quoted_field(parsed: List[str]) -> List[str]:
        if len(parsed) == 1:
            inner = parsed[0].strip()
            if "," in inner or "\t" in inner:
                try:
                    return next(csv.reader([inner]))
                except Exception:
                    pass
        return parsed

    def _try_strict(fields: List[str]) -> "dict | None":
        if len(fields) >= 4:
            try:
                return {
                    "time": float(fields[0]),
                    "mx":   float(fields[1]),
                    "my":   float(fields[2]),
                    "mz":   float(fields[3]),
                }
            except (ValueError, TypeError):
                pass
        return None

    def _flexible_extract(parsed: List[str], raw_line: str) -> List[float]:
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

            parsed = _unwrap_if_single_quoted_field(parsed)

            if header_map is None:
                non_empty = [f.strip() for f in parsed if f.strip()]
                all_text = non_empty and all(not numeric_re.fullmatch(f) for f in non_empty)
                if all_text and len(non_empty) >= 3:
                    header_map = {}
                    for i, col in enumerate(parsed):
                        canonical = COLUMN_ALIASES.get(col.strip().lower())
                        if canonical:
                            header_map[canonical] = i
                    logger.debug("header row detected: %s", [c.strip() for c in parsed])
                    continue

            result = _try_strict(parsed)
            if result:
                rows.append(result)
                continue

            # Key:value extraction (e.g. "13:26:05.144 -> X:-2131.35 Y:-3968.25 Z:-1349.39 Heading:241.76 Row:0")
            kv = _extract_kv(line)
            if {"mx", "my", "mz"}.issubset(kv):
                abs_t = _wall_time_to_sec(line)
                if abs_t is not None:
                    if t0_abs is None:
                        t0_abs = abs_t
                    kv["time"] = abs_t - t0_abs
                else:
                    kv.setdefault("time", float(len(rows)))
                rows.append(kv)
                continue

            nums = _flexible_extract(parsed, line)
            if len(nums) >= 4:
                rows.append({"time": nums[0], "mx": nums[1], "my": nums[2], "mz": nums[3]})
            elif len(nums) == 3:
                rows.append({"time": float(len(rows)), "mx": nums[0], "my": nums[1], "mz": nums[2]})
            else:
                skipped_rows += 1

    if skipped_rows:
        logger.debug("skipped %d unparseable row(s) in %s", skipped_rows, path)

    df = pd.DataFrame(rows)
    if not df.empty:
        for col in ("time", "mx", "my", "mz"):
            if col not in df.columns:
                df[col] = float("nan")
        df = df.sort_values("time").reset_index(drop=True)

    # Fallback: some CSVs use ISO timestamp strings with named columns
    if df.empty:
        logger.info("numeric parse yielded no rows — trying ISO timestamp fallback for %s", path)
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
                        df = df.dropna().sort_values("time").reset_index(drop=True)
                        logger.info("ISO timestamp fallback succeeded: %d rows from %s", len(df), path)
                except Exception:
                    logger.exception("ISO timestamp fallback failed for %s", path)

    # Strict schema gate — raises SchemaValidationError on missing/bad columns.
    validate_sensor_df(df)
    logger.info("extracted %d rows from %s", len(df), path)
    return df, header_comments
