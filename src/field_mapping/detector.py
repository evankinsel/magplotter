"""Coordinate and field column detector for magnetic field mapping CSVs.

Identifies spatial coordinate columns (X, Y, Z) and magnetic field columns
(B magnitude and/or Bx, By, Bz components) from a DataFrame using
priority-ordered regex pattern matching.

Public API:
    detect_coordinates(df: pd.DataFrame) -> Optional[FieldSchema]
    FieldSchema (dataclass)

Supported naming conventions (case-insensitive):
    Spatial X: x, X, pos_x, position_x, x_mm, x_cm, x_m, x_pos, col_x, posx
    Spatial Y: y, Y, pos_y, position_y, y_mm, y_cm, y_m, y_pos, col_y, posy
    Spatial Z: z, Z, pos_z, position_z, z_mm, z_cm, z_m, z_pos, col_z, posz
    Magnitude: B, Bmag, b_mag, magnitude, field_strength, b_total, |B|
    Components: Bx, By, Bz, b_x, b_y, b_z, field_x, field_y, field_z

Returns None and logs a warning when detection fails — never raises.
"""
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Spatial coordinate patterns, ordered by detection confidence (high → low).
# Unit-suffixed names (x_mm) are more explicit than bare names (x).
_X_PATTERNS: List[str] = [
    r"^x_?(mm|cm|m|um|in|ft)$",
    r"^pos_?x$", r"^position_?x$",
    r"^x_?pos(ition)?$",
    r"^col_?x$", r"^posx$", r"^xpos$",
    r"^x$",
]
_Y_PATTERNS: List[str] = [
    r"^y_?(mm|cm|m|um|in|ft)$",
    r"^pos_?y$", r"^position_?y$",
    r"^y_?pos(ition)?$",
    r"^col_?y$", r"^posy$", r"^ypos$",
    r"^y$",
]
_Z_PATTERNS: List[str] = [
    r"^z_?(mm|cm|m|um|in|ft)$",
    r"^pos_?z$", r"^position_?z$",
    r"^z_?pos(ition)?$",
    r"^col_?z$", r"^posz$", r"^zpos$",
    r"^z$",
]

# Field magnitude patterns (B-scalar).
_B_PATTERNS: List[str] = [
    r"^bmag(nitude)?$",
    r"^b_?mag(nitude)?$",
    r"^b_?total$",
    r"^field_?str(ength)?$",
    r"^b_?(ut|nt|t|gauss|g|tesla)$",
    r"^\|?b\|?$",
    r"^magnitude(_?b)?$",
    r"^field$",
    r"^b$",
]

# Field component patterns (Bx, By, Bz — explicit B naming).
_BX_PATTERNS: List[str] = [
    r"^bx$", r"^b_?x$",
    r"^field_?x$",
    r"^bx_?(ut|nt|t|gauss|g)$",
    r"^b_?x_?(ut|nt|t|gauss|g)$",
]
_BY_PATTERNS: List[str] = [
    r"^by$", r"^b_?y$",
    r"^field_?y$",
    r"^by_?(ut|nt|t|gauss|g)$",
    r"^b_?y_?(ut|nt|t|gauss|g)$",
]
_BZ_PATTERNS: List[str] = [
    r"^bz$", r"^b_?z$",
    r"^field_?z$",
    r"^bz_?(ut|nt|t|gauss|g)$",
    r"^b_?z_?(ut|nt|t|gauss|g)$",
]

# mx/my/mz aliases — used as fallback when spatial columns are already found.
_MX_PATTERNS: List[str] = [r"^mx$", r"^mag_?x$"]
_MY_PATTERNS: List[str] = [r"^my$", r"^mag_?y$"]
_MZ_PATTERNS: List[str] = [r"^mz$", r"^mag_?z$"]


@dataclass
class FieldSchema:
    """Detected column layout for a field mapping dataset."""
    x_col: str
    y_col: str
    z_col: Optional[str]      # None → 2-D mapping
    b_col: Optional[str]      # magnitude column, if present
    bx_col: Optional[str]
    by_col: Optional[str]
    bz_col: Optional[str]
    is_3d: bool
    has_vector: bool           # True when bx_col and by_col are both found
    units: Optional[str]       # position units inferred from column name


def _find_col(col_map: Dict[str, str], patterns: List[str]) -> Optional[str]:
    """Return the first original column name that matches any pattern (priority order)."""
    for pattern in patterns:
        for col_lower, col_orig in col_map.items():
            if re.fullmatch(pattern, col_lower):
                return col_orig
    return None


def _infer_units(col_name: str) -> Optional[str]:
    m = re.search(r"_(mm|cm|m|um|in|ft)$", col_name.lower())
    return m.group(1) if m else None


def detect_coordinates(df: pd.DataFrame) -> Optional[FieldSchema]:
    """
    Inspect DataFrame columns and return a FieldSchema when both spatial and
    field columns are identified.  Returns None and logs a warning otherwise.

    This function never raises; callers can skip field mapping on None return.
    """
    if df.empty:
        logger.debug("detector: empty DataFrame — skipping field mapping")
        return None

    col_map: Dict[str, str] = {c.strip().lower(): c for c in df.columns}
    logger.debug("detector: scanning %d columns: %s", len(df.columns), list(df.columns))

    x_col = _find_col(col_map, _X_PATTERNS)
    y_col = _find_col(col_map, _Y_PATTERNS)

    if x_col is None or y_col is None:
        logger.warning(
            "detector: could not identify X and Y spatial columns in %s — skipping field mapping",
            list(df.columns),
        )
        return None

    z_col = _find_col(col_map, _Z_PATTERNS)

    b_col = _find_col(col_map, _B_PATTERNS)
    bx_col = _find_col(col_map, _BX_PATTERNS)
    by_col = _find_col(col_map, _BY_PATTERNS)
    bz_col = _find_col(col_map, _BZ_PATTERNS)

    # Fallback: if no explicit Bx/By found, try mx/my as field components.
    if bx_col is None and by_col is None:
        mx_col = _find_col(col_map, _MX_PATTERNS)
        my_col = _find_col(col_map, _MY_PATTERNS)
        mz_col = _find_col(col_map, _MZ_PATTERNS)
        if mx_col and my_col:
            bx_col, by_col, bz_col = mx_col, my_col, mz_col
            logger.debug("detector: using mx/my/mz as field component columns")

    if b_col is None and (bx_col is None or by_col is None):
        logger.warning(
            "detector: spatial columns found (%s, %s) but no usable field columns — skipping field mapping",
            x_col, y_col,
        )
        return None

    units = _infer_units(x_col) or _infer_units(y_col)
    schema = FieldSchema(
        x_col=x_col, y_col=y_col, z_col=z_col,
        b_col=b_col, bx_col=bx_col, by_col=by_col, bz_col=bz_col,
        is_3d=(z_col is not None),
        has_vector=(bx_col is not None and by_col is not None),
        units=units,
    )
    logger.info(
        "detector: schema — x=%s, y=%s, z=%s, B=%s, Bx=%s, By=%s, Bz=%s, 3D=%s",
        x_col, y_col, z_col, b_col, bx_col, by_col, bz_col, schema.is_3d,
    )
    return schema
