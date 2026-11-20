"""Deterministic cleaning.

Only one transformation is applied: removal of surplus rows that repeat a
(programme_id, period_id, course_id) grain, keeping the lowest performance_id.
NULLs are never filled — they stay NULL and are excluded per-metric downstream
(BRL-07 / BRL-08).
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from src import config


def deduplicate(df: pd.DataFrame, keys: Sequence[str] = config.GRAIN_COLUMNS) -> pd.DataFrame:
    """Keep the primary (lowest performance_id) row per grain. Order-independent and idempotent."""
    if df.empty:
        return df.copy()
    ordered = df.sort_values("performance_id", kind="mergesort")
    kept = ordered.drop_duplicates(subset=list(keys), keep="first")
    return kept.sort_index().copy()


def removed_rows(df: pd.DataFrame, keys: Sequence[str] = config.GRAIN_COLUMNS) -> pd.DataFrame:
    """Rows that ``deduplicate`` drops."""
    kept_ids = set(deduplicate(df, keys)["performance_id"])
    return df.loc[~df["performance_id"].isin(kept_ids)].copy()


def apply_dataset_mode(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    if mode == config.MODE_RAW:
        return df.copy()
    if mode == config.MODE_CLEANED:
        return deduplicate(df)
    raise ValueError(f"Unknown dataset mode: {mode!r}")


def cleaning_summary(df: pd.DataFrame) -> dict[str, int]:
    clean = deduplicate(df)
    return {
        "raw_rows": len(df),
        "cleaned_rows": len(clean),
        "removed_duplicates": len(df) - len(clean),
        "null_average_marks_raw": int(df["average_marks"].isna().sum()),
        "null_average_marks_cleaned": int(clean["average_marks"].isna().sum()),
    }
