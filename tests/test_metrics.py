"""Tests for src.field_mapping.metrics — field characterization metrics."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

scipy = pytest.importorskip("scipy", reason="scipy required for metrics tests")

from src.field_mapping.detector import FieldSchema
from src.field_mapping.interpolator import interpolate_to_grid
from src.field_mapping.metrics import compute_field_metrics


def _schema(units="mm") -> FieldSchema:
    return FieldSchema(
        x_col="X", y_col="Y", z_col=None,
        b_col="B", bx_col=None, by_col=None, bz_col=None,
        is_3d=False, has_vector=False, units=units,
    )


def _regular_grid_df(nx=8, ny=8, peak_at_center=True) -> pd.DataFrame:
    """Dense regular grid with a known peak at center when peak_at_center=True."""
    xs = np.linspace(-20, 20, nx)
    ys = np.linspace(-20, 20, ny)
    XX, YY = np.meshgrid(xs, ys)
    if peak_at_center:
        B = 100.0 * np.exp(-(XX**2 + YY**2) / 200)
    else:
        B = 50.0 + XX * 0.5   # linear gradient
    return pd.DataFrame({"X": XX.ravel(), "Y": YY.ravel(), "B": B.ravel()})


def _get_grid(df, res=40):
    schema = _schema()
    return interpolate_to_grid(df, schema, {"grid_resolution": res}), schema


class TestBasicMetrics:
    def test_returns_dict(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert isinstance(m, dict)

    def test_peak_field_present_and_positive(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert "peak_field_strength" in m
        assert m["peak_field_strength"] > 0

    def test_average_field_present_and_positive(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert "average_field_strength" in m
        assert m["average_field_strength"] > 0

    def test_min_field_present(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert "minimum_field_strength" in m
        assert m["minimum_field_strength"] >= 0

    def test_ordering_peak_ge_avg_ge_min(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert m["peak_field_strength"] >= m["average_field_strength"]
        assert m["average_field_strength"] >= m["minimum_field_strength"]

    def test_std_nonnegative(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert m["field_std"] >= 0

    def test_uniformity_bounded(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        u = m.get("field_uniformity_pct")
        assert u is not None
        assert -200 < u <= 100


class TestHotSpot:
    def test_hot_spot_near_center_for_gaussian(self):
        grid, schema = _get_grid(_regular_grid_df(peak_at_center=True), res=50)
        m = compute_field_metrics(grid, schema)
        hs = m["hot_spot"]
        # Gaussian peak is at (0, 0) — allow 5mm tolerance due to grid resolution
        assert abs(hs["x"]) < 5.0
        assert abs(hs["y"]) < 5.0

    def test_hot_spot_b_matches_peak(self):
        grid, schema = _get_grid(_regular_grid_df(), res=40)
        m = compute_field_metrics(grid, schema)
        assert abs(m["hot_spot"]["B"] - m["peak_field_strength"]) < 1e-6


class TestGradient:
    def test_gradient_stats_keys_present(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        gs = m.get("gradient_stats", {})
        assert "max_gradient" in gs
        assert "mean_gradient" in gs

    def test_gradient_nonnegative(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert m["gradient_stats"]["max_gradient"] >= 0
        assert m["gradient_stats"]["mean_gradient"] >= 0

    def test_gradient_location_present(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert "peak_gradient_location" in m["gradient_stats"]


class TestMagneticCenter:
    def test_magnetic_center_present(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        mc = m.get("magnetic_center")
        assert mc is not None
        assert "x" in mc and "y" in mc

    def test_magnetic_center_near_origin_for_gaussian(self):
        grid, schema = _get_grid(_regular_grid_df(peak_at_center=True), res=50)
        m = compute_field_metrics(grid, schema)
        mc = m["magnetic_center"]
        assert abs(mc["x"]) < 3.0
        assert abs(mc["y"]) < 3.0


class TestHistogram:
    def test_histogram_present(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        hist = m.get("field_distribution_histogram", {})
        assert "bin_edges" in hist
        assert "counts" in hist

    def test_histogram_counts_sum_to_n_cells(self):
        grid, schema = _get_grid(_regular_grid_df(), res=30)
        m = compute_field_metrics(grid, schema)
        hist = m["field_distribution_histogram"]
        total_in_hist = sum(hist["counts"])
        assert total_in_hist == m["n_grid_cells"]


class TestCoverage:
    def test_coverage_fraction_between_0_and_1(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert 0.0 <= m["coverage_fraction"] <= 1.0

    def test_coverage_area_positive(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert m["coverage_area"] > 0


class TestEdgeCases:
    def test_empty_grid_returns_error_key(self):
        """A grid full of NaN should not crash but return an error entry."""
        import numpy as np
        from src.field_mapping.interpolator import GridResult

        xi = np.linspace(0, 10, 5)
        yi = np.linspace(0, 10, 5)
        XX, YY = np.meshgrid(xi, yi)
        Bi = np.full_like(XX, np.nan)
        schema = _schema()

        grid = GridResult(
            xi=xi, yi=yi, XX=XX, YY=YY,
            Bi=Bi, Bxi=None, Byi=None, Bzi=None,
            x_raw=np.array([]), y_raw=np.array([]), B_raw=np.array([]),
            nx=5, ny=5, method="linear", quality={},
        )
        m = compute_field_metrics(grid, schema)
        assert "error" in m

    def test_units_in_result(self):
        grid, schema = _get_grid(_regular_grid_df())
        m = compute_field_metrics(grid, schema)
        assert "units" in m
        assert m["units"]["field"] == "µT"
