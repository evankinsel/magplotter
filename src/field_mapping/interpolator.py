"""Spatial interpolation engine for magnetic field mapping.

Converts irregularly-sampled (X, Y, B) data onto a uniform rectangular grid
using scipy.interpolate.griddata.  The grid result feeds all downstream
visualization and metrics modules.

Public API:
    interpolate_to_grid(df, schema, config) -> Optional[GridResult]
    GridResult (dataclass)

Supported methods (from config["method"]):
    "nearest"   — fast, no extrapolation, recommended for very sparse data
    "linear"    — default; good balance of speed and smoothness
    "cubic"     — smoothest, requires more data points (>9 recommended)

Grid resolution is set via config["grid_resolution"] (default: 100 per axis).
Sparse datasets (< MIN_POINTS) fall back to "nearest" automatically.

Security note: operates on numerical arrays only; no file access.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .detector import FieldSchema

logger = logging.getLogger(__name__)

MIN_POINTS_CUBIC = 9
MIN_POINTS_LINEAR = 3
DEFAULT_RESOLUTION = 100
DEFAULT_METHOD = "linear"
VALID_METHODS = ("nearest", "linear", "cubic")


@dataclass
class GridResult:
    """Interpolated 2-D field map on a uniform rectangular grid."""
    # 1-D axis arrays
    xi: np.ndarray
    yi: np.ndarray
    # 2-D meshgrid (shape: ny × nx)
    XX: np.ndarray
    YY: np.ndarray
    # Interpolated field magnitude (shape: ny × nx); NaN outside convex hull
    Bi: np.ndarray
    # Optional interpolated vector components (same shape as Bi or None)
    Bxi: Optional[np.ndarray]
    Byi: Optional[np.ndarray]
    Bzi: Optional[np.ndarray]
    # Raw measurement points
    x_raw: np.ndarray
    y_raw: np.ndarray
    B_raw: np.ndarray
    # Grid metadata
    nx: int
    ny: int
    method: str
    # Quality diagnostics
    quality: dict = field(default_factory=dict)


def _resolve_B(df: pd.DataFrame, schema: FieldSchema) -> Optional[np.ndarray]:
    """Return B magnitude array, computing it from components if necessary."""
    if schema.b_col is not None:
        vals = pd.to_numeric(df[schema.b_col], errors="coerce").to_numpy(float)
        if not np.all(np.isnan(vals)):
            return vals

    if schema.has_vector:
        bx = pd.to_numeric(df[schema.bx_col], errors="coerce").to_numpy(float)
        by = pd.to_numeric(df[schema.by_col], errors="coerce").to_numpy(float)
        bz = (
            pd.to_numeric(df[schema.bz_col], errors="coerce").to_numpy(float)
            if schema.bz_col
            else np.zeros(len(bx))
        )
        return np.sqrt(bx**2 + by**2 + bz**2)

    return None


def _griddata(points: np.ndarray, values: np.ndarray, xi_grid, yi_grid, method: str) -> np.ndarray:
    """Thin wrapper around scipy.interpolate.griddata with import guard."""
    try:
        from scipy.interpolate import griddata
    except ImportError as exc:
        raise RuntimeError(
            "scipy is required for field mapping interpolation. "
            "Install it with: pip install scipy"
        ) from exc
    return griddata(points, values, (xi_grid, yi_grid), method=method)


def interpolate_to_grid(
    df: pd.DataFrame,
    schema: FieldSchema,
    config: Optional[dict] = None,
) -> Optional[GridResult]:
    """
    Interpolate scattered (X, Y, B) measurements onto a uniform grid.

    Returns None if the data is too sparse or contains only NaNs.  Logs
    quality warnings but does not raise.
    """
    if config is None:
        config = {}

    requested_method = config.get("method", DEFAULT_METHOD).lower()
    if requested_method not in VALID_METHODS:
        logger.warning("interpolator: unknown method %r — falling back to linear", requested_method)
        requested_method = DEFAULT_METHOD

    resolution = int(config.get("grid_resolution", DEFAULT_RESOLUTION))
    resolution = max(10, min(resolution, 1000))  # clamp to sane range

    x_raw = pd.to_numeric(df[schema.x_col], errors="coerce").to_numpy(float)
    y_raw = pd.to_numeric(df[schema.y_col], errors="coerce").to_numpy(float)
    B_raw = _resolve_B(df, schema)

    if B_raw is None:
        logger.error("interpolator: could not resolve B values — aborting")
        return None

    # Strip rows where any coordinate or B is NaN/inf
    mask = np.isfinite(x_raw) & np.isfinite(y_raw) & np.isfinite(B_raw)
    x_raw, y_raw, B_raw = x_raw[mask], y_raw[mask], B_raw[mask]

    n_pts = len(x_raw)
    logger.debug("interpolator: %d valid data points after NaN removal", n_pts)

    if n_pts < MIN_POINTS_LINEAR:
        logger.warning(
            "interpolator: only %d data points — need at least %d for interpolation — skipping",
            n_pts, MIN_POINTS_LINEAR,
        )
        return None

    # Auto-downgrade method for sparse data
    method = requested_method
    if method == "cubic" and n_pts < MIN_POINTS_CUBIC:
        logger.warning(
            "interpolator: cubic requires %d+ points, have %d — falling back to linear",
            MIN_POINTS_CUBIC, n_pts,
        )
        method = "linear"

    # Build uniform grid
    xi = np.linspace(x_raw.min(), x_raw.max(), resolution)
    yi = np.linspace(y_raw.min(), y_raw.max(), resolution)
    XX, YY = np.meshgrid(xi, yi)

    logger.info(
        "interpolator: %s interpolation — grid %dx%d, extent X=[%.2f, %.2f] Y=[%.2f, %.2f]",
        method, resolution, resolution,
        x_raw.min(), x_raw.max(), y_raw.min(), y_raw.max(),
    )

    points = np.column_stack([x_raw, y_raw])
    Bi = _griddata(points, B_raw, XX, YY, method)

    nan_frac = float(np.isnan(Bi).mean())
    logger.debug("interpolator: NaN fraction in grid = %.1f%%", nan_frac * 100)
    if nan_frac > 0.5:
        logger.warning(
            "interpolator: %.0f%% of grid is NaN — data may be too sparse or clustered",
            nan_frac * 100,
        )

    # Interpolate vector components when available
    Bxi = Byi = Bzi = None
    if schema.has_vector:
        bx_raw = pd.to_numeric(df[schema.bx_col], errors="coerce").to_numpy(float)[mask]
        by_raw = pd.to_numeric(df[schema.by_col], errors="coerce").to_numpy(float)[mask]
        Bxi = _griddata(points, bx_raw, XX, YY, method)
        Byi = _griddata(points, by_raw, XX, YY, method)
        if schema.bz_col:
            bz_raw = pd.to_numeric(df[schema.bz_col], errors="coerce").to_numpy(float)[mask]
            Bzi = _griddata(points, bz_raw, XX, YY, method)

    quality = {
        "n_input_points": int(n_pts),
        "n_valid_after_filter": int(n_pts),
        "grid_resolution": resolution,
        "requested_method": requested_method,
        "actual_method": method,
        "nan_fraction": round(nan_frac, 4),
        "x_range": [float(x_raw.min()), float(x_raw.max())],
        "y_range": [float(y_raw.min()), float(y_raw.max())],
    }
    logger.info("interpolator: grid ready — %s", quality)

    return GridResult(
        xi=xi, yi=yi, XX=XX, YY=YY,
        Bi=Bi, Bxi=Bxi, Byi=Byi, Bzi=Bzi,
        x_raw=x_raw, y_raw=y_raw, B_raw=B_raw,
        nx=resolution, ny=resolution,
        method=method,
        quality=quality,
    )
