"""Validation checks: missing values, duplicate keys, ranges and synthetic flag."""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config, data_loader, validation  # noqa: E402


@pytest.fixture(scope="module")
def raw():
    return data_loader.load_performance(config.PROGRAMME_CODES)


def test_detects_five_missing_average_marks(raw):
    missing = validation.missing_marks_rows(raw)
    assert len(missing) == 5
    summary = validation.missing_value_summary(raw, ["average_marks"]).iloc[0]
    assert summary["null_count"] == 5 and summary["row_count"] == 195
    logged = data_loader.load_quality_issues(config.PROGRAMME_CODES)
    logged_missing = set(logged.loc[logged["issue_code"] == "DQ-MISSING", "performance_id"].astype(int))
    assert set(missing["performance_id"].astype(int)) == logged_missing


def test_detects_duplicate_course_period_keys(raw):
    dups = validation.find_duplicate_keys(raw)
    assert len(dups) == 6  # 3 primaries + 3 re-entries
    pairs = validation.duplicate_pairs(raw)
    mapping = dict(zip(pairs["primary_performance_id"], pairs["duplicate_performance_id"]))
    assert mapping == {15: 193, 62: 194, 118: 195}


def test_percentages_within_0_100(raw):
    assert validation.range_violations(raw).empty
    for col in config.PCT_METRICS:
        s = raw[col].dropna()
        assert ((s >= 0) & (s <= 100)).all()


def test_range_check_flags_tampered_values(raw):
    bad = raw.head(3).copy()
    bad.loc[bad.index[0], "attendance_pct"] = 120.0
    bad.loc[bad.index[1], "pass_pct"] = -5.0
    viol = validation.range_violations(bad)
    assert set(viol["column"]) == {"attendance_pct", "pass_pct"}
    assert len(viol) == 2


def test_all_rows_synthetic(raw):
    assert validation.all_synthetic(raw)
    assert (raw["is_synthetic"] == 1).all()
    assert set(raw["data_version"]) == {config.DATA_VERSION}
    tampered = raw.head(2).copy()
    tampered["is_synthetic"] = [1, 0]
    assert not validation.all_synthetic(tampered)


def test_consistency_rules(raw):
    cons = validation.consistency_violations(raw)
    # Hard rules guaranteed by the schema CHECK constraints must never fire
    for rule in ("present > eligible", "passed > appeared", "assessed > enrolled",
                 "completed > assigned", "marks > maximum"):
        assert not (cons["rule"] == rule).any(), rule
    # A tampered frame is caught
    bad = raw.head(1).copy()
    bad["passed_count"] = bad["appeared_count"] + 1
    assert "passed > appeared" in set(validation.consistency_violations(bad)["rule"])


def test_schema_contract():
    assert validation.schema_matches(data_loader.view_columns())
    assert not validation.schema_matches(list(config.EXPECTED_VIEW_COLUMNS)[:-1])


def test_run_all_checks_summary(raw):
    summary = validation.run_all_checks(raw).set_index("check")
    assert summary.loc["Missing average_marks (DQ-MISSING)", "affected_rows"] == 5
    assert summary.loc["Duplicate course-period grain (DQ-DUPLICATE)", "affected_rows"] == 3
    assert summary.loc["Percentages within 0–100 (DQ-RANGE)", "status"] == "PASS"
    assert summary.loc["is_synthetic = 1 on every row", "status"] == "PASS"


def test_empty_frame_handled():
    empty = pd.DataFrame(columns=list(config.EXPECTED_VIEW_COLUMNS))
    assert validation.find_duplicate_keys(empty).empty
    assert not validation.all_synthetic(empty)
