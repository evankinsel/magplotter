"""
Plotting functions: save B(t), axes(t), heading(t) as PNG files.
"""
from typing import Dict
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_magnitude(df: pd.DataFrame, outpath: str, title: str = "Magnetic magnitude |B|"):
    if df.empty:
        plt.figure()
        plt.text(0.5, 0.5, "No data", ha="center")
        plt.savefig(outpath)
        plt.close()
        return
    B = np.sqrt(df["mx"] ** 2 + df["my"] ** 2 + df["mz"] ** 2)
    plt.figure(figsize=(6, 3))
    plt.plot(df["time"], B, "-", lw=1)
    plt.xlabel("time (s)")
    plt.ylabel("|B|")
    plt.title(title)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()


def plot_axes(df: pd.DataFrame, outpath: str, title: str = "Raw axes"):
    plt.figure(figsize=(6, 3))
    if df.empty:
        plt.text(0.5, 0.5, "No data", ha="center")
    else:
        plt.plot(df["time"], df["mx"], label="mx", lw=1)
        plt.plot(df["time"], df["my"], label="my", lw=1)
        plt.plot(df["time"], df["mz"], label="mz", lw=1)
        plt.xlabel("time (s)")
        plt.ylabel("magnetic (units)")
        plt.legend()
        plt.grid(True, alpha=0.3)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()


def plot_heading(df: pd.DataFrame, outpath: str, title: str = "Heading (deg)"):
    plt.figure(figsize=(6, 3))
    if df.empty:
        plt.text(0.5, 0.5, "No data", ha="center")
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
