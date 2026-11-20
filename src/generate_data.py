"""
Step 10: Synthetic Dataset Generation for Department-wise Performance Analysis
Assumed College Context: ABES (Academic Prototype Only — Synthetic Data)
Programmes in scope: B.Tech, MCA, BCA, MBA
Seed: 42

NOTE ON PROVENANCE
------------------
The DDL_SCRIPT, imports, constants and build_masters() below are reproduced
verbatim from the project's original generator. The original listing was
truncated inside generate_performance_fact(), so everything from that point
onward is a reconstruction written to satisfy the documented dataset contract:

  * performance_fact: 195 rows (48 courses x 4 periods = 192, plus 3 duplicate
    course-period entries 193/194/195 that repeat the grain of 15/62/118)
  * 5 NULL average_marks rows (DQ-MISSING)
  * injected statistical outliers (DQ-OUTLIER)
  * data_quality_issue: 24 rows across DQ-MISSING/DUPLICATE/RANGE/OUTLIER/SCHEMA

If you hold the complete original script, replace this file with it; the
application reads only the database contract (tables + view), not this code.
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

SEED = 42
DATA_VERSION = "SYNTH-DPA-1.0"
CREATED_TS = "2026-11-19T10:00:00Z"

DDL_SCRIPT = """
PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS vw_department_performance_analysis;
DROP TABLE IF EXISTS data_quality_issue;
DROP TABLE IF EXISTS performance_fact;
DROP TABLE IF EXISTS course_master;
DROP TABLE IF EXISTS academic_period_master;
DROP TABLE IF EXISTS programme_master;

CREATE TABLE programme_master (
    programme_id INTEGER PRIMARY KEY,
    programme_code TEXT NOT NULL UNIQUE CHECK (programme_code IN ('BTECH','MCA','BCA','MBA')),
    programme_name TEXT NOT NULL UNIQUE CHECK (programme_name IN ('B.Tech','MCA','BCA','MBA')),
    qualification_level TEXT NOT NULL CHECK (qualification_level IN ('UG','PG')),
    active_flag INTEGER NOT NULL DEFAULT 1 CHECK (active_flag IN (0,1)),
    created_at TEXT NOT NULL
);

CREATE TABLE academic_period_master (
    period_id INTEGER PRIMARY KEY,
    academic_year TEXT NOT NULL CHECK (length(academic_year) = 7),
    semester_no INTEGER NOT NULL CHECK (semester_no IN (1,2)),
    period_label TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    period_sequence INTEGER NOT NULL UNIQUE CHECK (period_sequence > 0),
    CHECK (date(start_date) IS NOT NULL AND date(end_date) IS NOT NULL),
    CHECK (date(start_date) <= date(end_date)),
    UNIQUE (academic_year, semester_no)
);

