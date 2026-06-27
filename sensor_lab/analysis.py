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
    field_rate_stats(df) -> dict
"""
import logging
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def axis_stats(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """Compute per-axis statistics across mx, my, mz in a single vectorized pass."""
    axes = ["mx", "my", "mz"]
    null = {"mean": None, "std": None, "min": None, "max": None, "drift": None}
    data = df[axes].astype(float)

    if data.empty:
        return {ax: null.copy() for ax in axes}

    # One aggregation call per statistic across all three axes simultaneously
    means  = data.mean()
    stds   = data.std(ddof=0)
    mins   = data.min()
    maxs   = data.max()
    drifts = (data.iloc[-1] - data.iloc[0]) if len(data) >= 2 else pd.Series(0.0, index=axes)

    return {
        ax: {
            "mean":  float(means[ax]),
            "std":   float(stds[ax]),
            "min":   float(mins[ax]),
            "max":   float(maxs[ax]),
            "drift": float(drifts[ax]),
        }
        for ax in axes
    }


def magnitude_metrics(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    if df.empty:
        return {"B_mean": None, "B_std": None, "B_drift": None}
    B = df["magnitude"] if "magnitude" in df.columns else np.sqrt(
        df["mx"].astype(float) ** 2 + df["my"].astype(float) ** 2 + df["mz"].astype(float) ** 2
    )
    return {
        "B_mean":  float(B.mean()),
        "B_std":   float(B.std(ddof=0)),
        "B_drift": float(B.iloc[-1] - B.iloc[0]) if len(B) >= 2 else 0.0,
    }


def circular_mean_deg(angles_deg: np.ndarray) -> float:
    ang = np.deg2rad(angles_deg)
    mean_ang = np.arctan2(np.mean(np.sin(ang)), np.mean(np.cos(ang)))
    return float(np.rad2deg(mean_ang) % 360)


def circular_std_deg(angles_deg: np.ndarray) -> float:
    # circular std (rad) = sqrt(-2 * ln(R)), R = mean resultant length
    ang = np.deg2rad(angles_deg)
    R = np.hypot(np.mean(np.cos(ang)), np.mean(np.sin(ang)))
    if R <= 0:
        return float(180.0)
    return float(np.rad2deg(np.sqrt(-2.0 * np.log(np.clip(R, 1e-12, 1.0)))))


def heading_metrics(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    if df.empty:
        return {"heading_mean_deg": None, "heading_std_deg": None}
    headings = df["heading_deg"].to_numpy() if "heading_deg" in df.columns else (
        np.rad2deg(np.arctan2(df["my"].astype(float), df["mx"].astype(float))) % 360
    )
    return {
        "heading_mean_deg": circular_mean_deg(headings),
        "heading_std_deg":  circular_std_deg(headings),
    }


def noise_metric(df: pd.DataFrame) -> Optional[float]:
    """Mean per-axis standard deviation — proxy for sensor noise floor."""
    if df.empty:
        return None
    return float(df[["mx", "my", "mz"]].astype(float).std(ddof=0).mean())


def field_rate_stats(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """
    Instantaneous rate-of-change of field magnitude dB/dt (µT s⁻¹).

    Uses np.gradient with the explicit time coordinate array so the derivative
    is correctly scaled even when sample intervals are non-uniform.
    """
    if df.empty or len(df) < 2:
        return {"dB_dt_max_abs": None, "dB_dt_mean_abs": None, "dB_dt_rms": None}

    B = (df["magnitude"].to_numpy(dtype=float) if "magnitude" in df.columns else
         np.sqrt(df["mx"].astype(float).to_numpy() ** 2
                 + df["my"].astype(float).to_numpy() ** 2
                 + df["mz"].astype(float).to_numpy() ** 2))
    t = df["time"].to_numpy(dtype=float)

    # Explicit time axis array — handles non-uniform sampling correctly
    dB_dt = np.gradient(B, t)

    return {
        "dB_dt_max_abs":  float(np.abs(dB_dt).max()),
        "dB_dt_mean_abs": float(np.abs(dB_dt).mean()),
        "dB_dt_rms":      float(np.sqrt(np.mean(dB_dt ** 2))),
    }


def compute_all_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    logger.debug("computing metrics for %d samples", len(df))
    metrics: Dict[str, Any] = {}
    metrics["axis_stats"] = axis_stats(df)
    metrics.update(magnitude_metrics(df))
    metrics.update(heading_metrics(df))
    metrics["noise_metric"] = noise_metric(df)
    metrics["field_rate"] = field_rate_stats(df)
    metrics["num_samples"] = int(len(df))
    if not df.empty:
        metrics["time_span_s"] = (
            float(df["time"].iloc[-1] - df["time"].iloc[0]) if len(df) >= 2 else 0.0
        )
    else:
        metrics["time_span_s"] = None
    logger.debug(
        "metrics computed: num_samples=%d, B_mean=%s, time_span_s=%s",
        metrics["num_samples"], metrics.get("B_mean"), metrics.get("time_span_s"),
    )
    return metrics
