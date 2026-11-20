"""Descriptive statistics and EDA helpers (row-level, course-period records).

These describe the *distribution of row percentages*; they complement but never
replace the weighted KPIs in ``src/analytics.py``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd
from scipy import stats as sps

from src import config

IQR_MULTIPLIER = 1.5


def describe_series(values: pd.Series | Sequence[float]) -> dict[str, float | int | None]:
    """count, mean, median, min, max, sample std (ddof=1), Q1, Q3, IQR and Tukey fences."""
    s = pd.to_numeric(pd.Series(values), errors="coerce").dropna().astype("float64")
    n = int(s.size)
    if n == 0:
        keys = ["mean", "median", "min", "max", "std", "q1", "q3", "iqr", "lower_fence", "upper_fence",
                "skewness"]
        return {"count": 0, **{k: None for k in keys}, "outliers": 0}
    q1, q3 = (float(v) for v in np.percentile(s.to_numpy(), [25, 75], method="linear"))
    iqr = q3 - q1
    lower, upper = q1 - IQR_MULTIPLIER * iqr, q3 + IQR_MULTIPLIER * iqr
    return {
        "count": n,
        "mean": float(s.mean()),
        "median": float(s.median()),
        "min": float(s.min()),
        "max": float(s.max()),
        "std": float(s.std(ddof=1)) if n > 1 else None,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "lower_fence": lower,
        "upper_fence": upper,
        "skewness": float(sps.skew(s.to_numpy(), bias=False)) if n > 2 and s.nunique() > 1 else None,
        "outliers": int(((s < lower) | (s > upper)).sum()),
    }


def describe_metrics(df: pd.DataFrame, metrics: Iterable[str] = config.PCT_METRICS) -> pd.DataFrame:
    rows = []
    for m in metrics:
        d = describe_series(df[m]) if m in df else describe_series([])
        rows.append({"metric": m, "label": config.METRIC_LABELS.get(m, m), **d})
    return pd.DataFrame(rows)


def iqr_fences(values: pd.Series) -> tuple[float | None, float | None]:
    d = describe_series(values)
    return d["lower_fence"], d["upper_fence"]


def flag_iqr_outliers(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Copy of ``df`` with ``is_outlier`` / ``outlier_side`` for ``metric`` (NULLs are never flagged)."""
    lower, upper = iqr_fences(df[metric])
    out = df.copy()
    s = pd.to_numeric(out[metric], errors="coerce")
    if lower is None:
        out["is_outlier"] = False
        out["outlier_side"] = None
        return out
    low_mask = s.notna() & (s < lower)
    high_mask = s.notna() & (s > upper)
    out["is_outlier"] = low_mask | high_mask
    out["outlier_side"] = np.select([low_mask, high_mask], ["Below lower fence", "Above upper fence"], default=None)
    return out


def iqr_outlier_scan(df: pd.DataFrame, metrics: Iterable[str] = config.PCT_METRICS,
                     id_columns: Sequence[str] = ("performance_id", "programme_name", "period_label",
                                                  "course_code", "course_category")) -> pd.DataFrame:
    """Long table of every IQR outlier across ``metrics``."""
    frames = []
    for m in metrics:
        flagged = flag_iqr_outliers(df, m)
        lower, upper = iqr_fences(df[m])
        hit = flagged.loc[flagged["is_outlier"], [c for c in id_columns if c in flagged] + [m, "outlier_side"]]
        if hit.empty:
            continue
        frames.append(hit.rename(columns={m: "value"}).assign(metric=m, lower_fence=lower, upper_fence=upper))
    cols = [*[c for c in id_columns if c in df], "metric", "value", "lower_fence", "upper_fence", "outlier_side"]
    if not frames:
        return pd.DataFrame(columns=cols)
    return pd.concat(frames, ignore_index=True)[cols]


def correlation_matrix(df: pd.DataFrame, metrics: Iterable[str] = config.PCT_METRICS,
                       min_periods: int = 3) -> pd.DataFrame:
    """Pearson correlation with pairwise-complete observations (NULLs dropped per pair)."""
    cols = [m for m in metrics if m in df]
    return df[cols].apply(pd.to_numeric, errors="coerce").corr(method="pearson", min_periods=min_periods)


def pairwise_n(df: pd.DataFrame, metrics: Iterable[str] = config.PCT_METRICS) -> pd.DataFrame:
    cols = [m for m in metrics if m in df]
    notna = df[cols].notna().astype(int)
    return notna.T @ notna


def pearson_test(x: pd.Series, y: pd.Series) -> dict[str, float | int | None]:
    pair = pd.concat([pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")], axis=1).dropna()
    n = len(pair)
    if n < 3 or pair.iloc[:, 0].nunique() < 2 or pair.iloc[:, 1].nunique() < 2:
        return {"n": n, "r": None, "p_value": None}
    res = sps.pearsonr(pair.iloc[:, 0], pair.iloc[:, 1])
    return {"n": n, "r": float(res.statistic), "p_value": float(res.pvalue)}


def ols_fit(x: pd.Series, y: pd.Series) -> dict[str, float | int | None]:
    """Simple OLS y ~ x via statsmodels (slope in pp of y per pp of x)."""
    import statsmodels.api as sm

    pair = pd.concat([pd.to_numeric(x, errors="coerce"), pd.to_numeric(y, errors="coerce")], axis=1).dropna()
    if len(pair) < 3 or pair.iloc[:, 0].nunique() < 2:
        return {"n": len(pair), "slope": None, "intercept": None, "r_squared": None, "p_value": None}
    model = sm.OLS(pair.iloc[:, 1].to_numpy(), sm.add_constant(pair.iloc[:, 0].to_numpy())).fit()
    return {
        "n": int(model.nobs),
        "intercept": float(model.params[0]),
        "slope": float(model.params[1]),
        "r_squared": float(model.rsquared),
        "p_value": float(model.pvalues[1]),
    }
