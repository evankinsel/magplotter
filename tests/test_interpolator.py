"""Tests for src.field_mapping.interpolator — grid interpolation."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

scipy = pytest.importorskip("scipy", reason="scipy required for interpolation tests")

from src.field_mapping.detector import FieldSchema
from src.field_mapping.interpolator import (
    GridResult,
    interpolate_to_grid,
    MIN_POINTS_LINEAR,
    DEFAULT_RESOLUTION,
)


def _schema_2d_b(x="X", y="Y", b="B") -> FieldSchema:
    return FieldSchema(
        x_col=x, y_col=y, z_col=None,
        b_col=b, bx_col=None, by_col=None, bz_col=None,
        is_3d=False, has_vector=False, units=None,
    )


def _schema_2d_vec() -> FieldSchema:
    return FieldSchema(
        x_col="X", y_col="Y", z_col=None,
        b_col="B", bx_col="Bx", by_col="By", bz_col="Bz",
        is_3d=False, has_vector=True, units="mm",
    )


def _grid_df(nx=5, ny=5, noise=0.0) -> pd.DataFrame:
    """Create a regular grid dataset with a known field distribution."""
    rng = np.random.default_rng(42)
    xs = np.linspace(0, 40, nx)
    ys = np.linspace(0, 40, ny)
    XX, YY = np.meshgrid(xs, ys)
    B = 100.0 - (XX**2 + YY**2) * 0.05
    if noise:
        B += rng.normal(0, noise, B.shape)
    return pd.DataFrame({
        "X": XX.ravel(),
        "Y": YY.ravel(),
        "B": B.ravel(),
    })


class TestBasicInterpolation:
    def test_linear_returns_grid_result(self):
        df = _grid_df(5, 5)
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema, {"method": "linear", "grid_resolution": 20})
        assert result is not None
        assert isinstance(result, GridResult)

    def test_nearest_interpolation(self):
        df = _grid_df(5, 5)
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema, {"method": "nearest", "grid_resolution": 20})
        assert result is not None
        assert result.method == "nearest"

    def test_cubic_interpolation(self):
        df = _grid_df(6, 6)   # enough points for cubic
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema, {"method": "cubic", "grid_resolution": 20})
        assert result is not None

    def test_grid_shape_matches_resolution(self):
        df = _grid_df(5, 5)
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema, {"grid_resolution": 30})
        assert result.Bi.shape == (30, 30)
        assert len(result.xi) == 30
        assert len(result.yi) == 30

    def test_bi_not_all_nan(self):
        df = _grid_df(5, 5)
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema)
        assert result is not None
        assert not np.all(np.isnan(result.Bi))

    def test_raw_arrays_preserved(self):
        df = _grid_df(5, 5)
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema)
        assert result is not None
        assert len(result.x_raw) == len(df)
        assert len(result.B_raw) == len(df)

    def test_quality_dict_present(self):
        df = _grid_df(5, 5)
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema)
        assert result is not None
        assert "nan_fraction" in result.quality
        assert "n_input_points" in result.quality

    def test_unknown_method_falls_back_to_linear(self):
        df = _grid_df(5, 5)
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema, {"method": "bogus"})
        assert result is not None
        assert result.method == "linear"


class TestVectorInterpolation:
    def test_vector_components_interpolated(self):
        n = 25
        rng = np.random.default_rng(0)
        df = pd.DataFrame({
            "X": rng.uniform(0, 40, n),
            "Y": rng.uniform(0, 40, n),
            "B": rng.uniform(80, 120, n),
            "Bx": rng.uniform(-10, 10, n),
            "By": rng.uniform(-10, 10, n),
            "Bz": rng.uniform(-5, 5, n),
        })
        schema = _schema_2d_vec()
        result = interpolate_to_grid(df, schema, {"grid_resolution": 15})
        assert result is not None
        assert result.Bxi is not None
        assert result.Byi is not None
        assert result.Bzi is not None
        assert result.Bxi.shape == result.Bi.shape


class TestSparseData:
    def test_too_few_points_returns_none(self):
        df = pd.DataFrame({"X": [0.0, 1.0], "Y": [0.0, 1.0], "B": [100.0, 90.0]})
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema)
        assert result is None   # only 2 points < MIN_POINTS_LINEAR

    def test_minimum_points_works(self):
        df = pd.DataFrame({
            "X": [0.0, 10.0, 20.0],
            "Y": [0.0, 10.0, 0.0],
            "B": [100.0, 90.0, 80.0],
        })
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema, {"method": "linear", "grid_resolution": 10})
        assert result is not None

    def test_cubic_falls_back_for_sparse(self):
        df = pd.DataFrame({
            "X": [0.0, 5.0, 10.0, 15.0],
            "Y": [0.0, 0.0, 5.0, 5.0],
            "B": [100.0, 90.0, 80.0, 70.0],
        })
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema, {"method": "cubic", "grid_resolution": 10})
        assert result is not None
        assert result.method == "linear"   # auto-downgraded

    def test_nan_in_input_stripped(self):
        df = pd.DataFrame({
            "X": [0.0, np.nan, 10.0, 20.0, 30.0],
            "Y": [0.0, 5.0, 10.0, 0.0, 10.0],
            "B": [100.0, 95.0, np.nan, 85.0, 80.0],
        })
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema, {"grid_resolution": 10})
        assert result is not None
        assert result.quality["n_valid_after_filter"] == 3


class TestLargeDataset:
    def test_large_dataset_performance(self):
        rng = np.random.default_rng(99)
        n = 5000
        df = pd.DataFrame({
            "X": rng.uniform(0, 100, n),
            "Y": rng.uniform(0, 100, n),
            "B": 100 - rng.uniform(0, 30, n),
        })
        schema = _schema_2d_b()
        result = interpolate_to_grid(df, schema, {"method": "linear", "grid_resolution": 50})
        assert result is not None
        assert result.Bi.shape == (50, 50)
