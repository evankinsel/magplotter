"""Magnetic field contour map generator.

Produces a publication-quality filled contour plot with labelled contour lines,
and marks the peak and minimum field locations.

Public API:
    generate_contour_map(grid, schema, output_dir, config) -> Path

Output: field_contours.png
"""
import logging
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np

from .detector import FieldSchema
from .interpolator import GridResult

logger = logging.getLogger(__name__)

_FIGURE_SIZE = (9, 7)
_DPI = 150
_DEFAULT_LEVELS = 15
_DEFAULT_COLORMAP = "plasma"


def generate_contour_map(
    grid: GridResult,
    schema: FieldSchema,
    output_dir: Path,
    config: Optional[dict] = None,
) -> Path:
    """
    Render filled + labelled contour map of field magnitude.

    Marks the global maximum (⊕) and minimum (⊗) field locations.

    Parameters
    ----------
    grid        : GridResult from interpolator
    schema      : FieldSchema from detector
    output_dir  : directory where field_contours.png will be written
    config      : optional dict with keys: levels, colormap

    Returns the path to the saved PNG.
    """
    if config is None:
        config = {}

    levels = int(config.get("levels", _DEFAULT_LEVELS))
    colormap = config.get("colormap", _DEFAULT_COLORMAP)
    output_dir = Path(output_dir)
    out_path = output_dir / "field_contours.png"

    logger.info("contour: generating %s (levels=%d)", out_path, levels)

    fig, ax = plt.subplots(figsize=_FIGURE_SIZE, dpi=_DPI)

    Bi_masked = np.ma.masked_invalid(grid.Bi)

    # Filled contours
    cf = ax.contourf(grid.XX, grid.YY, Bi_masked, levels=levels, cmap=colormap)

    # Contour lines with labels
    cs = ax.contour(
        grid.XX, grid.YY, Bi_masked, levels=levels,
        colors="white", linewidths=0.6, alpha=0.7,
    )
    ax.clabel(cs, inline=True, fontsize=7, fmt="%.1f")

    # Colorbar
    cbar = fig.colorbar(cf, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("|B| (µT)", fontsize=11)

    # Find and mark peak / minimum on the valid (non-NaN) grid
    valid_mask = ~np.isnan(grid.Bi)
    if valid_mask.any():
        flat_max = np.nanargmax(grid.Bi)
        iy_max, ix_max = np.unravel_index(flat_max, grid.Bi.shape)
        xmax, ymax = grid.XX[iy_max, ix_max], grid.YY[iy_max, ix_max]
        bmax = grid.Bi[iy_max, ix_max]

        flat_min = np.nanargmin(grid.Bi)
        iy_min, ix_min = np.unravel_index(flat_min, grid.Bi.shape)
        xmin, ymin = grid.XX[iy_min, ix_min], grid.YY[iy_min, ix_min]
        bmin = grid.Bi[iy_min, ix_min]

        ax.plot(
            xmax, ymax, marker="+", markersize=16, color="white",
            markeredgewidth=2, zorder=10,
            label=f"Max  |B|={bmax:.1f} µT  ({xmax:.1f}, {ymax:.1f})",
        )
        ax.plot(
            xmin, ymin, marker="x", markersize=14, color="cyan",
            markeredgewidth=2, zorder=10,
            label=f"Min  |B|={bmin:.1f} µT  ({xmin:.1f}, {ymin:.1f})",
        )

    ul = f"({schema.units or 'mm'})"
    ax.set_xlabel(f"{schema.x_col} {ul}", fontsize=11)
    ax.set_ylabel(f"{schema.y_col} {ul}", fontsize=11)
    ax.set_title("Magnetic Field Magnitude — Contour Map", fontsize=13, fontweight="bold")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(fontsize=8, loc="upper right", framealpha=0.7)

    fig.tight_layout()
    fig.savefig(out_path, dpi=_DPI)
    plt.close(fig)
    logger.info("contour: saved %s", out_path)
    return out_path
