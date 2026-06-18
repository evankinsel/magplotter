"""Interactive HTML export for field mapping visualizations using Plotly.

Generates browser-viewable HTML files with zoom, pan, and hover inspection.
Plotly is an optional dependency — this module skips gracefully when it is
not installed and logs at DEBUG level (not WARNING) to avoid alarming users
who do not need interactive output.

Public API:
    generate_interactive_exports(grid, schema, output_dir, config) -> List[Path]

Outputs (when plotly is available):
    interactive_heatmap.html
    interactive_surface.html
"""
import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

from .detector import FieldSchema
from .interpolator import GridResult

logger = logging.getLogger(__name__)

_PLOTLY_AVAILABLE: Optional[bool] = None


def _check_plotly() -> bool:
    global _PLOTLY_AVAILABLE
    if _PLOTLY_AVAILABLE is None:
        try:
            import plotly  # noqa: F401
            _PLOTLY_AVAILABLE = True
        except ImportError:
            _PLOTLY_AVAILABLE = False
            logger.debug(
                "export: plotly not installed — interactive HTML exports skipped. "
                "Install with: pip install plotly"
            )
    return _PLOTLY_AVAILABLE


def _interactive_heatmap(
    grid: GridResult,
    schema: FieldSchema,
    output_dir: Path,
    config: dict,
) -> Optional[Path]:
    import plotly.graph_objects as go

    out_path = output_dir / "interactive_heatmap.html"

    # Plotly Heatmap expects (y-axis, x-axis) indexing — same as our grid
    fig = go.Figure(
        data=go.Heatmap(
            z=grid.Bi,
            x=grid.xi,
            y=grid.yi,
            colorscale="Viridis",
            colorbar=dict(title="|B| (µT)"),
            hoverongaps=False,
            hovertemplate=(
                f"{schema.x_col}: %{{x:.2f}}<br>"
                f"{schema.y_col}: %{{y:.2f}}<br>"
                "|B|: %{z:.2f} µT<extra></extra>"
            ),
        )
    )

    ul = schema.units or "mm"
    fig.update_layout(
        title="Magnetic Field Magnitude — Interactive Heatmap",
        xaxis_title=f"{schema.x_col} ({ul})",
        yaxis_title=f"{schema.y_col} ({ul})",
        yaxis_scaleanchor="x",
        template="plotly_dark",
        margin=dict(l=60, r=60, t=60, b=60),
    )

    # Overlay raw measurement scatter
    fig.add_trace(go.Scatter(
        x=grid.x_raw, y=grid.y_raw,
        mode="markers",
        marker=dict(size=4, color="white", opacity=0.4),
        name="Measurement points",
        hovertemplate=f"{schema.x_col}: %{{x:.2f}}<br>{schema.y_col}: %{{y:.2f}}<extra></extra>",
    ))

    fig.write_html(str(out_path), include_plotlyjs="cdn")
    logger.info("export: interactive heatmap saved %s", out_path)
    return out_path


def _interactive_surface(
    grid: GridResult,
    schema: FieldSchema,
    output_dir: Path,
    config: dict,
) -> Optional[Path]:
    import plotly.graph_objects as go

    out_path = output_dir / "interactive_surface.html"

    # Replace NaN with mean for surface rendering
    B_fill = np.where(np.isnan(grid.Bi), float(np.nanmean(grid.Bi)), grid.Bi)

    fig = go.Figure(
        data=go.Surface(
            z=B_fill,
            x=grid.xi,
            y=grid.yi,
            colorscale="Viridis",
            colorbar=dict(title="|B| (µT)"),
            contours=dict(
                z=dict(show=True, usecolormap=True, highlightcolor="white", project_z=True)
            ),
        )
    )

    ul = schema.units or "mm"
    fig.update_layout(
        title="Magnetic Field Magnitude — Interactive 3D Surface",
        scene=dict(
            xaxis_title=f"{schema.x_col} ({ul})",
            yaxis_title=f"{schema.y_col} ({ul})",
            zaxis_title="|B| (µT)",
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        ),
        template="plotly_dark",
        margin=dict(l=0, r=0, t=60, b=0),
    )

    fig.write_html(str(out_path), include_plotlyjs="cdn")
    logger.info("export: interactive surface saved %s", out_path)
    return out_path


def generate_interactive_exports(
    grid: GridResult,
    schema: FieldSchema,
    output_dir: Path,
    config: Optional[dict] = None,
) -> List[Path]:
    """
    Generate interactive HTML exports using Plotly.

    Returns a list of paths to written HTML files.  Returns an empty list
    if Plotly is not installed — this is not treated as an error.
    """
    if not _check_plotly():
        return []

    if config is None:
        config = {}

    output_dir = Path(output_dir)
    generated: List[Path] = []

    try:
        p = _interactive_heatmap(grid, schema, output_dir, config)
        if p:
            generated.append(p)
    except Exception as exc:
        logger.warning("export: interactive heatmap failed — %s", exc)

    try:
        p = _interactive_surface(grid, schema, output_dir, config)
        if p:
            generated.append(p)
    except Exception as exc:
        logger.warning("export: interactive surface failed — %s", exc)

    logger.info("export: %d interactive file(s) generated", len(generated))
    return generated
