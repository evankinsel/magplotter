"""Magnetic field vector field (quiver) visualizer.

Renders the in-plane field direction and magnitude as a quiver plot when Bx
and By data are available.  The background coloring shows field magnitude;
arrows show direction (and optionally strength through length).

Public API:
    generate_vector_field(grid, schema, output_dir, config) -> Optional[Path]

Output: vector_field.png
Returns None (not an error) when Bx/By data are absent.
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
_DEFAULT_DENSITY = 20   # quiver arrows per axis
_DEFAULT_NORMALIZE = False
_DEFAULT_COLORMAP = "viridis"


def generate_vector_field(
    grid: GridResult,
    schema: FieldSchema,
    output_dir: Path,
    config: Optional[dict] = None,
) -> Optional[Path]:
    """
    Produce a vector field overlay on a magnitude heatmap.

    Arrows are subsampled to `density` × `density` from the full grid.
    When normalize=True arrow lengths are uniform (direction only).

    Parameters
    ----------
    grid        : GridResult (must have Bxi and Byi populated)
    schema      : FieldSchema
    output_dir  : target directory
    config      : optional dict with keys: density, normalize, colormap

    Returns path to the saved PNG, or None when vector components are absent.
    """
    if grid.Bxi is None or grid.Byi is None:
        logger.warning("vector_field: Bx/By components not available — skipping")
        return None

    if config is None:
        config = {}

    density = int(config.get("density", _DEFAULT_DENSITY))
    normalize = bool(config.get("normalize", _DEFAULT_NORMALIZE))
    colormap = config.get("colormap", _DEFAULT_COLORMAP)
    output_dir = Path(output_dir)
    out_path = output_dir / "vector_field.png"

    logger.info("vector_field: generating (density=%d, normalize=%s)", density, normalize)

    fig, ax = plt.subplots(figsize=_FIGURE_SIZE, dpi=_DPI)

    # Background magnitude heatmap
    Bi_masked = np.ma.masked_invalid(grid.Bi)
    im = ax.pcolormesh(grid.XX, grid.YY, Bi_masked, cmap=colormap, shading="auto", alpha=0.8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("|B| (µT)", fontsize=11)

    # Subsample grid for quiver arrows
    step_x = max(1, grid.nx // density)
    step_y = max(1, grid.ny // density)
    sl = (slice(None, None, step_y), slice(None, None, step_x))

    qX = grid.XX[sl]
    qY = grid.YY[sl]
    qU = np.ma.masked_invalid(grid.Bxi[sl])
    qV = np.ma.masked_invalid(grid.Byi[sl])

    if normalize:
        mag = np.sqrt(qU**2 + qV**2)
        mag = np.where(mag == 0, 1, mag)
        qU, qV = qU / mag, qV / mag

    # Color arrows by magnitude for double encoding
    arrow_color = np.sqrt(qU**2 + qV**2).data
    ax.quiver(
        qX, qY, qU, qV,
        arrow_color,
        cmap=colormap,
        scale=None, scale_units="xy",
        angles="xy",
        width=0.003,
        alpha=0.9,
        zorder=5,
    )

    ul = f"({schema.units or 'mm'})"
    ax.set_xlabel(f"{schema.x_col} {ul}", fontsize=11)
    ax.set_ylabel(f"{schema.y_col} {ul}", fontsize=11)
    norm_label = " (normalized)" if normalize else ""
    ax.set_title(f"Magnetic Field Vector Map{norm_label}", fontsize=13, fontweight="bold")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.3, color="gray")

    fig.tight_layout()
    fig.savefig(out_path, dpi=_DPI)
    plt.close(fig)
    logger.info("vector_field: saved %s", out_path)
    return out_path
