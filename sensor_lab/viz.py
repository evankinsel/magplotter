"""
Plotting functions: save B(t), axes(t), heading(t) as PNG files.

Functions:
    plot_magnitude(df, outpath, title=...)
    plot_axes(df, outpath, title=...)
    plot_heading(df, outpath, title=...)

These helpers use `matplotlib` and save figures to `outpath`. On headless
systems, set `MPLBACKEND=Agg` or ensure an appropriate backend is available.

Security note: plotting uses only numerical data and writes files to
the local filesystem; it does not execute file contents. Still, be
cautious when writing into shared output folders.
"""
import logging

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def plot_magnitude(df: pd.DataFrame, outpath: str, title: str = "Magnetic magnitude |B|"):
    logger.debug("generating field_strength plot -> %s", outpath)
    if df.empty:
        plt.figure()
        plt.text(0.5, 0.5, "No data", ha="center")
        plt.savefig(outpath)
        plt.close()
        logger.warning("field_strength plot saved with no data: %s", outpath)
        return
    B = np.sqrt(df["mx"] ** 2 + df["my"] ** 2 + df["mz"] ** 2)
    plt.figure(figsize=(6, 3))
    plt.plot(df["time"], B, "-", lw=1)
    plt.xlabel("time (s)")
    plt.ylabel("|B| (µT)")
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()
    logger.info("field_strength plot saved: %s", outpath)


def plot_axes(df: pd.DataFrame, outpath: str, title: str = "Raw axes"):
    logger.debug("generating axes plot -> %s", outpath)
    plt.figure(figsize=(6, 3))
    if df.empty:
        plt.text(0.5, 0.5, "No data", ha="center")
        logger.warning("axes plot saved with no data: %s", outpath)
    else:
        plt.plot(df["time"], df["mx"], label="mx (µT)", lw=1)
        plt.plot(df["time"], df["my"], label="my (µT)", lw=1)
        plt.plot(df["time"], df["mz"], label="mz (µT)", lw=1)
        plt.xlabel("time (s)")
        plt.ylabel("magnetic field (µT)")
        plt.legend()
        plt.grid(True, alpha=0.3)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()
    logger.info("axes plot saved: %s", outpath)


def plot_heading(df: pd.DataFrame, outpath: str, title: str = "Heading (deg)"):
    logger.debug("generating heading plot -> %s", outpath)
    plt.figure(figsize=(6, 3))
    if df.empty:
        plt.text(0.5, 0.5, "No data", ha="center")
        logger.warning("heading plot saved with no data: %s", outpath)
    else:
        headings = (np.rad2deg(np.arctan2(df["my"].astype(float), df["mx"].astype(float))) + 360) % 360
        plt.plot(df["time"], headings, "-", lw=1)
        plt.xlabel("time (s)")
        plt.ylabel("heading (deg)")
        plt.ylim(0, 360)
        plt.grid(True, alpha=0.3)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()
    logger.info("heading plot saved: %s", outpath)
