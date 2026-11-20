"""Weighted KPIs verified independently against SQL and hand-built frames."""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import analytics, cleaning, config, data_loader  # noqa: E402

DEDUP_SQL = (
    "performance_id IN (SELECT MIN(performance_id) FROM performance_fact "
    "GROUP BY programme_id, period_id, course_id)"
)


def sql_scalar(sql, params=()):
    conn = sqlite3.connect(config.DB_PATH)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


@pytest.fixture(scope="module")
def raw():
    return data_loader.load_performance(config.PROGRAMME_CODES)


@pytest.fixture(scope="module")
def clean(raw):
    return cleaning.deduplicate(raw)


# ---------------------------------------------------------------------------
# Independent SQL verification (cleaned dataset)
# ---------------------------------------------------------------------------
def test_attendance_matches_sql(clean):
    expected = sql_scalar(
        "SELECT 100.0 * SUM(attendance_present_count) / NULLIF(SUM(attendance_eligible_count), 0) "
        f"FROM performance_fact WHERE {DEDUP_SQL}")
    assert analytics.overall_attendance_pct(clean) == pytest.approx(expected, abs=1e-9)


def test_average_assessment_matches_sql(clean):
    expected = sql_scalar(
        "SELECT SUM((average_marks / maximum_marks) * 100.0 * assessed_count) / NULLIF(SUM(assessed_count), 0) "
        f"FROM performance_fact WHERE average_marks IS NOT NULL AND {DEDUP_SQL}")
    assert analytics.average_assessment_pct(clean) == pytest.approx(expected, abs=1e-9)


def test_pass_matches_sql(clean):
    expected = sql_scalar(
        "SELECT 100.0 * SUM(passed_count) / NULLIF(SUM(appeared_count), 0) "
        f"FROM performance_fact WHERE {DEDUP_SQL}")
    assert analytics.pass_pct(clean) == pytest.approx(expected, abs=1e-9)


def test_project_completion_matches_sql(clean):
    expected = sql_scalar(
        "SELECT 100.0 * SUM(projects_completed) / NULLIF(SUM(projects_assigned), 0) FROM performance_fact "
        f"WHERE projects_assigned > 0 AND projects_completed IS NOT NULL AND {DEDUP_SQL}")
    assert analytics.project_completion_pct(clean) == pytest.approx(expected, abs=1e-9)


def test_practical_matches_sql(clean):
    expected = sql_scalar(
        "SELECT SUM((practical_average_score / practical_max_marks) * 100.0 * assessed_count) "
        "/ NULLIF(SUM(assessed_count), 0) FROM performance_fact "
        f"WHERE practical_average_score IS NOT NULL AND {DEDUP_SQL}")
    assert analytics.practical_average_pct(clean) == pytest.approx(expected, abs=1e-9)


def test_raw_mode_matches_sql_without_dedup(raw):
    expected = sql_scalar("SELECT 100.0 * SUM(passed_count) / SUM(appeared_count) FROM performance_fact")
    assert analytics.pass_pct(raw) == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("code", ["BTECH", "MCA", "BCA", "MBA"])
def test_programme_attendance_matches_sql(clean, code):
    expected = sql_scalar(
        "SELECT 100.0 * SUM(pf.attendance_present_count) / SUM(pf.attendance_eligible_count) "
        "FROM performance_fact pf JOIN programme_master pm ON pm.programme_id = pf.programme_id "
        f"WHERE pm.programme_code = ? AND pf.{DEDUP_SQL}", (code,))
    table = analytics.grouped_kpis(clean, "programme_code").set_index("programme_code")
    assert table.loc[code, "attendance"] == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------------------
# Formula semantics on hand-built frames
# ---------------------------------------------------------------------------
def frame(rows):
    base = {c: np.nan for c in config.EXPECTED_VIEW_COLUMNS}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_weighted_not_unweighted_mean():
    df = frame([
        dict(attendance_present_count=90, attendance_eligible_count=100, passed_count=9, appeared_count=10,
             average_marks=40, maximum_marks=50, assessed_count=10, enrolled_count=10),
        dict(attendance_present_count=500, attendance_eligible_count=1000, passed_count=50, appeared_count=100,
             average_marks=50, maximum_marks=100, assessed_count=100, enrolled_count=100),
    ])
    assert analytics.overall_attendance_pct(df) == pytest.approx(590 / 1100 * 100)
    assert analytics.overall_attendance_pct(df) != pytest.approx((90 + 50) / 2)
    assert analytics.pass_pct(df) == pytest.approx(59 / 110 * 100)
    # (80% * 10 + 50% * 100) / 110
    assert analytics.average_assessment_pct(df) == pytest.approx((80 * 10 + 50 * 100) / 110)
    assert analytics.total_course_seat_enrolments(df) == 110


