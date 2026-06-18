"""Field mapping subsystem for MagPlotter.

Entry point:
    run_field_mapping(csv_path, output_dir, base_dir, config) -> Optional[dict]

The top-level function orchestrates the full pipeline:
    1. Read raw CSV (all columns preserved)
    2. Detect spatial + field columns (detector)
    3. Interpolate onto uniform grid (interpolator)
    4. Generate heatmap, contour, vector field, surface (visualization modules)
    5. Compute characterization metrics (metrics)
    6. Export optional interactive HTML (export / plotly)

Returns a summary dict merged into the run summary by processor.py, or None
when the dataset does not contain spatial coordinate data.
"""
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .contour import generate_contour_map
from .detector import FieldSchema, detect_coordinates
from .export import generate_interactive_exports
from .heatmap import generate_heatmap
from .interpolator import GridResult, interpolate_to_grid
from .metrics import compute_field_metrics
from .surface import generate_surface
from .vectorfield import generate_vector_field

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG: Dict[str, Any] = {
    "field_mapping": {
        "enabled": True,
        "interpolation": {"method": "linear", "grid_resolution": 100},
        "heatmap": {"enabled": True, "colormap": "viridis"},
        "contour": {"enabled": True, "levels": 15},
        "vector_field": {"enabled": True, "density": 20, "normalize": False},
        "surface": {"enabled": True},
        "interactive": {"enabled": True},
    }
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base; override wins on conflict."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load config/config.yaml (if present) and merge with built-in defaults.
    Falls back to defaults silently when the file is missing or malformed.
    """
    if base_dir is None:
        return _DEFAULT_CONFIG

    config_path = Path(base_dir) / "config" / "config.yaml"
    if not config_path.exists():
        logger.debug("field_mapping: config.yaml not found — using defaults")
        return _DEFAULT_CONFIG

    try:
        import yaml
        with open(config_path, encoding="utf-8") as fh:
            user_cfg = yaml.safe_load(fh) or {}
        merged = _deep_merge(_DEFAULT_CONFIG, user_cfg)
        logger.debug("field_mapping: loaded config from %s", config_path)
        return merged
    except Exception as exc:
        logger.warning("field_mapping: could not parse config.yaml (%s) — using defaults", exc)
        return _DEFAULT_CONFIG


def _read_spatial_csv(csv_path: str) -> Optional[pd.DataFrame]:
    """
    Read a CSV preserving all columns (no column aliasing / row filtering).
    Comment lines starting with '#' or '//' are stripped before parsing.
    Returns None on any read error.
    """
    try:
        lines: List[str] = []
        with open(csv_path, "r", errors="replace") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                lines.append(line)

        content = "".join(lines)
        df = pd.read_csv(io.StringIO(content), skip_blank_lines=True)
        if df.empty:
            return None

        # Coerce all columns to numeric; non-numeric → NaN
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        return df
    except Exception as exc:
        logger.warning("field_mapping: could not read %s — %s", csv_path, exc)
        return None


def run_field_mapping(
    csv_path: str,
    output_dir: Path,
    base_dir: Optional[Path] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Execute the complete field mapping pipeline for one CSV file.

    Parameters
    ----------
    csv_path   : path to the raw CSV (read independently from the time-series parser)
    output_dir : run output directory (e.g. output/runs/<run_name>/)
    base_dir   : project root, used to locate config/config.yaml
    config     : pre-loaded config dict; if None, config.yaml is loaded automatically

    Returns a result dict (schema info, metrics, generated file list) on success,
    or None if the dataset has no spatial coordinate data or mapping is disabled.
    """
    logger.info("field_mapping: starting — source: %s", csv_path)

    if config is None:
        config = load_config(base_dir)

    fm_cfg = config.get("field_mapping", {})
    if not fm_cfg.get("enabled", True):
        logger.info("field_mapping: disabled in config — skipping")
        return None

    # 1. Read raw CSV
    df = _read_spatial_csv(csv_path)
    if df is None:
        logger.debug("field_mapping: could not read CSV — skipping")
        return None

    # 2. Coordinate detection
    schema = detect_coordinates(df)
    if schema is None:
        return None   # warning already logged by detector

    # 3. Interpolation
    interp_cfg = fm_cfg.get("interpolation", {})
    grid = interpolate_to_grid(df, schema, interp_cfg)
    if grid is None:
        logger.warning("field_mapping: interpolation failed — skipping")
        return None

    output_dir = Path(output_dir)
    generated: List[str] = []

    # 4a. Heatmap
    if fm_cfg.get("heatmap", {}).get("enabled", True):
        try:
            p = generate_heatmap(grid, schema, output_dir, fm_cfg.get("heatmap", {}))
            generated.append(str(p))
        except Exception:
            logger.warning("field_mapping: heatmap generation failed", exc_info=True)

    # 4b. Contour map
    if fm_cfg.get("contour", {}).get("enabled", True):
        try:
            p = generate_contour_map(grid, schema, output_dir, fm_cfg.get("contour", {}))
            generated.append(str(p))
        except Exception:
            logger.warning("field_mapping: contour map generation failed", exc_info=True)

    # 4c. Vector field (only when Bx/By available)
    if schema.has_vector and fm_cfg.get("vector_field", {}).get("enabled", True):
        try:
            p = generate_vector_field(grid, schema, output_dir, fm_cfg.get("vector_field", {}))
            if p:
                generated.append(str(p))
        except Exception:
            logger.warning("field_mapping: vector field generation failed", exc_info=True)

    # 4d. 3D surface
    if fm_cfg.get("surface", {}).get("enabled", True):
        try:
            p = generate_surface(grid, schema, output_dir, fm_cfg.get("surface", {}))
            generated.append(str(p))
        except Exception:
            logger.warning("field_mapping: surface plot generation failed", exc_info=True)

    # 5. Metrics
    metrics: Dict[str, Any] = {}
    try:
        metrics = compute_field_metrics(grid, schema)
        metrics_path = output_dir / "field_metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as fh:
            json.dump(metrics, fh, indent=2, ensure_ascii=False)
        generated.append(str(metrics_path))
        logger.debug("field_mapping: metrics saved to %s", metrics_path)
    except Exception:
        logger.warning("field_mapping: metrics computation failed", exc_info=True)

    # 6. Interactive exports (optional — skipped gracefully when plotly is absent)
    if fm_cfg.get("interactive", {}).get("enabled", True):
        try:
            paths = generate_interactive_exports(grid, schema, output_dir, fm_cfg.get("interactive", {}))
            generated.extend(str(p) for p in paths)
        except Exception:
            logger.debug("field_mapping: interactive export skipped", exc_info=True)

    logger.info(
        "field_mapping: complete — %d file(s) generated in %s",
        len(generated), output_dir,
    )

    return {
        "schema": {
            "x_col": schema.x_col,
            "y_col": schema.y_col,
            "z_col": schema.z_col,
            "b_col": schema.b_col,
            "bx_col": schema.bx_col,
            "by_col": schema.by_col,
            "bz_col": schema.bz_col,
            "is_3d": schema.is_3d,
            "has_vector": schema.has_vector,
            "units": schema.units,
        },
        "grid_shape": [int(grid.ny), int(grid.nx)],
        "interpolation_method": grid.method,
        "metrics": metrics,
        "generated_files": generated,
    }
