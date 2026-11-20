"""Central configuration: paths, domain constants, KPI catalogue and chart palette."""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (always resolved from the repository root, never from os.getcwd())
# ---------------------------------------------------------------------------
REPO_ROOT: Path = Path(__file__).resolve().parent.parent
DB_PATH: Path = REPO_ROOT / "data" / "app.db"
SECRETS_EXAMPLE_PATH: Path = REPO_ROOT / ".streamlit" / "secrets.toml.example"
SCHEMA_SQL_PATH: Path = REPO_ROOT / "sql" / "schema.sql"

# ---------------------------------------------------------------------------
# Dataset identity
# ---------------------------------------------------------------------------
APP_TITLE = "Department-wise Performance Analysis"
COLLEGE_CONTEXT = "ABES (assumed context)"
DATA_VERSION = "SYNTH-DPA-1.0"
DATA_SEED = 42
SYNTHETIC_NOTICE = (
    "Academic prototype — every figure is synthetic (dataset SYNTH-DPA-1.0, seed 42). "
    "No real student, staff or institutional records are used."
)

VIEW_NAME = "vw_department_performance_analysis"

# ---------------------------------------------------------------------------
# Programme / period / course domain values
# ---------------------------------------------------------------------------
PROGRAMME_CODES: tuple[str, ...] = ("BTECH", "MCA", "BCA", "MBA")
PROGRAMME_NAMES: dict[str, str] = {"BTECH": "B.Tech", "MCA": "MCA", "BCA": "BCA", "MBA": "MBA"}
PROGRAMME_CODE_BY_NAME: dict[str, str] = {v: k for k, v in PROGRAMME_NAMES.items()}
ALL_SCOPE = "ALL"

PERIOD_LABELS: tuple[str, ...] = ("2025-26 Sem 1", "2025-26 Sem 2", "2026-27 Sem 1", "2026-27 Sem 2")
COURSE_CATEGORIES: tuple[str, ...] = ("Core", "Elective", "Practical", "Project")
ASSESSMENT_TYPES: tuple[str, ...] = ("Internal", "End-Semester", "Practical")
ASSESSMENT_SCALE: dict[str, int] = {"Internal": 50, "End-Semester": 100, "Practical": 50}

DQ_CODES: tuple[str, ...] = ("DQ-MISSING", "DQ-DUPLICATE", "DQ-RANGE", "DQ-OUTLIER", "DQ-SCHEMA")
SEVERITIES: tuple[str, ...] = ("Low", "Medium", "High")

# Grain used for deduplication (one record per programme, period and course)
GRAIN_COLUMNS: tuple[str, ...] = ("programme_id", "period_id", "course_id")

# ---------------------------------------------------------------------------
# Expected view contract (39 columns, in order)
# ---------------------------------------------------------------------------
EXPECTED_VIEW_COLUMNS: tuple[str, ...] = (
    "performance_id", "programme_id", "programme_code", "programme_name", "qualification_level",
    "programme_active", "period_id", "academic_year", "semester_no", "period_label", "start_date",
    "end_date", "period_sequence", "course_id", "course_code", "course_name", "course_category",
    "credits", "enrolled_count", "assessed_count", "attendance_present_count",
    "attendance_eligible_count", "attendance_pct", "assessment_type", "average_marks",
    "maximum_marks", "average_marks_pct", "appeared_count", "passed_count", "pass_pct",
    "projects_assigned", "projects_completed", "project_completion_pct",
    "practical_average_score", "practical_max_marks", "practical_score_pct", "data_version",
    "is_synthetic", "created_at",
)

# Row-level percentage columns (computed by the view) used for EDA/statistics
PCT_METRICS: tuple[str, ...] = (
    "attendance_pct", "average_marks_pct", "pass_pct", "project_completion_pct", "practical_score_pct",
)
METRIC_LABELS: dict[str, str] = {
    "attendance_pct": "Attendance %",
    "average_marks_pct": "Average Marks %",
    "pass_pct": "Pass %",
    "project_completion_pct": "Project Completion %",
    "practical_score_pct": "Practical Score %",
}

