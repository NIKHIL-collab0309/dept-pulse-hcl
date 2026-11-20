-- =============================================================================
-- Department-wise Performance Analysis — SQLite schema (dataset SYNTH-DPA-1.0)
-- Extracted verbatim from DDL_SCRIPT in src/generate_data.py. Do not edit by
-- hand: regenerate from the generator if the schema ever changes.
-- Objects: programme_master, academic_period_master, course_master,
--          performance_fact, data_quality_issue, 3 indexes,
--          vw_department_performance_analysis (39 columns).
-- =============================================================================
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
