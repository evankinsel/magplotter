"""3-D surface visualizer for magnetic field magnitude.

Renders the interpolated field as a 3-D surface where height encodes |B|,
using matplotlib's Axes3D.  Smooth shading via lighting is applied when
supported by the backend.

Public API:
    generate_surface(grid, schema, output_dir, config) -> Path

Output: field_surface.png
"""
import logging
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — registers the 3-D projection

from .detector import FieldSchema
from .interpolator import GridResult

logger = logging.getLogger(__name__)

_FIGURE_SIZE = (10, 8)
_DPI = 150
_DEFAULT_COLORMAP = "viridis"
_DEFAULT_ELEV = 30
_DEFAULT_AZIM = -60
_DOWNSAMPLE = 80   # max grid points per axis for surface rendering


def generate_surface(
    grid: GridResult,
    schema: FieldSchema,
    output_dir: Path,
    config: Optional[dict] = None,
) -> Path:
    """
    Render a 3-D surface of field magnitude.

    Grid is downsampled to _DOWNSAMPLE per axis for performance; high-resolution
    grids would produce surfaces too heavy for static PNG output.

    Parameters
    ----------
    grid        : GridResult from interpolator
    schema      : FieldSchema from detector
    output_dir  : target directory
    config      : optional dict with keys: colormap, elevation, azimuth

    Returns path to the saved PNG.
    """
    if config is None:
        config = {}

    colormap = config.get("colormap", _DEFAULT_COLORMAP)
    elev = float(config.get("elevation", _DEFAULT_ELEV))
    azim = float(config.get("azimuth", _DEFAULT_AZIM))
    output_dir = Path(output_dir)
    out_path = output_dir / "field_surface.png"

    logger.info("surface: generating %s (elev=%.0f, azim=%.0f)", out_path, elev, azim)

    # Downsample for manageable rendering
    step = max(1, grid.nx // _DOWNSAMPLE)
    sl = (slice(None, None, step), slice(None, None, step))
    XX_s = grid.XX[sl]
    YY_s = grid.YY[sl]
    Bi_s = grid.Bi[sl]

    # Replace NaN with the mean so the surface renders without holes
    B_fill = np.where(np.isnan(Bi_s), np.nanmean(Bi_s), Bi_s)

    fig = plt.figure(figsize=_FIGURE_SIZE, dpi=_DPI)
    ax = fig.add_subplot(111, projection="3d")

    surf = ax.plot_surface(
        XX_s, YY_s, B_fill,
        cmap=colormap,
        linewidth=0,
        antialiased=True,
        alpha=0.92,
    )

    fig.colorbar(surf, ax=ax, shrink=0.5, aspect=12, pad=0.08, label="|B| (µT)")

    ul = schema.units or "mm"
    ax.set_xlabel(f"{schema.x_col} ({ul})", fontsize=10, labelpad=8)
    ax.set_ylabel(f"{schema.y_col} ({ul})", fontsize=10, labelpad=8)
    ax.set_zlabel("|B| (µT)", fontsize=10, labelpad=8)
    ax.set_title("Magnetic Field — 3D Surface", fontsize=13, fontweight="bold")
    ax.view_init(elev=elev, azim=azim)

    fig.tight_layout()
    fig.savefig(out_path, dpi=_DPI)
    plt.close(fig)
    logger.info("surface: saved %s", out_path)
    return out_path
