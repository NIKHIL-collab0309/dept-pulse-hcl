"""Live data-validation checks on view-shaped DataFrames (no UI code)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd

from src import config


def missing_value_summary(df: pd.DataFrame, columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Count NULLs per column. Structural NULLs (e.g. project fields on theory courses) are reported too."""
    cols = list(columns) if columns is not None else list(df.columns)
    out = pd.DataFrame({
        "column": cols,
        "null_count": [int(df[c].isna().sum()) for c in cols],
        "row_count": len(df),
    })
    out["null_pct"] = (out["null_count"] / out["row_count"].where(out["row_count"] > 0) * 100).round(2)
    return out


def missing_marks_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows where average_marks is NULL (DQ-MISSING)."""
    return df.loc[df["average_marks"].isna()].copy()


def find_duplicate_keys(df: pd.DataFrame, keys: Sequence[str] = config.GRAIN_COLUMNS) -> pd.DataFrame:
    """All rows sharing a (programme_id, period_id, course_id) grain with another row."""
    mask = df.duplicated(subset=list(keys), keep=False)
    return df.loc[mask].sort_values(list(keys) + ["performance_id"]).copy()


def duplicate_pairs(df: pd.DataFrame, keys: Sequence[str] = config.GRAIN_COLUMNS) -> pd.DataFrame:
    """Map each surplus row to the primary (lowest performance_id) row of its grain."""
    dups = find_duplicate_keys(df, keys)
    if dups.empty:
        return pd.DataFrame(columns=["primary_performance_id", "duplicate_performance_id", *keys])
    rows = []
    for key, grp in dups.groupby(list(keys), sort=True):
        ids = sorted(int(i) for i in grp["performance_id"])
        for dup_id in ids[1:]:
            rows.append({"primary_performance_id": ids[0], "duplicate_performance_id": dup_id,
                         **dict(zip(keys, key))})
    return pd.DataFrame(rows)


def range_violations(
    df: pd.DataFrame, columns: Iterable[str] = config.PCT_METRICS, low: float = 0.0, high: float = 100.0
) -> pd.DataFrame:
    """Rows whose non-NULL percentage values fall outside [low, high]."""
    frames = []
    for col in columns:
        s = df[col]
        bad = df.loc[s.notna() & ((s < low) | (s > high)), ["performance_id", col]]
        if not bad.empty:
            frames.append(bad.rename(columns={col: "value"}).assign(column=col))
    if not frames:
        return pd.DataFrame(columns=["performance_id", "value", "column"])
    return pd.concat(frames, ignore_index=True)


def consistency_violations(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-field reconciliation rules (count relationships)."""
    rules = {
        "present > eligible": df["attendance_present_count"] > df["attendance_eligible_count"],
        "passed > appeared": df["passed_count"] > df["appeared_count"],
        "assessed > enrolled": df["assessed_count"] > df["enrolled_count"],
        "appeared > assessed": df["appeared_count"] > df["assessed_count"],
        "completed > assigned": df["projects_completed"].notna()
        & (df["projects_completed"] > df["projects_assigned"]),
        "marks > maximum": df["average_marks"].notna() & (df["average_marks"] > df["maximum_marks"]),
    }
    frames = [df.loc[mask, ["performance_id"]].assign(rule=name) for name, mask in rules.items() if mask.any()]
    if not frames:
        return pd.DataFrame(columns=["performance_id", "rule"])
    return pd.concat(frames, ignore_index=True)


def all_synthetic(df: pd.DataFrame) -> bool:
    return bool(len(df) > 0 and (df["is_synthetic"] == 1).all())


def schema_matches(columns: Sequence[str]) -> bool:
    return tuple(columns) == config.EXPECTED_VIEW_COLUMNS


def run_all_checks(df: pd.DataFrame) -> pd.DataFrame:
    """One summary row per check: name, status (PASS/WARN/FAIL), affected rows, detail."""
    n_missing = int(df["average_marks"].isna().sum())
    dup = duplicate_pairs(df)
    rng = range_violations(df)
    cons = consistency_violations(df)
    rows = [
        {"check": "Missing average_marks (DQ-MISSING)", "status": "WARN" if n_missing else "PASS",
         "affected_rows": n_missing,
         "detail": "Excluded from KPI-02 denominator; never coerced to 0."},
        {"check": "Duplicate course-period grain (DQ-DUPLICATE)", "status": "WARN" if len(dup) else "PASS",
         "affected_rows": len(dup),
         "detail": "Cleaned mode keeps the lowest performance_id per (programme, period, course)."},
        {"check": "Percentages within 0–100 (DQ-RANGE)", "status": "FAIL" if len(rng) else "PASS",
         "affected_rows": len(rng), "detail": "All five view percentage columns."},
        {"check": "Count reconciliation rules", "status": "WARN" if len(cons) else "PASS",
         "affected_rows": int(cons["performance_id"].nunique()) if len(cons) else 0,
         "detail": ", ".join(sorted(cons["rule"].unique())) if len(cons) else "All count relationships hold."},
        {"check": "is_synthetic = 1 on every row", "status": "PASS" if all_synthetic(df) else "FAIL",
         "affected_rows": int((df["is_synthetic"] != 1).sum()), "detail": f"Dataset {config.DATA_VERSION}."},
        {"check": "Data version", "status": "PASS" if set(df["data_version"].unique()) <= {config.DATA_VERSION} else "WARN",
         "affected_rows": int((df["data_version"] != config.DATA_VERSION).sum()),
         "detail": ", ".join(sorted(map(str, df["data_version"].unique())))},
    ]
    return pd.DataFrame(rows)
