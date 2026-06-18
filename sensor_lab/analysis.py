"""
Compute physics-based metrics for a magnetometer run.
Includes axis stats, |B| metrics, heading (circular stats), noise metric.

Primary functions:
    compute_all_metrics(df) -> dict
    axis_stats(df) -> dict
    magnitude_metrics(df) -> dict
    heading_metrics(df) -> dict

Notes: functions expect a `pandas.DataFrame` with numeric columns `time, mx, my, mz`.
If the DataFrame is empty, functions return sensible `None`-filled placeholders.

Security note: this module performs numerical computations only and
does not touch external resources. Ensure upstream parsing has validated
and sanitized input data types.
"""
from typing import Dict, Any
import numpy as np
import pandas as pd


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
    B = np.sqrt(df["mx"] ** 2 + df["my"] ** 2 + df["mz"] ** 2)
    return {
        "B_mean": float(B.mean()),
        "B_std": float(B.std(ddof=0)),
        "B_drift": float(B.iloc[-1] - B.iloc[0]) if len(B) >= 2 else 0.0,
    }


def circular_mean_deg(angles_deg: np.ndarray) -> float:
    # convert degrees to radians, compute atan2(mean_sin, mean_cos)
    ang = np.deg2rad(angles_deg)
    mean_sin = np.mean(np.sin(ang))
    mean_cos = np.mean(np.cos(ang))
    mean_ang = np.arctan2(mean_sin, mean_cos)
    return float(np.rad2deg(mean_ang) % 360)


def circular_std_deg(angles_deg: np.ndarray) -> float:
    # circular standard deviation (radians) = sqrt(-2 * ln(R)), where R = sqrt(mean_cos^2 + mean_sin^2)
    ang = np.deg2rad(angles_deg)
    mean_sin = np.mean(np.sin(ang))
    mean_cos = np.mean(np.cos(ang))
    R = np.hypot(mean_cos, mean_sin)
    if R <= 0:
        return float(180.0)  # maximal uncertainty fallback
    circ_std_rad = np.sqrt(-2.0 * np.log(np.clip(R, 1e-12, 1.0)))
    return float(np.rad2deg(circ_std_rad))


def heading_metrics(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {"heading_mean_deg": None, "heading_std_deg": None}
    headings = np.rad2deg(np.arctan2(df["my"].astype(float), df["mx"].astype(float))) % 360
    mean_h = circular_mean_deg(headings)
    std_h = circular_std_deg(headings)
    return {"heading_mean_deg": mean_h, "heading_std_deg": std_h}


def noise_metric(df: pd.DataFrame) -> float:
    if df.empty:
        return None
    stds = [df[col].astype(float).std(ddof=0) for col in ["mx", "my", "mz"]]
    return float(np.mean(stds))


def compute_all_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    metrics = {}
    metrics["axis_stats"] = axis_stats(df)
    metrics.update(magnitude_metrics(df))
    metrics.update(heading_metrics(df))
    metrics["noise_metric"] = noise_metric(df)
    # additional metadata
    metrics["num_samples"] = int(len(df))
    if not df.empty:
        metrics["time_span_s"] = float(df["time"].iloc[-1] - df["time"].iloc[0]) if len(df) >= 2 else 0.0
    else:
        metrics["time_span_s"] = None
    return metrics
