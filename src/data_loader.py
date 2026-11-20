"""SQLite access layer for data/app.db.

* Path resolved from the repository root (never ``os.getcwd()``).
* ``PRAGMA foreign_keys = ON`` on every connection.
* Read-only URI connections, so the app can never create or modify the database.
* Parameterised SQL (``?`` placeholders) only; programme scope is always bound.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from src import config


class DatabaseNotFoundError(FileNotFoundError):
    """Raised when data/app.db has not been generated yet."""


def get_connection(db_path: Path | str = config.DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    if not db_path.exists():
        raise DatabaseNotFoundError(
            f"Database not found at {db_path}. Run `python src/generate_data.py` from the repository root first."
        )
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def connection(db_path: Path | str = config.DB_PATH):
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


def _validated_codes(programme_codes: Iterable[str]) -> list[str]:
    codes = [str(c).upper() for c in programme_codes]
    if not codes:
        raise ValueError("At least one programme_code is required.")
    unknown = sorted(set(codes) - set(config.PROGRAMME_CODES))
    if unknown:
        raise ValueError(f"Unknown programme_code(s): {unknown}")
    # Preserve canonical order, drop duplicates
    return [c for c in config.PROGRAMME_CODES if c in set(codes)]


def _scope_clause(codes: Sequence[str], column: str = "programme_code") -> tuple[str, list[str]]:
    """Return a WHERE fragment with ``?`` placeholders. A single code uses ``= ?``."""
    if len(codes) == 1:
        return f"{column} = ?", [codes[0]]
    return f"{column} IN ({','.join('?' for _ in codes)})", list(codes)


def _read(sql: str, params: Sequence | None = None, db_path: Path | str = config.DB_PATH) -> pd.DataFrame:
    with connection(db_path) as conn:
        return pd.read_sql_query(sql, conn, params=list(params or []))


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------
def load_performance(programme_codes: Iterable[str], db_path: Path | str = config.DB_PATH) -> pd.DataFrame:
    """All view rows for the given programme codes (raw: duplicates and NULLs preserved)."""
    codes = _validated_codes(programme_codes)
    clause, params = _scope_clause(codes)
    sql = (
        f"SELECT * FROM {config.VIEW_NAME} WHERE {clause} "
        "ORDER BY period_sequence, programme_id, course_id, performance_id"
    )
    return _read(sql, params, db_path)


def load_performance_for_user(user, db_path: Path | str = config.DB_PATH) -> pd.DataFrame:
    """Scope-enforced loader. An HOD is always bound to ``WHERE programme_code = ?``."""
    if user.is_hod:
        return load_performance([user.programme_code], db_path)
    return load_performance(config.PROGRAMME_CODES, db_path)


def load_programmes(programme_codes: Iterable[str], db_path: Path | str = config.DB_PATH) -> pd.DataFrame:
    codes = _validated_codes(programme_codes)
    clause, params = _scope_clause(codes)
    return _read(f"SELECT * FROM programme_master WHERE {clause} ORDER BY programme_id", params, db_path)


def load_periods(db_path: Path | str = config.DB_PATH) -> pd.DataFrame:
    return _read("SELECT * FROM academic_period_master ORDER BY period_sequence", None, db_path)


def load_courses(programme_codes: Iterable[str], db_path: Path | str = config.DB_PATH) -> pd.DataFrame:
    codes = _validated_codes(programme_codes)
    clause, params = _scope_clause(codes, "pm.programme_code")
    sql = (
        "SELECT cm.*, pm.programme_code, pm.programme_name FROM course_master cm "
        "JOIN programme_master pm ON pm.programme_id = cm.programme_id "
        f"WHERE {clause} ORDER BY cm.course_id"
    )
    return _read(sql, params, db_path)


def load_quality_issues(
    programme_codes: Iterable[str],
    include_dataset_level: bool = True,
    db_path: Path | str = config.DB_PATH,
) -> pd.DataFrame:
    """Data-quality issues for rows in scope; optionally the dataset-level (no-row) findings."""
    codes = _validated_codes(programme_codes)
    clause, params = _scope_clause(codes, "pm.programme_code")
    base = (
        "SELECT dq.*, pm.programme_code, pm.programme_name, ap.period_label, cm.course_code "
        "FROM data_quality_issue dq "
        "LEFT JOIN performance_fact pf ON pf.performance_id = dq.performance_id "
        "LEFT JOIN programme_master pm ON pm.programme_id = pf.programme_id "
        "LEFT JOIN academic_period_master ap ON ap.period_id = pf.period_id "
        "LEFT JOIN course_master cm ON cm.course_id = pf.course_id "
    )
    where = f"WHERE ({clause})"
    if include_dataset_level:
        where += " OR dq.performance_id IS NULL"
    return _read(f"{base}{where} ORDER BY dq.issue_id", params, db_path)


def view_columns(db_path: Path | str = config.DB_PATH) -> list[str]:
    with connection(db_path) as conn:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({config.VIEW_NAME})")]


def foreign_keys_enabled(db_path: Path | str = config.DB_PATH) -> bool:
    with connection(db_path) as conn:
        return conn.execute("PRAGMA foreign_keys;").fetchone()[0] == 1


def table_counts(db_path: Path | str = config.DB_PATH) -> dict[str, int]:
    tables = ("programme_master", "academic_period_master", "course_master", "performance_fact", "data_quality_issue")
    with connection(db_path) as conn:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
