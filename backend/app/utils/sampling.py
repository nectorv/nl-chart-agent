from __future__ import annotations

import random

import pandas as pd

from .logger import get_logger

logger = get_logger(__name__)

MAX_ROWS = 500


def sample_dataframe(df: pd.DataFrame, run_id: str = "") -> pd.DataFrame:
    original = len(df)
    if original <= MAX_ROWS:
        return df

    temporal_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]

    if temporal_cols:
        df = df.sort_values(temporal_cols[0])
        indices = [int(i * (original - 1) / (MAX_ROWS - 1)) for i in range(MAX_ROWS)]
        sampled = df.iloc[indices].reset_index(drop=True)
    else:
        sampled = df.sample(n=MAX_ROWS, random_state=42).reset_index(drop=True)

    logger.info(
        "Sampled dataframe run_id=%s original=%d sampled=%d",
        run_id,
        original,
        MAX_ROWS,
    )
    return sampled