def test_null_marks_excluded_not_zeroed():
    df = frame([
        dict(average_marks=40, maximum_marks=50, assessed_count=10),
        dict(average_marks=np.nan, maximum_marks=50, assessed_count=90),
    ])
    assert analytics.average_assessment_pct(df) == pytest.approx(80.0)


def test_project_and_practical_not_available_when_no_records():
    df = frame([dict(attendance_present_count=5, attendance_eligible_count=10, passed_count=1,
                     appeared_count=2, assessed_count=2, enrolled_count=2)])
    assert analytics.project_completion_pct(df) is None
    assert analytics.practical_average_pct(df) is None
    df2 = frame([dict(projects_assigned=5, projects_completed=np.nan),
                 dict(projects_assigned=0, projects_completed=0)])
    assert analytics.project_completion_pct(df2) is None


def test_project_completion_ignores_null_completed():
    df = frame([dict(projects_assigned=10, projects_completed=8),
                dict(projects_assigned=10, projects_completed=np.nan)])
    assert analytics.project_completion_pct(df) == pytest.approx(80.0)


def test_extremes_return_ties():
    df = frame([
        dict(programme_name="A", passed_count=9, appeared_count=10),
        dict(programme_name="B", passed_count=18, appeared_count=20),
        dict(programme_name="C", passed_count=5, appeared_count=10),
    ])
    ext = analytics.kpi_extremes(df, "programme_name", "pass")
    assert sorted(ext["highest"]) == ["A", "B"] and ext["highest_value"] == pytest.approx(90.0)
    assert ext["lowest"] == ["C"] and ext["lowest_value"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# KPI-07 period deltas in pp
# ---------------------------------------------------------------------------
def sql_period_pass(seq):
    return sql_scalar(
        "SELECT 100.0 * SUM(pf.passed_count) / SUM(pf.appeared_count) FROM performance_fact pf "
        "JOIN academic_period_master ap ON ap.period_id = pf.period_id "
        f"WHERE ap.period_sequence = ? AND pf.{DEDUP_SQL}", (seq,))


def test_period_trend_ordered_and_pp_deltas(clean):
    trend = analytics.period_deltas(analytics.period_trend(clean))
    assert trend["period_sequence"].tolist() == [1, 2, 3, 4]
    assert trend["period_label"].tolist() == list(config.PERIOD_LABELS)
    assert np.isnan(trend.loc[0, "pass_pp"])
    for i in range(1, 4):
        expected = sql_period_pass(i + 1) - sql_period_pass(i)
        assert trend.loc[i, "pass_pp"] == pytest.approx(expected, abs=1e-9)
        assert trend.loc[i, "attendance_pp"] == pytest.approx(
            trend.loc[i, "attendance"] - trend.loc[i - 1, "attendance"])


def test_latest_vs_prior(clean):
    res = analytics.latest_vs_prior(clean, [1, 2, 3, 4])
    assert res["current_label"] == "2026-27 Sem 2" and res["prior_label"] == "2026-27 Sem 1"
    assert res["pass"]["pp"] == pytest.approx(sql_period_pass(4) - sql_period_pass(3), abs=1e-9)
    first = analytics.latest_vs_prior(clean, [1])
    assert first["prior_label"] is None and first["pass"]["pp"] is None


def test_grouped_deltas_by_programme(clean):
    d = analytics.period_deltas(analytics.period_trend(clean, "programme_name"), ["pass"], by="programme_name")
    for _, grp in d.groupby("programme_name"):
        grp = grp.sort_values("period_sequence")
        assert np.isnan(grp["pass_pp"].iloc[0])
        assert np.allclose(grp["pass_pp"].iloc[1:].to_numpy(), np.diff(grp["pass"].to_numpy()))


def test_assessment_breakdown_scales(clean):
    b = analytics.assessment_breakdown(clean).set_index("assessment_type")
    assert b.loc["Internal", "scale"] == "/50" and b.loc["End-Semester", "scale"] == "/100"
    for t in b.index:
        sub = clean[clean["assessment_type"] == t]
        assert b.loc[t, "assessment"] == pytest.approx(analytics.average_assessment_pct(sub))


def test_raw_vs_cleaned_table(raw):
    t = analytics.raw_vs_cleaned(raw).set_index("metric")
    assert t.loc["Records (course-period rows)", "impact"] == -3
    key = f"{config.KPI_IDS['pass']} {config.KPI_LABELS['pass']}"
    assert t.loc[key, "impact"] == pytest.approx(t.loc[key, "cleaned"] - t.loc[key, "raw"])