CREATE TABLE course_master (
    course_id INTEGER PRIMARY KEY,
    course_code TEXT NOT NULL UNIQUE,
    course_name TEXT NOT NULL,
    programme_id INTEGER NOT NULL,
    course_category TEXT NOT NULL CHECK (course_category IN ('Core','Elective','Practical','Project')),
    credits INTEGER NOT NULL CHECK (credits BETWEEN 1 AND 6),
    active_flag INTEGER NOT NULL DEFAULT 1 CHECK (active_flag IN (0,1)),
    FOREIGN KEY (programme_id) REFERENCES programme_master(programme_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE performance_fact (
    performance_id INTEGER PRIMARY KEY,
    programme_id INTEGER NOT NULL,
    period_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    enrolled_count INTEGER NOT NULL CHECK (enrolled_count >= 0),
    assessed_count INTEGER NOT NULL CHECK (assessed_count BETWEEN 0 AND enrolled_count),
    attendance_present_count INTEGER NOT NULL CHECK (attendance_present_count >= 0),
    attendance_eligible_count INTEGER NOT NULL CHECK (attendance_eligible_count >= attendance_present_count),
    assessment_type TEXT NOT NULL CHECK (assessment_type IN ('Internal','End-Semester','Practical')),
    average_marks REAL NULL,
    maximum_marks REAL NULL,
    appeared_count INTEGER NOT NULL CHECK (appeared_count BETWEEN 0 AND enrolled_count),
    passed_count INTEGER NOT NULL CHECK (passed_count BETWEEN 0 AND appeared_count),
    projects_assigned INTEGER NULL CHECK (projects_assigned IS NULL OR projects_assigned >= 0),
    projects_completed INTEGER NULL,
    practical_average_score REAL NULL,
    practical_max_marks REAL NULL,
    data_version TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic = 1),
    created_at TEXT NOT NULL,
    FOREIGN KEY (programme_id) REFERENCES programme_master(programme_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (period_id) REFERENCES academic_period_master(period_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (course_id) REFERENCES course_master(course_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CHECK (attendance_eligible_count >= attendance_present_count),
    CHECK (average_marks IS NULL OR (maximum_marks IS NOT NULL AND maximum_marks > 0 AND average_marks BETWEEN 0 AND maximum_marks)),
    CHECK (projects_completed IS NULL OR (projects_assigned IS NOT NULL AND projects_completed BETWEEN 0 AND projects_assigned)),
    CHECK (practical_average_score IS NULL OR (practical_max_marks IS NOT NULL AND practical_max_marks > 0 AND practical_average_score BETWEEN 0 AND practical_max_marks)),
    UNIQUE (programme_id, period_id, course_id, assessment_type)
);

CREATE TABLE data_quality_issue (
    issue_id INTEGER PRIMARY KEY,
    performance_id INTEGER NULL,
    issue_code TEXT NOT NULL CHECK (issue_code IN ('DQ-MISSING','DQ-DUPLICATE','DQ-RANGE','DQ-OUTLIER','DQ-SCHEMA')),
    field_name TEXT NOT NULL,
    issue_type TEXT NOT NULL CHECK (issue_type IN ('Missing','Duplicate','Invalid','Unusual')),
    severity TEXT NOT NULL CHECK (severity IN ('Low','Medium','High')),
    observed_value TEXT NULL,
    issue_description TEXT NOT NULL CHECK (length(trim(issue_description)) > 0),
    detected_at TEXT NOT NULL,
    resolution_status TEXT NOT NULL CHECK (resolution_status IN ('Open','Reviewed','Resolved','Accepted')),
    dataset_version TEXT NOT NULL,
    FOREIGN KEY (performance_id) REFERENCES performance_fact(performance_id)
        ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE INDEX idx_performance_programme_period
    ON performance_fact(programme_id, period_id);

CREATE INDEX idx_performance_period
    ON performance_fact(period_id);

CREATE INDEX idx_quality_issue_type
    ON data_quality_issue(issue_type, severity);

CREATE VIEW vw_department_performance_analysis AS
SELECT
    pf.performance_id,
    pm.programme_id,
    pm.programme_code,
    pm.programme_name,
    pm.qualification_level,
    pm.active_flag AS programme_active,
    ap.period_id,
    ap.academic_year,
    ap.semester_no,
    ap.period_label,
    ap.start_date,
    ap.end_date,
    ap.period_sequence,
    cm.course_id,
    cm.course_code,
    cm.course_name,
    cm.course_category,
    cm.credits,
    pf.enrolled_count,
    pf.assessed_count,
    pf.attendance_present_count,
    pf.attendance_eligible_count,
    CASE WHEN pf.attendance_eligible_count > 0
         THEN 100.0 * pf.attendance_present_count / pf.attendance_eligible_count END AS attendance_pct,
    pf.assessment_type,
    pf.average_marks,
    pf.maximum_marks,
    CASE WHEN pf.maximum_marks > 0
         THEN 100.0 * pf.average_marks / pf.maximum_marks END AS average_marks_pct,
    pf.appeared_count,
    pf.passed_count,
    CASE WHEN pf.appeared_count > 0
         THEN 100.0 * pf.passed_count / pf.appeared_count END AS pass_pct,
    pf.projects_assigned,
    pf.projects_completed,
    CASE WHEN pf.projects_assigned > 0 AND pf.projects_completed IS NOT NULL
         THEN 100.0 * pf.projects_completed / pf.projects_assigned END AS project_completion_pct,
    pf.practical_average_score,
    pf.practical_max_marks,
    CASE WHEN pf.practical_max_marks > 0
         THEN 100.0 * pf.practical_average_score / pf.practical_max_marks END AS practical_score_pct,
    pf.data_version,
    pf.is_synthetic,
    pf.created_at
FROM performance_fact pf
JOIN programme_master pm ON pm.programme_id = pf.programme_id
JOIN academic_period_master ap ON ap.period_id = pf.period_id
JOIN course_master cm ON cm.course_id = pf.course_id;
"""


def build_masters():
    programmes = pd.DataFrame([
        {"programme_id": 1, "programme_code": "BTECH", "programme_name": "B.Tech", "qualification_level": "UG", "active_flag": 1, "created_at": CREATED_TS},
        {"programme_id": 2, "programme_code": "MCA",   "programme_name": "MCA",    "qualification_level": "PG", "active_flag": 1, "created_at": CREATED_TS},
        {"programme_id": 3, "programme_code": "BCA",   "programme_name": "BCA",    "qualification_level": "UG", "active_flag": 1, "created_at": CREATED_TS},
        {"programme_id": 4, "programme_code": "MBA",   "programme_name": "MBA",    "qualification_level": "PG", "active_flag": 1, "created_at": CREATED_TS},
    ])

    periods = pd.DataFrame([
        {"period_id": 1, "academic_year": "2025-26", "semester_no": 1, "period_label": "2025-26 Sem 1", "start_date": "2025-08-01", "end_date": "2025-12-20", "period_sequence": 1},
        {"period_id": 2, "academic_year": "2025-26", "semester_no": 2, "period_label": "2025-26 Sem 2", "start_date": "2026-01-15", "end_date": "2026-05-30", "period_sequence": 2},
        {"period_id": 3, "academic_year": "2026-27", "semester_no": 1, "period_label": "2026-27 Sem 1", "start_date": "2026-08-03", "end_date": "2026-12-19", "period_sequence": 3},
        {"period_id": 4, "academic_year": "2026-27", "semester_no": 2, "period_label": "2026-27 Sem 2", "start_date": "2027-01-14", "end_date": "2027-05-29", "period_sequence": 4},
    ])

    course_specs = {
        1: [  # B.Tech (12 courses)
            ("BT-CS101", "Data Structures and Algorithmic Thinking", "Core", 4),
            ("BT-CS102", "Operating Systems and Kernel Architecture", "Core", 4),
            ("BT-CS103", "Database Management Systems", "Core", 4),
            ("BT-CS104", "Computer Networks and Internet Protocols", "Core", 4),
            ("BT-CS105", "Design and Analysis of Algorithms", "Core", 4),
            ("BT-EC106", "Digital Logic and Microprocessor Systems", "Core", 3),
            ("BT-CS201", "Cloud Computing and Distributed Infrastructure", "Elective", 3),
            ("BT-CS202", "Applied Machine Learning Foundations", "Elective", 3),
            ("BT-CS203", "Information Security and Cryptography", "Elective", 3),
            ("BT-CS301", "Data Structures and Systems Lab", "Practical", 2),
            ("BT-CS302", "Full-Stack Web Engineering Lab", "Practical", 2),
            ("BT-CS401", "Capstone Engineering Design Project", "Project", 4),
        ],
        2: [  # MCA (12 courses)
            ("MC-CA101", "Advanced Data Structures in C++ and Python", "Core", 4),
            ("MC-CA102", "Enterprise Database Design and SQL Analytics", "Core", 4),
            ("MC-CA103", "Software Engineering and Agile Delivery", "Core", 4),
            ("MC-CA104", "Object-Oriented Systems and Java Architecture", "Core", 4),
            ("MC-CA105", "Discrete Mathematics and Statistical Computing", "Core", 3),
            ("MC-CA201", "Exploratory Data Analysis and Visualisation", "Elective", 3),
            ("MC-CA202", "Natural Language Processing Applications", "Elective", 3),
            ("MC-CA203", "DevOps and Containerised Microservices", "Elective", 3),
            ("MC-CA301", "Python Data Analytics and SQLite Lab", "Practical", 2),
            ("MC-CA302", "Web Application Development Lab", "Practical", 2),
            ("MC-CA401", "Minor Applied Software Project", "Project", 3),
            ("MC-CA402", "Major Industry Analytics Capstone Project", "Project", 5),
        ],
        3: [  # BCA (12 courses)
            ("BC-UG101", "Programming Fundamentals with C and Python", "Core", 4),
            ("BC-UG102", "Relational Databases and Query Processing", "Core", 4),
            ("BC-UG103", "Computer Organisation and Architecture", "Core", 4),
            ("BC-UG104", "Web Technologies and Frontend Design", "Core", 4),
            ("BC-UG105", "Operating System Concepts", "Core", 3),
            ("BC-UG201", "Business Intelligence and Spreadsheet Modelling", "Elective", 3),
            ("BC-UG202", "Mobile Application Prototyping", "Elective", 3),
            ("BC-UG203", "Cyber Hygiene and Network Fundamentals", "Elective", 3),
            ("BC-UG301", "Python and Database Programming Lab", "Practical", 2),
            ("BC-UG302", "Web Interface and Scripting Lab", "Practical", 2),
            ("BC-UG303", "Linux Administration and Shell Scripting Lab", "Practical", 2),
            ("BC-UG401", "Undergraduate Software Development Project", "Project", 4),
        ],
        4: [  # MBA (12 courses)
            ("MB-MG101", "Managerial Economics and Indian Business Environment", "Core", 4),
            ("MB-MG102", "Financial Reporting and Cost Accounting", "Core", 4),
            ("MB-MG103", "Marketing Management and Consumer Behaviour", "Core", 4),
            ("MB-MG104", "Organisational Behaviour and Human Capital", "Core", 4),
            ("MB-MG105", "Quantitative Techniques and Business Statistics", "Core", 4),
            ("MB-MG106", "Operations and Supply Chain Analytics", "Core", 3),
            ("MB-MG201", "Corporate Finance and Valuation Strategy", "Elective", 3),
            ("MB-MG202", "Digital Marketing and Brand Analytics", "Elective", 3),
            ("MB-MG203", "Business Analytics for Decision Makers", "Elective", 3),
            ("MB-MG301", "Financial Modelling and ERP Simulation Lab", "Practical", 2),
            ("MB-MG401", "Summer Industry Immersion Field Project", "Project", 4),
            ("MB-MG402", "Strategic Management Capstone Case Project", "Project", 4),
        ],
    }

    course_rows = []
    cid = 1
    for prog_id in [1, 2, 3, 4]:
        for code, name, cat, credits in course_specs[prog_id]:
            course_rows.append({
                "course_id": cid,
                "course_code": code,
                "course_name": name,
                "programme_id": prog_id,
                "course_category": cat,
                "credits": credits,
                "active_flag": 1,
            })
            cid += 1

    courses = pd.DataFrame(course_rows)
    return programmes, periods, courses


# ---------------------------------------------------------------------------
# Reconstructed section (original listing truncated from here onward)
# ---------------------------------------------------------------------------

# Assessment scale per course category: (assessment_type, maximum_marks)
CATEGORY_ASSESSMENT = {
    "Core": ("End-Semester", 100.0),
    "Elective": ("Internal", 50.0),
    "Practical": ("Practical", 50.0),
    "Project": ("Internal", 50.0),
}

# Primary rows whose (programme_id, period_id, course_id) grain is re-entered
# as duplicates 193, 194, 195 respectively.
DUPLICATE_SOURCE_IDS = (15, 62, 118)
NULL_MARKS_COUNT = 5
OUTLIER_COUNT = 8
RANGE_ISSUE_COUNT = 5


def _clip_int(value, low, high):
    return int(max(low, min(high, round(value))))


def generate_performance_fact(programmes, periods, courses):
    rng = np.random.default_rng(SEED)

    # Cohort sizes reflect realistic Indian college programme capacities (synthetic ABES scenario)
    cohort_ranges = {
        1: (110, 145),  # B.Tech largest intake
        2: (55, 75),    # MCA
        3: (75, 105),   # BCA
        4: (60, 85),    # MBA
    }

    # Pattern 1: PG programmes (MCA, MBA) maintain higher baseline attendance & pass rates than UG (B.Tech, BCA)
    base_attendance = {1: 0.77, 2: 0.85, 3: 0.75, 4: 0.86}
    base_score_pct = {1: 0.62, 2: 0.70, 3: 0.60, 4: 0.69}
    base_pass = {1: 0.82, 2: 0.90, 3: 0.79, 4: 0.91}
    # Pattern 2: gentle improvement across successive periods
    period_lift = {1: 0.00, 2: 0.012, 3: 0.020, 4: 0.028}
    # Pattern 3: practical/project courses carry higher attendance than theory electives
    category_att_adj = {"Core": 0.0, "Elective": -0.03, "Practical": 0.04, "Project": 0.02}

    rows = []
    perf_id = 1
    for _, period in periods.sort_values("period_sequence").iterrows():
        pid = int(period["period_id"])
        lift = period_lift[pid]
        for prog_id in [1, 2, 3, 4]:
            low, high = cohort_ranges[prog_id]
            cohort = int(rng.integers(low, high + 1))
            prog_courses = courses[courses["programme_id"] == prog_id].sort_values("course_id")
            for _, course in prog_courses.iterrows():
                cat = course["course_category"]
                credits = int(course["credits"])
                if cat == "Elective":
                    enrolled = _clip_int(cohort * rng.uniform(0.35, 0.60), 15, cohort)
                else:
                    enrolled = cohort
                assessed = enrolled - int(rng.integers(0, 5))
                assessed = max(assessed, 0)

                sessions = credits * 12
                eligible = enrolled * sessions
                att_rate = np.clip(
                    base_attendance[prog_id] + lift + category_att_adj[cat] + rng.normal(0, 0.03),
                    0.55, 0.98,
                )
                present = _clip_int(eligible * att_rate, 0, eligible)

                assessment_type, max_marks = CATEGORY_ASSESSMENT[cat]
                score_rate = np.clip(
                    base_score_pct[prog_id] + lift + 0.35 * (att_rate - base_attendance[prog_id])
                    + rng.normal(0, 0.04),
                    0.35, 0.95,
                )
                if cat in ("Practical", "Project"):
                    score_rate = min(score_rate + 0.06, 0.96)
                avg_marks = round(float(max_marks * score_rate), 2)

                appeared = assessed
                pass_rate = np.clip(
                    base_pass[prog_id] + lift + 0.5 * (score_rate - base_score_pct[prog_id])
                    + rng.normal(0, 0.03),
                    0.55, 0.995,
                )
                passed = int(rng.binomial(appeared, pass_rate)) if appeared > 0 else 0

                projects_assigned = None
                projects_completed = None
                practical_avg = None
                practical_max = None
                if cat == "Project":
                    team_size = 4 if prog_id in (1, 3) else 3
                    projects_assigned = int(np.ceil(enrolled / team_size))
                    completion = np.clip(0.80 + lift + rng.normal(0, 0.06), 0.55, 1.0)
                    projects_completed = _clip_int(projects_assigned * completion, 0, projects_assigned)
                if cat == "Practical":
                    practical_max = 50.0
                    prac_rate = np.clip(score_rate + rng.normal(0.03, 0.03), 0.40, 0.97)
                    practical_avg = round(float(practical_max * prac_rate), 2)

                rows.append({
                    "performance_id": perf_id,
                    "programme_id": prog_id,
                    "period_id": pid,
                    "course_id": int(course["course_id"]),
                    "enrolled_count": enrolled,
                    "assessed_count": assessed,
                    "attendance_present_count": present,
                    "attendance_eligible_count": eligible,
                    "assessment_type": assessment_type,
                    "average_marks": avg_marks,
                    "maximum_marks": max_marks,
                    "appeared_count": appeared,
                    "passed_count": passed,
                    "projects_assigned": projects_assigned,
                    "projects_completed": projects_completed,
                    "practical_average_score": practical_avg,
                    "practical_max_marks": practical_max,
                    "data_version": DATA_VERSION,
                    "is_synthetic": 1,
                    "created_at": CREATED_TS,
                })
                perf_id += 1

    fact = pd.DataFrame(rows)
    fact = fact.astype({
        "projects_assigned": "Int64",
        "projects_completed": "Int64",
        "practical_average_score": "Float64",
        "practical_max_marks": "Float64",
        "average_marks": "Float64",
    })

    issues = []
    protected = set(DUPLICATE_SOURCE_IDS)
    candidate_ids = [i for i in fact["performance_id"] if i not in protected]

    # --- DQ-MISSING: 5 NULL average_marks --------------------------------
    missing_ids = sorted(int(x) for x in rng.choice(candidate_ids, NULL_MARKS_COUNT, replace=False))
    for mid in missing_ids:
        fact.loc[fact["performance_id"] == mid, "average_marks"] = pd.NA
        issues.append({
            "performance_id": mid, "issue_code": "DQ-MISSING", "field_name": "average_marks",
            "issue_type": "Missing", "severity": "Medium", "observed_value": None,
            "issue_description": "average_marks not supplied by source mark sheet; excluded from KPI-02 denominator (not coerced to 0).",
            "resolution_status": "Open",
        })
    protected.update(missing_ids)

    # --- DQ-OUTLIER: depress attendance or pass rate on 8 rows -------------
    remaining = [i for i in candidate_ids if i not in protected]
    outlier_ids = sorted(int(x) for x in rng.choice(remaining, OUTLIER_COUNT, replace=False))
    for n, oid in enumerate(outlier_ids):
        idx = fact.index[fact["performance_id"] == oid][0]
        if n % 2 == 0:
            eligible = int(fact.at[idx, "attendance_eligible_count"])
            new_present = _clip_int(eligible * rng.uniform(0.42, 0.52), 0, eligible)
            fact.at[idx, "attendance_present_count"] = new_present
            observed = f"{100.0 * new_present / eligible:.2f}"
            field = "attendance_present_count"
            desc = "Attendance rate far below programme norm; flagged as statistical outlier (IQR rule) for review."
            severity = "Medium"
        else:
            appeared = int(fact.at[idx, "appeared_count"])
            new_passed = _clip_int(appeared * rng.uniform(0.38, 0.50), 0, appeared)
            fact.at[idx, "passed_count"] = new_passed
            observed = f"{100.0 * new_passed / appeared:.2f}" if appeared else None
            field = "passed_count"
            desc = "Pass rate far below programme norm; flagged as statistical outlier (IQR rule) for review."
            severity = "High"
        issues.append({
            "performance_id": oid, "issue_code": "DQ-OUTLIER", "field_name": field,
            "issue_type": "Unusual", "severity": severity, "observed_value": observed,
            "issue_description": desc,
            "resolution_status": "Reviewed" if n < 4 else "Open",
        })
    protected.update(outlier_ids)

    # --- DQ-RANGE: appeared_count exceeds assessed_count on 5 rows ---------
    remaining = [
        i for i in candidate_ids
        if i not in protected
        and int(fact.loc[fact["performance_id"] == i, "assessed_count"].iloc[0])
        < int(fact.loc[fact["performance_id"] == i, "enrolled_count"].iloc[0])
    ]
    range_ids = sorted(int(x) for x in rng.choice(remaining, RANGE_ISSUE_COUNT, replace=False))
    for rid in range_ids:
        idx = fact.index[fact["performance_id"] == rid][0]
        new_appeared = int(fact.at[idx, "enrolled_count"])
        fact.at[idx, "appeared_count"] = new_appeared
        issues.append({
            "performance_id": rid, "issue_code": "DQ-RANGE", "field_name": "appeared_count",
            "issue_type": "Invalid", "severity": "Low", "observed_value": str(new_appeared),
            "issue_description": "appeared_count exceeds assessed_count; reconciliation range check failed (within enrolment cap).",
            "resolution_status": "Accepted",
        })
    protected.update(range_ids)

    # --- DQ-DUPLICATE: re-entries 193/194/195 of 15/62/118 -----------------
    dup_rows = []
    next_id = int(fact["performance_id"].max()) + 1
    for src_id in DUPLICATE_SOURCE_IDS:
        src = fact.loc[fact["performance_id"] == src_id].iloc[0].to_dict()
        dup = dict(src)
        dup["performance_id"] = next_id
        # Re-entered under a different assessment_type (allowed by the 4-column UNIQUE key)
        if src["assessment_type"] == "Internal":
            dup["assessment_type"], dup["maximum_marks"] = "End-Semester", 100.0
        else:
            dup["assessment_type"], dup["maximum_marks"] = "Internal", 50.0
        dup["average_marks"] = round(float(dup["maximum_marks"]) * float(rng.uniform(0.58, 0.74)), 2)
        dup["attendance_present_count"] = _clip_int(
            src["attendance_present_count"] * rng.uniform(0.97, 1.0), 0, src["attendance_eligible_count"]
        )
        dup["passed_count"] = _clip_int(src["passed_count"] - rng.integers(0, 3), 0, src["appeared_count"])
        dup_rows.append(dup)
        issues.append({
            "performance_id": next_id, "issue_code": "DQ-DUPLICATE",
            "field_name": "programme_id|period_id|course_id",
            "issue_type": "Duplicate", "severity": "High",
            "observed_value": f"duplicates performance_id {src_id}",
            "issue_description": f"Course-period grain re-entered (copy of performance_id {src_id}); deduplication keeps the lowest performance_id.",
            "resolution_status": "Open",
        })
        next_id += 1
    fact = pd.concat([fact, pd.DataFrame(dup_rows)], ignore_index=True)
    fact = fact.astype({
        "projects_assigned": "Int64",
        "projects_completed": "Int64",
        "practical_average_score": "Float64",
        "practical_max_marks": "Float64",
        "average_marks": "Float64",
    })

    # --- DQ-SCHEMA: dataset-level load findings (no row reference) ---------
    schema_findings = [
        ("student_feedback_score", "source column absent from target schema",
         "Source extract contained column 'student_feedback_score' with no target field; dropped during load.", "Low", "Accepted"),
        ("maximum_marks", "'50/50' (TEXT)",
         "Source supplied maximum_marks as composite TEXT for some Internal rows; normalised to REAL 50.0 on load.", "Medium", "Resolved"),
        ("created_at", "mixed timezone suffixes",
         "Source timestamps mixed IST and UTC suffixes; standardised to ISO-8601 UTC.", "Low", "Resolved"),
    ]
    for field, observed, desc, sev, status in schema_findings:
        issues.append({
            "performance_id": None, "issue_code": "DQ-SCHEMA", "field_name": field,
            "issue_type": "Invalid", "severity": sev, "observed_value": observed,
            "issue_description": desc, "resolution_status": status,
        })

    order = {"DQ-MISSING": 0, "DQ-DUPLICATE": 1, "DQ-RANGE": 2, "DQ-OUTLIER": 3, "DQ-SCHEMA": 4}
    dq = pd.DataFrame(issues)
    dq["_o"] = dq["issue_code"].map(order)
    dq = dq.sort_values(["_o", "performance_id"], na_position="last", kind="stable").drop(columns="_o")
    dq.insert(0, "issue_id", range(1, len(dq) + 1))
    dq["detected_at"] = CREATED_TS
    dq["dataset_version"] = DATA_VERSION
    dq["performance_id"] = dq["performance_id"].astype("Int64")
    return fact, dq.reset_index(drop=True)


def _to_records(df, columns):
    out = []
    for rec in df[columns].itertuples(index=False, name=None):
        out.append(tuple(None if (v is pd.NA or (isinstance(v, float) and np.isnan(v))) else
                         (int(v) if isinstance(v, (np.integer,)) else
                          float(v) if isinstance(v, (np.floating,)) else v)
                         for v in rec))
    return out


def write_database(db_path, programmes, periods, courses, fact, dq):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(DDL_SCRIPT)
        conn.execute("PRAGMA foreign_keys = ON;")
        for table, df in [
            ("programme_master", programmes),
            ("academic_period_master", periods),
            ("course_master", courses),
            ("performance_fact", fact),
            ("data_quality_issue", dq),
        ]:
            cols = list(df.columns)
            placeholders = ",".join("?" for _ in cols)
            conn.executemany(
                f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
                _to_records(df, cols),
            )
        conn.commit()
    finally:
        conn.close()


def validate_database(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ["programme_master", "academic_period_master", "course_master",
                      "performance_fact", "data_quality_issue"]
        }
        expected = {"programme_master": 4, "academic_period_master": 4, "course_master": 48,
                    "performance_fact": 195, "data_quality_issue": 24}
        assert counts == expected, f"Row-count mismatch: {counts}"
        n_null = conn.execute("SELECT COUNT(*) FROM performance_fact WHERE average_marks IS NULL").fetchone()[0]
        assert n_null == NULL_MARKS_COUNT, n_null
        dup_groups = conn.execute(
            "SELECT COUNT(*) FROM (SELECT programme_id, period_id, course_id FROM performance_fact "
            "GROUP BY 1,2,3 HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        assert dup_groups == 3, dup_groups
        view_cols = [r[1] for r in conn.execute("PRAGMA table_info(vw_department_performance_analysis)")]
        assert len(view_cols) == 39, len(view_cols)
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert not fk_errors, fk_errors
        return counts
    finally:
        conn.close()


def export_workbook(xlsx_path, frames):
    """Write a styled reviewer workbook (one sheet per table)."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1E293B")
    thin = Side(style="thin", color="CBD5E1")
    for name, df in frames.items():
        ws = wb.create_sheet(title=name[:31])
        ws.append(list(df.columns))
        for rec in _to_records(df, list(df.columns)):
            ws.append(list(rec))
        for c_idx, col in enumerate(df.columns, start=1):
            cell = ws.cell(row=1, column=c_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            ws.column_dimensions[get_column_letter(c_idx)].width = max(12, min(48, len(str(col)) + 4))
        ws.freeze_panes = "A2"
    wb.save(xlsx_path)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    os.makedirs(data_dir, exist_ok=True)
    db_path = data_dir / "app.db"

    programmes, periods, courses = build_masters()
    fact, dq = generate_performance_fact(programmes, periods, courses)
    write_database(db_path, programmes, periods, courses, fact, dq)
    counts = validate_database(db_path)
    export_workbook(
        data_dir / f"{DATA_VERSION}_dataset.xlsx",
        {"programme_master": programmes, "academic_period_master": periods,
         "course_master": courses, "performance_fact": fact, "data_quality_issue": dq},
    )
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {DATA_VERSION} (seed {SEED}) -> {db_path}")
    for t, n in counts.items():
        print(f"  {t:<24} {n:>4} rows")


if __name__ == "__main__":
    main()
