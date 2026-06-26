"""
Analysis stage: compute physics-based metrics from transformed sensor data.

Pure functions — no file I/O, no side effects.
Expects df to have been produced by transform_sensor_data (columns: time, mx, my, mz,
magnitude, heading_deg).  Falls back to inline computation when derived columns are absent
so the functions remain usable in isolation.

Functions:
    compute_all_metrics(df) -> dict
    axis_stats(df) -> dict
    magnitude_metrics(df) -> dict
    heading_metrics(df) -> dict
"""
import logging
from typing import Dict, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def axis_stats(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    stats = {}
    for axis in ["mx", "my", "mz"]:
        series = df[axis].astype(float)
        if series.empty:
            stats[axis] = {"mean": None, "std": None, "min": None, "max": None, "drift": None}
            continue
        stats[axis] = {
            "mean": float(series.mean()),
            "std": float(series.std(ddof=0)),
            "min": float(series.min()),
            "max": float(series.max()),
            "drift": float(series.iloc[-1] - series.iloc[0]) if len(series) >= 2 else 0.0,
        }
    return stats


def magnitude_metrics(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {"B_mean": None, "B_std": None, "B_drift": None}
    B = df["magnitude"] if "magnitude" in df.columns else np.sqrt(
        df["mx"].astype(float) ** 2 + df["my"].astype(float) ** 2 + df["mz"].astype(float) ** 2
    )
    return {
        "B_mean": float(B.mean()),
        "B_std": float(B.std(ddof=0)),
        "B_drift": float(B.iloc[-1] - B.iloc[0]) if len(B) >= 2 else 0.0,
    }


def circular_mean_deg(angles_deg: np.ndarray) -> float:
    ang = np.deg2rad(angles_deg)
    mean_sin = np.mean(np.sin(ang))
    mean_cos = np.mean(np.cos(ang))
    mean_ang = np.arctan2(mean_sin, mean_cos)
    return float(np.rad2deg(mean_ang) % 360)


def circular_std_deg(angles_deg: np.ndarray) -> float:
    # circular std (rad) = sqrt(-2 * ln(R)), R = mean resultant length
    ang = np.deg2rad(angles_deg)
    mean_sin = np.mean(np.sin(ang))
    mean_cos = np.mean(np.cos(ang))
    R = np.hypot(mean_cos, mean_sin)
    if R <= 0:
        return float(180.0)
    circ_std_rad = np.sqrt(-2.0 * np.log(np.clip(R, 1e-12, 1.0)))
    return float(np.rad2deg(circ_std_rad))


def heading_metrics(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {"heading_mean_deg": None, "heading_std_deg": None}
    headings = df["heading_deg"].to_numpy() if "heading_deg" in df.columns else (
        np.rad2deg(np.arctan2(df["my"].astype(float), df["mx"].astype(float))) % 360
    )
    mean_h = circular_mean_deg(headings)
    std_h = circular_std_deg(headings)
    return {"heading_mean_deg": mean_h, "heading_std_deg": std_h}


def noise_metric(df: pd.DataFrame) -> float:
    if df.empty:
        return None
    stds = [df[col].astype(float).std(ddof=0) for col in ["mx", "my", "mz"]]
    return float(np.mean(stds))


def compute_all_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    logger.debug("computing metrics for %d samples", len(df))
    metrics = {}
    metrics["axis_stats"] = axis_stats(df)
    metrics.update(magnitude_metrics(df))
    metrics.update(heading_metrics(df))
    metrics["noise_metric"] = noise_metric(df)
    metrics["num_samples"] = int(len(df))
    if not df.empty:
        metrics["time_span_s"] = float(df["time"].iloc[-1] - df["time"].iloc[0]) if len(df) >= 2 else 0.0
    else:
        metrics["time_span_s"] = None
    logger.debug(
        "metrics computed: num_samples=%d, B_mean=%s, time_span_s=%s",
        metrics["num_samples"], metrics.get("B_mean"), metrics.get("time_span_s"),
    )
    return metrics
