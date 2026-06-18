"""Magnetic field heatmap generator.

Produces an engineering-quality 2-D heatmap PNG of field magnitude on the
interpolated grid, using a perceptually-uniform colormap (default: viridis).

Public API:
    generate_heatmap(grid, schema, output_dir, config) -> Path

Output: field_heatmap.png
"""
import logging
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np

from .detector import FieldSchema
from .interpolator import GridResult

logger = logging.getLogger(__name__)

_DEFAULT_COLORMAP = "viridis"
_FIGURE_SIZE = (9, 7)
_DPI = 150


def _units_label(schema: FieldSchema) -> str:
    pos_units = schema.units or "mm"
    return f"({pos_units})"


def generate_heatmap(
    grid: GridResult,
    schema: FieldSchema,
    output_dir: Path,
    config: Optional[dict] = None,
) -> Path:
    """
    Render the interpolated field magnitude as a 2-D heatmap.

    Parameters
    ----------
    grid        : GridResult from interpolator.interpolate_to_grid
    schema      : FieldSchema from detector.detect_coordinates
    output_dir  : directory where field_heatmap.png will be written
    config      : optional dict with keys: colormap

    Returns the path to the saved PNG.
    """
    if config is None:
        config = {}

    colormap = config.get("colormap", _DEFAULT_COLORMAP)
    output_dir = Path(output_dir)
    out_path = output_dir / "field_heatmap.png"

    logger.info("heatmap: generating %s", out_path)

    fig, ax = plt.subplots(figsize=_FIGURE_SIZE, dpi=_DPI)

    # Mask NaN for display
    Bi_masked = np.ma.masked_invalid(grid.Bi)

    im = ax.pcolormesh(
        grid.XX, grid.YY, Bi_masked,
        cmap=colormap, shading="auto",
    )

    # Raw measurement locations
    ax.scatter(
        grid.x_raw, grid.y_raw,
        c="white", s=6, marker=".", alpha=0.4, label="Measurement points",
        zorder=5,
    )

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("|B| (µT)", fontsize=11)

    # Axes labels
    ul = _units_label(schema)
    ax.set_xlabel(f"{schema.x_col} {ul}", fontsize=11)
    ax.set_ylabel(f"{schema.y_col} {ul}", fontsize=11)
    ax.set_title("Magnetic Field Magnitude — 2D Heatmap", fontsize=13, fontweight="bold")

    ax.grid(True, linestyle="--", linewidth=0.4, alpha=0.5, color="gray")
    ax.set_aspect("equal", adjustable="box")
    ax.legend(fontsize=8, loc="upper right")

    fig.tight_layout()
    fig.savefig(out_path, dpi=_DPI)
    plt.close(fig)
    logger.info("heatmap: saved %s", out_path)
    return out_path
