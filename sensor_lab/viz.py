"""
Visualisation stage: produce matplotlib Figure objects from transformed sensor data.

Pure functions — no file I/O, no side effects.
Callers are responsible for saving and closing each Figure.

Functions:
    render_magnitude(df, title=...) -> Figure
    render_axes(df, title=...)      -> Figure
    render_heading(df, title=...)   -> Figure
"""
import logging

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def render_magnitude(
    df: pd.DataFrame,
    title: str = "Magnetic magnitude |B|",
) -> plt.Figure:
    """Return a Figure plotting |B| vs time. Expects df["magnitude"] from the transform stage."""
    fig, ax = plt.subplots(figsize=(6, 3))
    if df.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    else:
        B = df["magnitude"] if "magnitude" in df.columns else np.sqrt(
            df["mx"].astype(float) ** 2 + df["my"].astype(float) ** 2 + df["mz"].astype(float) ** 2
        )
        ax.plot(df["time"], B, "-", lw=1)
        ax.set_xlabel("time (s)")
        ax.set_ylabel("|B| (µT)")
        ax.grid(True, alpha=0.3)
    ax.set_title(title)
    fig.tight_layout()
    return fig


def render_axes(
    df: pd.DataFrame,
    title: str = "Raw axes",
) -> plt.Figure:
    """Return a Figure plotting mx/my/mz vs time."""
    fig, ax = plt.subplots(figsize=(6, 3))
    if df.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    else:
        ax.plot(df["time"], df["mx"], label="mx (µT)", lw=1)
        ax.plot(df["time"], df["my"], label="my (µT)", lw=1)
        ax.plot(df["time"], df["mz"], label="mz (µT)", lw=1)
        ax.set_xlabel("time (s)")
        ax.set_ylabel("magnetic field (µT)")
        ax.legend()
        ax.grid(True, alpha=0.3)
    ax.set_title(title)
    fig.tight_layout()
    return fig


def render_heading(
    df: pd.DataFrame,
    title: str = "Heading (deg)",
) -> plt.Figure:
    """Return a Figure plotting bearing vs time. Expects df["heading_deg"] from the transform stage."""
    fig, ax = plt.subplots(figsize=(6, 3))
    if df.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
    else:
        headings = df["heading_deg"] if "heading_deg" in df.columns else (
            np.rad2deg(np.arctan2(df["my"].astype(float), df["mx"].astype(float))) + 360
        ) % 360
        ax.plot(df["time"], headings, "-", lw=1)
        ax.set_xlabel("time (s)")
        ax.set_ylabel("heading (deg)")
        ax.set_ylim(0, 360)
        ax.grid(True, alpha=0.3)
    ax.set_title(title)
    fig.tight_layout()
    return fig
