"""Tests for src.field_mapping.heatmap — PNG generation."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # headless

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

scipy = pytest.importorskip("scipy", reason="scipy required for interpolation")

from src.field_mapping.detector import FieldSchema
from src.field_mapping.interpolator import interpolate_to_grid
from src.field_mapping.heatmap import generate_heatmap
from src.field_mapping.contour import generate_contour_map
from src.field_mapping.surface import generate_surface


def _make_grid(tmp_path):
    rng = np.random.default_rng(7)
    n = 30
    df = pd.DataFrame({
        "X": rng.uniform(0, 50, n),
        "Y": rng.uniform(0, 50, n),
        "B": 100 - rng.uniform(0, 20, n),
    })
    schema = FieldSchema(
        x_col="X", y_col="Y", z_col=None,
        b_col="B", bx_col=None, by_col=None, bz_col=None,
        is_3d=False, has_vector=False, units="mm",
    )
    grid = interpolate_to_grid(df, schema, {"grid_resolution": 20})
    return grid, schema


class TestHeatmap:
    def test_heatmap_file_created(self, tmp_path):
        grid, schema = _make_grid(tmp_path)
        out = generate_heatmap(grid, schema, tmp_path)
        assert out.exists()
        assert out.stat().st_size > 1000   # non-trivial PNG

    def test_heatmap_correct_filename(self, tmp_path):
        grid, schema = _make_grid(tmp_path)
        out = generate_heatmap(grid, schema, tmp_path)
        assert out.name == "field_heatmap.png"

    def test_heatmap_custom_colormap(self, tmp_path):
        grid, schema = _make_grid(tmp_path)
        out = generate_heatmap(grid, schema, tmp_path, config={"colormap": "plasma"})
        assert out.exists()

    def test_heatmap_default_config(self, tmp_path):
        grid, schema = _make_grid(tmp_path)
        out = generate_heatmap(grid, schema, tmp_path, config=None)
        assert out.exists()


class TestContourMap:
    def test_contour_file_created(self, tmp_path):
        grid, schema = _make_grid(tmp_path)
        out = generate_contour_map(grid, schema, tmp_path)
        assert out.exists()
        assert out.name == "field_contours.png"
        assert out.stat().st_size > 1000

    def test_contour_custom_levels(self, tmp_path):
        grid, schema = _make_grid(tmp_path)
        out = generate_contour_map(grid, schema, tmp_path, config={"levels": 5})
        assert out.exists()


class TestSurface:
    def test_surface_file_created(self, tmp_path):
        grid, schema = _make_grid(tmp_path)
        out = generate_surface(grid, schema, tmp_path)
        assert out.exists()
        assert out.name == "field_surface.png"
        assert out.stat().st_size > 1000

    def test_surface_custom_angle(self, tmp_path):
        grid, schema = _make_grid(tmp_path)
        out = generate_surface(grid, schema, tmp_path, config={"elevation": 45, "azimuth": 30})
        assert out.exists()


class TestVectorField:
    def test_vector_field_with_components(self, tmp_path):
        from src.field_mapping.vectorfield import generate_vector_field

        rng = np.random.default_rng(11)
        n = 40
        df = pd.DataFrame({
            "X": rng.uniform(0, 50, n),
            "Y": rng.uniform(0, 50, n),
            "B": 100 - rng.uniform(0, 20, n),
            "Bx": rng.uniform(-10, 10, n),
            "By": rng.uniform(-10, 10, n),
        })
        schema = FieldSchema(
            x_col="X", y_col="Y", z_col=None,
            b_col="B", bx_col="Bx", by_col="By", bz_col=None,
            is_3d=False, has_vector=True, units="mm",
        )
        grid = interpolate_to_grid(df, schema, {"grid_resolution": 20})
        out = generate_vector_field(grid, schema, tmp_path)
        assert out is not None
        assert out.exists()
        assert out.name == "vector_field.png"

    def test_vector_field_returns_none_without_components(self, tmp_path):
        from src.field_mapping.vectorfield import generate_vector_field
        from src.field_mapping.interpolator import GridResult

        # Grid without Bxi/Byi
        grid, schema = _make_grid(tmp_path)
        result = generate_vector_field(grid, schema, tmp_path)
        assert result is None