# ---------------------------------------------------------------------------
# KPI catalogue (weighted formulas implemented in src/analytics.py)
# ---------------------------------------------------------------------------
KPI_KEYS: tuple[str, ...] = ("attendance", "assessment", "pass", "project", "practical")
KPI_LABELS: dict[str, str] = {
    "attendance": "Overall Attendance %",
    "assessment": "Average Assessment %",
    "pass": "Pass %",
    "project": "Project Completion %",
    "practical": "Practical Average %",
}
KPI_IDS: dict[str, str] = {
    "attendance": "KPI-01", "assessment": "KPI-02", "pass": "KPI-03",
    "project": "KPI-04", "practical": "KPI-05",
}
KPI_FORMULAS: dict[str, str] = {
    "attendance": "SUM(attendance_present_count) / SUM(attendance_eligible_count) × 100",
    "assessment": "SUM((average_marks / maximum_marks) × 100 × assessed_count) / SUM(assessed_count), non-NULL marks only",
    "pass": "SUM(passed_count) / SUM(appeared_count) × 100",
    "project": "SUM(projects_completed) / SUM(projects_assigned) × 100, where assigned > 0 and completed IS NOT NULL",
    "practical": "SUM((practical_average_score / practical_max_marks) × 100 × assessed_count) / SUM(assessed_count), non-NULL scores only",
}
ENROLMENT_LABEL = "Total Course-Seat Enrolments"
ENROLMENT_CAUTION = (
    "Course-seat enrolments add up every course a student is registered on in each semester; "
    "this is not a unique student headcount."
)
NOT_AVAILABLE = "Not available"
NOT_AVAILABLE_IN_DATASET = "Not available in this dataset"

LOW_ATTENDANCE_THRESHOLD = 75.0  # % — common Indian university eligibility norm

# ---------------------------------------------------------------------------
# Dataset modes
# ---------------------------------------------------------------------------
MODE_CLEANED = "Cleaned (Deduplicated — Recommended)"
MODE_RAW = "Raw (Unfiltered)"
DATASET_MODES: tuple[str, ...] = (MODE_CLEANED, MODE_RAW)

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
ROLE_DEAN = "Dean"
ROLE_HOD = "HOD"
ROLE_LOGIN_LABELS: dict[str, str] = {"Dean of Academics": ROLE_DEAN, "Department HOD": ROLE_HOD}

# ---------------------------------------------------------------------------
# Theme + chart palette (validated for CVD separation on the #1E293B surface)
# ---------------------------------------------------------------------------
THEME = {
    "background": "#0F172A",
    "surface": "#1E293B",
    "primary": "#38BDF8",
    "text": "#F8FAFC",
    "text_secondary": "#CBD5E1",
    "muted": "#94A3B8",
    "grid": "#334155",
    "baseline": "#475569",
}
SERIES_COLORS: tuple[str, ...] = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181")
# Colour follows the entity, never its rank
PROGRAMME_COLORS: dict[str, str] = {
    "B.Tech": SERIES_COLORS[0], "MCA": SERIES_COLORS[1], "BCA": SERIES_COLORS[2], "MBA": SERIES_COLORS[3],
}
CATEGORY_COLORS: dict[str, str] = {
    "Core": SERIES_COLORS[0], "Elective": SERIES_COLORS[1], "Practical": SERIES_COLORS[2], "Project": SERIES_COLORS[3],
}
ASSESSMENT_COLORS: dict[str, str] = {
    "Internal": SERIES_COLORS[0], "End-Semester": SERIES_COLORS[1], "Practical": SERIES_COLORS[2],
}
KPI_COLORS: dict[str, str] = dict(zip(KPI_LABELS.values(), SERIES_COLORS))
STATUS_COLORS: dict[str, str] = {"Low": "#0ca30c", "Medium": "#fab219", "High": "#d03b3b"}
SEQUENTIAL_SCALE = ["#104281", "#1c5cab", "#2a78d6", "#5598e7", "#86b6ef", "#b7d3f6"]
DIVERGING_SCALE = [[0.0, "#e66767"], [0.5, "#383835"], [1.0, "#3987e5"]]
