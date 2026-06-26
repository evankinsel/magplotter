"""
Transformation stage: derive secondary quantities from cleaned magnetometer data.

Pure function — no file I/O, no side effects.

Functions:
    transform_sensor_data(df) -> pd.DataFrame
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def transform_sensor_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of df with two derived columns appended:

    magnitude   – total field strength sqrt(mx² + my² + mz²) in the same
                  units as the input axes (typically µT).
    heading_deg – horizontal bearing atan2(my, mx) normalised to [0, 360).

    Downstream analysis and visualisation consume these columns rather than
    recomputing the same values independently.
    """
    if df.empty:
        out = df.copy()
        out["magnitude"] = pd.Series(dtype=float)
        out["heading_deg"] = pd.Series(dtype=float)
        logger.debug("transform: empty DataFrame — derived columns added as empty series")
        return out

    out = df.copy()
    mx = df["mx"].astype(float)
    my = df["my"].astype(float)
    mz = df["mz"].astype(float)

    out["magnitude"] = np.sqrt(mx**2 + my**2 + mz**2)
    out["heading_deg"] = (np.rad2deg(np.arctan2(my, mx)) + 360.0) % 360.0

    logger.debug(
        "transform: %d rows — magnitude [%.2f, %.2f] µT, heading [%.1f, %.1f]°",
        len(out),
        float(out["magnitude"].min()),
        float(out["magnitude"].max()),
        float(out["heading_deg"].min()),
        float(out["heading_deg"].max()),
    )
    return out
