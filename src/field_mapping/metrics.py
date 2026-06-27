"""Engineering-grade magnetic field characterization metrics.

Computes scalar and spatial statistics from an interpolated field map and
saves them to field_metrics.json.

Public API:
    compute_field_metrics(grid, schema) -> dict

Computed metrics:
    Peak / average / minimum field strength and locations
    Field uniformity (coefficient of variation)
    Standard deviation
    Gradient magnitude statistics (max, mean, map)
    Magnetic center (B-weighted centroid)
    Hot spot location (peak field coordinate)
    Spatial variance
    Field distribution histogram (20 bins)
    Uniform region area fraction
    Field symmetry estimate
    Radial falloff profile
    Field coverage area
    Advanced gradient statistics

All values serialised as plain Python types for JSON compatibility.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .detector import FieldSchema
from .interpolator import GridResult

logger = logging.getLogger(__name__)

_HISTOGRAM_BINS = 20
_UNIFORM_STD_FACTOR = 1.0   # region where |B| > (mean - 1·std)


def _nanfinite(arr: np.ndarray) -> np.ndarray:
    return arr[np.isfinite(arr)]


def _grid_spacing(grid: GridResult) -> Tuple[float, float]:
    dx = float(grid.xi[1] - grid.xi[0]) if len(grid.xi) > 1 else 1.0
    dy = float(grid.yi[1] - grid.yi[0]) if len(grid.yi) > 1 else 1.0
    return dx, dy


def _gradient_magnitude(grid: GridResult) -> Optional[np.ndarray]:
    """Return gradient magnitude map of the same shape as grid.Bi."""
    dx, dy = _grid_spacing(grid)
    Bi_filled = np.where(np.isnan(grid.Bi), np.nanmean(grid.Bi), grid.Bi)
    try:
        gy, gx = np.gradient(Bi_filled, dy, dx)
        return np.sqrt(gx**2 + gy**2)
    except Exception as exc:
        logger.warning("metrics: gradient computation failed — %s", exc)
        return None


def _weighted_centroid(grid: GridResult) -> Tuple[Optional[float], Optional[float]]:
    """B-weighted centroid (magnetic center)."""
    Bi = grid.Bi.copy()
    Bi[~np.isfinite(Bi)] = 0.0
    total = Bi.sum()
    if total == 0:
        return None, None
    cx = float((grid.XX * Bi).sum() / total)
    cy = float((grid.YY * Bi).sum() / total)
    return cx, cy


def _radial_profile(
    grid: GridResult, cx: float, cy: float, n_bins: int = 20
) -> List[Dict[str, Any]]:
    """Mean |B| binned by distance from the magnetic center.

    Uses np.digitize + np.bincount to assign all cells to bins in one pass
    instead of iterating over each bin with a boolean mask.
    """
    R = np.sqrt((grid.XX - cx) ** 2 + (grid.YY - cy) ** 2)
    valid = np.isfinite(grid.Bi)
    if not valid.any():
        return []
    r_max = float(R[valid].max())
    if r_max == 0:
        return []

    bins = np.linspace(0, r_max, n_bins + 1)
    bin_centers = 0.5 * (bins[:-1] + bins[1:])

    R_valid = R.ravel()[valid.ravel()]
    B_valid = grid.Bi.ravel()[valid.ravel()]

    # np.digitize returns 1-based indices; clip so the upper-edge lands in the last bin
    bin_idx = np.clip(np.digitize(R_valid, bins) - 1, 0, n_bins - 1)

    counts = np.bincount(bin_idx, minlength=n_bins)
    B_sums = np.bincount(bin_idx, weights=B_valid, minlength=n_bins)
    B_sq_sums = np.bincount(bin_idx, weights=B_valid ** 2, minlength=n_bins)

    populated = counts > 0
    means = np.where(populated, B_sums / np.where(populated, counts, 1), 0.0)
    variances = np.where(populated, B_sq_sums / np.where(populated, counts, 1) - means ** 2, 0.0)
    stds = np.sqrt(np.maximum(variances, 0.0))

    return [
        {
            "r_center": round(float(bin_centers[i]), 4),
            "B_mean": round(float(means[i]), 4),
            "B_std": round(float(stds[i]), 4),
            "n_cells": int(counts[i]),
        }
        for i in range(n_bins)
        if populated[i]
    ]


def _symmetry_score(grid: GridResult, cx: float, cy: float) -> Optional[float]:
    """
    Estimate field symmetry by comparing each cell to its 180° rotated counterpart.

    Score is in [0, 1]: 1 = perfectly symmetric, 0 = fully asymmetric.
    """
    from scipy.interpolate import RegularGridInterpolator
    try:
        Bi_filled = np.where(np.isnan(grid.Bi), np.nanmean(grid.Bi), grid.Bi)
        interp = RegularGridInterpolator(
            (grid.yi, grid.xi), Bi_filled, method="linear", bounds_error=False,
            fill_value=np.nanmean(grid.Bi),
        )
        # Mirror coordinates through the centroid
        x_mirror = 2 * cx - grid.XX
        y_mirror = 2 * cy - grid.YY
        pts_mirror = np.column_stack([
            y_mirror.ravel(), x_mirror.ravel()
        ])
        B_mirror = interp(pts_mirror).reshape(grid.Bi.shape)
        valid = np.isfinite(grid.Bi)
        if not valid.any():
            return None
        diff = np.abs(grid.Bi[valid] - B_mirror[valid])
        mean_B = np.abs(grid.Bi[valid]).mean()
        if mean_B == 0:
            return None
        return round(float(1.0 - (diff.mean() / mean_B)), 4)
    except Exception as exc:
        logger.debug("metrics: symmetry score failed — %s", exc)
        return None


def compute_field_metrics(grid: GridResult, schema: FieldSchema) -> Dict[str, Any]:
    """
    Compute the full set of engineering field characterization metrics.

    Returns a plain dict suitable for json.dump.
    """
    logger.info("metrics: computing field characterization metrics")

    valid = np.isfinite(grid.Bi)
    B_valid = grid.Bi[valid]

    if B_valid.size == 0:
        logger.warning("metrics: no valid (non-NaN) grid cells — returning empty metrics")
        return {"error": "no valid data in interpolated grid"}

    # Basic statistics
    B_peak = float(B_valid.max())
    B_mean = float(B_valid.mean())
    B_min = float(B_valid.min())
    B_std = float(B_valid.std())
    B_var = float(B_valid.var())

    # Uniformity: 100 * (1 - CV), where CV = std/mean
    uniformity_pct = round(float((1.0 - B_std / B_mean) * 100), 3) if B_mean != 0 else None

    # Hot spot (peak field location)
    flat_peak = np.nanargmax(grid.Bi)
    iy_peak, ix_peak = np.unravel_index(flat_peak, grid.Bi.shape)
    hot_spot = {
        "x": round(float(grid.XX[iy_peak, ix_peak]), 4),
        "y": round(float(grid.YY[iy_peak, ix_peak]), 4),
        "B": round(B_peak, 4),
    }

    # Minimum field location
    flat_min = np.nanargmin(grid.Bi)
    iy_min, ix_min = np.unravel_index(flat_min, grid.Bi.shape)
    cold_spot = {
        "x": round(float(grid.XX[iy_min, ix_min]), 4),
        "y": round(float(grid.YY[iy_min, ix_min]), 4),
        "B": round(B_min, 4),
    }

    # Magnetic center (B-weighted centroid)
    cx, cy = _weighted_centroid(grid)
    magnetic_center = {"x": round(cx, 4), "y": round(cy, 4)} if cx is not None else None

    # Gradient statistics
    grad_mag = _gradient_magnitude(grid)
    gradient_stats: Dict[str, Any] = {}
    if grad_mag is not None:
        g_valid = _nanfinite(grad_mag)
        if g_valid.size > 0:
            gradient_stats = {
                "max_gradient": round(float(g_valid.max()), 4),
                "mean_gradient": round(float(g_valid.mean()), 4),
                "std_gradient": round(float(g_valid.std()), 4),
            }
            # Gradient map summary (peak location)
            flat_gmax = np.nanargmax(grad_mag)
            igy, igx = np.unravel_index(flat_gmax, grad_mag.shape)
            gradient_stats["peak_gradient_location"] = {
                "x": round(float(grid.XX[igy, igx]), 4),
                "y": round(float(grid.YY[igy, igx]), 4),
            }

    # Uniform region (cells where B > mean - std_factor*std)
    threshold = B_mean - _UNIFORM_STD_FACTOR * B_std
    uniform_mask = valid & (grid.Bi >= threshold)
    uniform_fraction = round(float(uniform_mask.sum() / valid.sum()), 4) if valid.sum() else 0.0

    # Field coverage area (fraction of grid cells with valid data)
    dx, dy = _grid_spacing(grid)
    cell_area = dx * dy
    coverage_area = round(float(valid.sum() * cell_area), 4)
    total_area = round(float(grid.nx * grid.ny * cell_area), 4)
    coverage_fraction = round(float(valid.sum() / (grid.nx * grid.ny)), 4)

    # Histogram
    hist_counts, hist_edges = np.histogram(B_valid, bins=_HISTOGRAM_BINS)
    histogram = {
        "bin_edges": [round(float(e), 4) for e in hist_edges],
        "counts": [int(c) for c in hist_counts],
    }

    # Radial falloff profile
    radial_profile: List[Dict[str, Any]] = []
    if cx is not None and cy is not None:
        radial_profile = _radial_profile(grid, cx, cy)

    # Symmetry score (optional — may be slow on large grids)
    symmetry_score = None
    if cx is not None and cy is not None:
        symmetry_score = _symmetry_score(grid, cx, cy)

    metrics: Dict[str, Any] = {
        "peak_field_strength": round(B_peak, 4),
        "average_field_strength": round(B_mean, 4),
        "minimum_field_strength": round(B_min, 4),
        "field_std": round(B_std, 4),
        "field_variance": round(B_var, 4),
        "field_uniformity_pct": uniformity_pct,
        "hot_spot": hot_spot,
        "cold_spot": cold_spot,
        "magnetic_center": magnetic_center,
        "gradient_stats": gradient_stats,
        "uniform_region_fraction": uniform_fraction,
        "coverage_area": coverage_area,
        "total_scan_area": total_area,
        "coverage_fraction": coverage_fraction,
        "field_distribution_histogram": histogram,
        "radial_falloff_profile": radial_profile,
        "symmetry_score": symmetry_score,
        "n_grid_cells": int(valid.sum()),
        "grid_shape": [int(grid.ny), int(grid.nx)],
        "interpolation_quality": grid.quality,
        "units": {
            "field": "µT",
            "position": schema.units or "mm",
            "area": f"({schema.units or 'mm'})²",
            "gradient": f"µT / ({schema.units or 'mm'})",
        },
    }

    logger.info(
        "metrics: peak=%.2f µT, mean=%.2f µT, uniformity=%.1f%%",
        B_peak, B_mean, uniformity_pct or 0,
    )
    return metrics
