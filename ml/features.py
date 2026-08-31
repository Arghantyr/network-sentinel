"""Feature engineering shared by training and evaluation."""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = (
    "duration_s", "bytes_out", "bytes_in", "packets", "dst_port",
    "failed_connections", "out_in_ratio",
)
REQUIRED_RAW_COLUMNS = frozenset(FEATURE_COLUMNS) - {"out_in_ratio"}


def make_features(records: pd.DataFrame) -> pd.DataFrame:
    """Return numeric model features without modifying the input dataframe."""
    missing = REQUIRED_RAW_COLUMNS - set(records.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    features = records.copy()
    features["out_in_ratio"] = (features["bytes_out"] + 1) / (features["bytes_in"] + 1)
    return (features.loc[:, FEATURE_COLUMNS]
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .astype(float))
