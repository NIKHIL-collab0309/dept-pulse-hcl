"""Deterministic deduplication without NULL coercion."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import cleaning, config, data_loader  # noqa: E402

GRAIN = list(config.GRAIN_COLUMNS)


@pytest.fixture(scope="module")
def raw():
    return data_loader.load_performance(config.PROGRAMME_CODES)


def test_dedup_reduces_195_to_192_unique_grain_rows(raw):
    clean = cleaning.deduplicate(raw)
    assert len(raw) == 195
    assert len(clean) == 192
    assert not clean.duplicated(subset=GRAIN).any()
    assert clean[GRAIN].drop_duplicates().shape[0] == 192


def test_keeps_lowest_performance_id(raw):
    removed = cleaning.removed_rows(raw)
    assert sorted(removed["performance_id"].astype(int)) == [193, 194, 195]
    kept = set(cleaning.deduplicate(raw)["performance_id"].astype(int))
    assert {15, 62, 118} <= kept


def test_nulls_not_coerced_to_zero(raw):
    clean = cleaning.deduplicate(raw)
    assert clean["average_marks"].isna().sum() == raw["average_marks"].isna().sum() == 5
    null_ids = set(raw.loc[raw["average_marks"].isna(), "performance_id"])
    assert clean.loc[clean["performance_id"].isin(null_ids), "average_marks"].isna().all()
    for col in ("projects_assigned", "projects_completed", "practical_average_score", "practical_max_marks"):
        raw_kept = raw[raw["performance_id"].isin(clean["performance_id"])]
        assert clean[col].isna().sum() == raw_kept[col].isna().sum()
        assert (clean[col] == 0).sum() == (raw_kept[col] == 0).sum()


def test_deterministic_and_idempotent(raw):
    a = cleaning.deduplicate(raw)
    b = cleaning.deduplicate(raw.sample(frac=1.0, random_state=7))
    assert sorted(a["performance_id"]) == sorted(b["performance_id"])
    assert cleaning.deduplicate(a)["performance_id"].tolist() == a["performance_id"].tolist()


def test_values_of_kept_rows_unchanged(raw):
    clean = cleaning.deduplicate(raw).set_index("performance_id")
    original = raw.set_index("performance_id").loc[clean.index]
    assert clean.equals(original)


def test_dataset_modes(raw):
    assert len(cleaning.apply_dataset_mode(raw, config.MODE_RAW)) == 195
    assert len(cleaning.apply_dataset_mode(raw, config.MODE_CLEANED)) == 192
    with pytest.raises(ValueError):
        cleaning.apply_dataset_mode(raw, "Something else")


def test_cleaning_summary(raw):
    s = cleaning.cleaning_summary(raw)
    assert s == {"raw_rows": 195, "cleaned_rows": 192, "removed_duplicates": 3,
                 "null_average_marks_raw": 5, "null_average_marks_cleaned": 5}


@pytest.mark.parametrize("code", ["BTECH", "MCA", "BCA", "MBA"])
def test_each_programme_dedups_to_12_courses_x_4_periods(code):
    scoped = data_loader.load_performance([code])
    assert len(cleaning.deduplicate(scoped)) == 48
