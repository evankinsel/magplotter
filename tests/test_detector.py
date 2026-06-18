"""Tests for src.field_mapping.detector — coordinate and field column detection."""
import sys
from pathlib import Path
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.field_mapping.detector import detect_coordinates, FieldSchema


def _df(**kwargs) -> pd.DataFrame:
    """Helper: build a small DataFrame from column keyword arguments."""
    n = 4
    return pd.DataFrame({k: [float(i) for i in range(n)] for k in kwargs})


class TestDetect2D:
    def test_bare_xy_and_b(self):
        df = _df(X=None, Y=None, B=None)
        df["X"] = [0.0, 1.0, 2.0, 3.0]
        df["Y"] = [0.0, 1.0, 2.0, 3.0]
        df["B"] = [100.0, 95.0, 90.0, 85.0]
        s = detect_coordinates(df)
        assert s is not None
        assert s.x_col == "X"
        assert s.y_col == "Y"
        assert s.b_col == "B"
        assert s.is_3d is False
        assert s.has_vector is False

    def test_lowercase_xy_and_bmag(self):
        df = pd.DataFrame({"x": [0, 1, 2, 3], "y": [0, 1, 2, 3], "bmag": [10, 9, 8, 7]})
        s = detect_coordinates(df)
        assert s is not None
        assert s.x_col == "x"
        assert s.b_col == "bmag"

    def test_positional_aliases_pos_x_pos_y(self):
        df = pd.DataFrame({
            "pos_x": [0, 1, 2, 3],
            "pos_y": [0, 1, 2, 3],
            "field": [10, 9, 8, 7],
        })
        s = detect_coordinates(df)
        assert s is not None
        assert s.x_col == "pos_x"
        assert s.y_col == "pos_y"

    def test_mm_unit_suffix_aliases(self):
        df = pd.DataFrame({
            "x_mm": [0.0, 10.0, 20.0, 30.0],
            "y_mm": [0.0, 0.0, 0.0, 0.0],
            "B": [100.0, 95.0, 90.0, 85.0],
        })
        s = detect_coordinates(df)
        assert s is not None
        assert s.x_col == "x_mm"
        assert s.units == "mm"

    def test_position_x_alias(self):
        df = pd.DataFrame({
            "position_x": [0, 1, 2, 3],
            "position_y": [0, 1, 2, 3],
            "magnitude": [50.0, 48.0, 46.0, 44.0],
        })
        s = detect_coordinates(df)
        assert s is not None

    def test_vector_components_bx_by_bz(self):
        df = pd.DataFrame({
            "X": [0, 1, 2, 3],
            "Y": [0, 1, 2, 3],
            "Bx": [10.0, 9.0, 8.0, 7.0],
            "By": [5.0, 4.0, 4.0, 3.0],
            "Bz": [2.0, 2.0, 1.0, 1.0],
        })
        s = detect_coordinates(df)
        assert s is not None
        assert s.has_vector is True
        assert s.bx_col == "Bx"
        assert s.by_col == "By"
        assert s.bz_col == "Bz"
        assert s.b_col is None   # no explicit magnitude column

    def test_vector_components_lowercase(self):
        df = pd.DataFrame({
            "x": [0, 1, 2, 3],
            "y": [0, 1, 2, 3],
            "bx": [1.0, 2.0, 3.0, 4.0],
            "by": [0.5, 1.0, 1.5, 2.0],
        })
        s = detect_coordinates(df)
        assert s is not None
        assert s.has_vector is True

    def test_mx_my_fallback_when_spatial_present(self):
        df = pd.DataFrame({
            "x_mm": [0, 10, 20, 30],
            "y_mm": [0, 0, 0, 0],
            "mx": [10.0, 9.5, 9.0, 8.5],
            "my": [2.0, 2.0, 1.5, 1.0],
            "mz": [50.0, 48.0, 46.0, 44.0],
        })
        s = detect_coordinates(df)
        assert s is not None
        assert s.has_vector is True
        assert s.bx_col == "mx"


class TestDetect3D:
    def test_xyz_and_b(self):
        df = pd.DataFrame({
            "X": [0, 1, 0, 1],
            "Y": [0, 0, 1, 1],
            "Z": [0, 0, 0, 0],
            "B": [100.0, 95.0, 90.0, 85.0],
        })
        s = detect_coordinates(df)
        assert s is not None
        assert s.is_3d is True
        assert s.z_col == "Z"

    def test_xyz_mm_aliases(self):
        df = pd.DataFrame({
            "x_mm": [0, 1, 0, 1],
            "y_mm": [0, 0, 1, 1],
            "z_mm": [0, 0, 0, 1],
            "bmag": [10.0, 9.5, 9.0, 8.5],
        })
        s = detect_coordinates(df)
        assert s is not None
        assert s.is_3d is True
        assert s.z_col == "z_mm"


class TestDetectFailures:
    def test_empty_dataframe_returns_none(self):
        s = detect_coordinates(pd.DataFrame())
        assert s is None

    def test_time_series_df_returns_none(self):
        df = pd.DataFrame({
            "time": [0.0, 0.1, 0.2, 0.3],
            "mx": [10.0, 9.5, 9.0, 8.5],
            "my": [2.0, 2.0, 1.5, 1.0],
            "mz": [50.0, 48.0, 46.0, 44.0],
        })
        s = detect_coordinates(df)
        assert s is None

    def test_spatial_without_field_returns_none(self):
        df = pd.DataFrame({
            "X": [0, 1, 2, 3],
            "Y": [0, 1, 2, 3],
            "temperature": [25.0, 25.1, 25.2, 25.3],
        })
        s = detect_coordinates(df)
        assert s is None

    def test_only_x_no_y_returns_none(self):
        df = pd.DataFrame({"X": [0, 1, 2, 3], "B": [100, 90, 80, 70]})
        s = detect_coordinates(df)
        assert s is None

    def test_corrupted_column_names(self):
        df = pd.DataFrame({
            "!!!": [1, 2, 3, 4],
            "???": [1, 2, 3, 4],
        })
        s = detect_coordinates(df)
        assert s is None


class TestFieldSchema:
    def test_schema_is_dataclass(self):
        from dataclasses import fields
        field_names = {f.name for f in fields(FieldSchema)}
        assert "x_col" in field_names
        assert "y_col" in field_names
        assert "is_3d" in field_names
        assert "has_vector" in field_names
