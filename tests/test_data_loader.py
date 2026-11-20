"""SQLite connection, schema contract and parameterised filtering."""

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config, data_loader  # noqa: E402


def test_db_path_resolved_from_repo_root():
    assert config.DB_PATH == ROOT / "data" / "app.db"
    assert config.DB_PATH.exists(), "run `python src/generate_data.py` first"


def test_connection_enables_foreign_keys():
    with data_loader.connection() as conn:
        assert conn.execute("PRAGMA foreign_keys;").fetchone()[0] == 1
    assert data_loader.foreign_keys_enabled()


def test_connection_is_read_only():
    with data_loader.connection() as conn, pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM programme_master")


def test_missing_database_raises_helpful_error(tmp_path):
    with pytest.raises(data_loader.DatabaseNotFoundError):
        data_loader.get_connection(tmp_path / "nope.db")
    assert not (tmp_path / "nope.db").exists()


def test_table_counts():
    assert data_loader.table_counts() == {
        "programme_master": 4, "academic_period_master": 4, "course_master": 48,
        "performance_fact": 195, "data_quality_issue": 24,
    }


def test_view_schema_has_39_columns_in_contract_order():
    cols = data_loader.view_columns()
    assert len(cols) == 39
    assert tuple(cols) == config.EXPECTED_VIEW_COLUMNS
    df = data_loader.load_performance(config.PROGRAMME_CODES)
    assert df.shape == (195, 39)


def test_schema_sql_matches_generator_ddl():
    import ast

    tree = ast.parse((ROOT / "src" / "generate_data.py").read_text(encoding="utf-8"))
    ddl = next(n.value.value for n in tree.body
               if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "DDL_SCRIPT")
    assert ddl.strip() in (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")


def test_master_values():
    periods = data_loader.load_periods()
    assert periods["period_label"].tolist() == list(config.PERIOD_LABELS)
    assert periods["period_sequence"].tolist() == [1, 2, 3, 4]
    progs = data_loader.load_programmes(config.PROGRAMME_CODES)
    assert progs["programme_code"].tolist() == ["BTECH", "MCA", "BCA", "MBA"]


@pytest.mark.parametrize("code", ["BTECH", "MCA", "BCA", "MBA"])
def test_parameterised_programme_filter(code):
    df = data_loader.load_performance([code])
    assert set(df["programme_code"]) == {code}
    courses = data_loader.load_courses([code])
    assert len(courses) == 12 and set(courses["programme_code"]) == {code}


def test_multi_programme_filter_and_row_totals():
    df = data_loader.load_performance(["MCA", "MBA"])
    assert set(df["programme_code"]) == {"MCA", "MBA"}
    per_code = {c: len(data_loader.load_performance([c])) for c in config.PROGRAMME_CODES}
    assert sum(per_code.values()) == 195
    assert all(n >= 48 for n in per_code.values())  # 12 courses x 4 periods, plus any re-entries


@pytest.mark.parametrize("bad", [[], ["CSE"], ["MCA' OR '1'='1"], ["MCA; DROP TABLE performance_fact;--"]])
def test_invalid_or_injected_codes_rejected(bad):
    with pytest.raises(ValueError):
        data_loader.load_performance(bad)


def test_scope_clause_uses_placeholders():
    clause, params = data_loader._scope_clause(["MCA"])
    assert clause == "programme_code = ?" and params == ["MCA"]
    clause, params = data_loader._scope_clause(["MCA", "BCA"])
    assert clause == "programme_code IN (?,?)" and params == ["MCA", "BCA"]


def test_quality_issues_scoped():
    all_issues = data_loader.load_quality_issues(config.PROGRAMME_CODES)
    assert len(all_issues) == 24
    mca = data_loader.load_quality_issues(["MCA"])
    in_rows = mca[mca["performance_id"].notna()]
    assert set(in_rows["programme_code"]) <= {"MCA"}
    # dataset-level findings (no row reference) are visible in every scope
    assert (mca["performance_id"].isna()).sum() == all_issues["performance_id"].isna().sum()
    no_dataset = data_loader.load_quality_issues(["MCA"], include_dataset_level=False)
    assert no_dataset["performance_id"].notna().all()
