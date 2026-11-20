"""Descriptive statistics, IQR fences and correlation."""

import statistics as pystats
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import cleaning, config, data_loader  # noqa: E402
from src import statistics as st_mod  # noqa: E402

SAMPLE = [1.0, 2.0, 3.0, 4.0, 100.0]


def test_describe_known_sample():
    d = st_mod.describe_series(SAMPLE)
    assert d["count"] == 5
    assert d["mean"] == pytest.approx(22.0)
    assert d["median"] == pytest.approx(3.0)
    assert d["min"] == 1.0 and d["max"] == 100.0
    assert d["std"] == pytest.approx(pystats.stdev(SAMPLE))  # sample std, ddof=1
    assert d["std"] != pytest.approx(pystats.pstdev(SAMPLE))
    assert d["q1"] == pytest.approx(2.0) and d["q3"] == pytest.approx(4.0)
    assert d["iqr"] == pytest.approx(2.0)
    assert d["lower_fence"] == pytest.approx(-1.0) and d["upper_fence"] == pytest.approx(7.0)
    assert d["outliers"] == 1


def test_nulls_dropped_not_zeroed():
    d = st_mod.describe_series([10.0, np.nan, 20.0, None, 30.0])
    assert d["count"] == 3 and d["mean"] == pytest.approx(20.0) and d["min"] == 10.0


def test_empty_and_single():
    assert st_mod.describe_series([])["count"] == 0
    one = st_mod.describe_series([5.0])
    assert one["count"] == 1 and one["std"] is None and one["iqr"] == 0.0


def test_matches_pandas_on_real_metrics():
    df = cleaning.deduplicate(data_loader.load_performance(config.PROGRAMME_CODES))
    for m in config.PCT_METRICS:
        s = df[m].dropna()
        d = st_mod.describe_series(df[m])
        assert d["count"] == len(s)
        assert d["mean"] == pytest.approx(s.mean())
        assert d["median"] == pytest.approx(s.median())
        assert d["std"] == pytest.approx(s.std(ddof=1))
        assert d["q1"] == pytest.approx(s.quantile(0.25))
        assert d["q3"] == pytest.approx(s.quantile(0.75))
        assert d["iqr"] == pytest.approx(s.quantile(0.75) - s.quantile(0.25))
        lo, hi = d["lower_fence"], d["upper_fence"]
        assert d["outliers"] == int(((s < lo) | (s > hi)).sum())


def test_flag_outliers():
    df = pd.DataFrame({"x": SAMPLE + [np.nan]})
    flagged = st_mod.flag_iqr_outliers(df, "x")
    assert flagged["is_outlier"].tolist() == [False, False, False, False, True, False]
    assert flagged.loc[4, "outlier_side"] == "Above upper fence"


def test_outlier_scan_long_format():
    df = cleaning.deduplicate(data_loader.load_performance(config.PROGRAMME_CODES))
    scan = st_mod.iqr_outlier_scan(df)
    desc = st_mod.describe_metrics(df).set_index("metric")
    for m in config.PCT_METRICS:
        assert (scan["metric"] == m).sum() == desc.loc[m, "outliers"]
    assert ((scan["value"] < scan["lower_fence"]) | (scan["value"] > scan["upper_fence"])).all()


def test_correlation_and_ols():
    x = pd.Series([1, 2, 3, 4, 5], dtype=float)
    df = pd.DataFrame({"attendance_pct": x, "average_marks_pct": 2 * x + 1, "pass_pct": -x,
                       "project_completion_pct": np.nan, "practical_score_pct": np.nan})
    corr = st_mod.correlation_matrix(df)
    assert corr.loc["attendance_pct", "average_marks_pct"] == pytest.approx(1.0)
    assert corr.loc["attendance_pct", "pass_pct"] == pytest.approx(-1.0)
    assert np.isnan(corr.loc["attendance_pct", "project_completion_pct"])
    fit = st_mod.ols_fit(df["attendance_pct"], df["average_marks_pct"])
    assert fit["slope"] == pytest.approx(2.0) and fit["intercept"] == pytest.approx(1.0)
    assert fit["r_squared"] == pytest.approx(1.0)
    test = st_mod.pearson_test(df["attendance_pct"], df["pass_pct"])
    assert test["r"] == pytest.approx(-1.0) and test["n"] == 5
