"""Weighted KPI engine (KPI-01 … KPI-07).

Rules enforced here:
* Rates are always ratio-of-sums (weighted); unweighted means of row percentages are never used.
* NULL inputs are excluded from that metric's numerator AND denominator only — never coerced to 0.
* A metric with an empty denominator returns ``None`` (rendered as "Not available").
* Period movements are reported in percentage points (pp): current_rate − prior_rate.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd

from src import cleaning, config

# Numerator / denominator column pairs per KPI (built by _with_components)
_COMPONENTS: dict[str, tuple[str, str, float]] = {
    # key: (numerator, denominator, multiplier)
    "attendance": ("_att_num", "_att_den", 100.0),
    "assessment": ("_asm_num", "_asm_den", 1.0),
    "pass": ("_pass_num", "_pass_den", 100.0),
    "project": ("_proj_num", "_proj_den", 100.0),
    "practical": ("_prac_num", "_prac_den", 1.0),
}


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("float64")


def _with_components(df: pd.DataFrame) -> pd.DataFrame:
    """Add per-row numerator/denominator contributions. Excluded rows contribute to neither side."""
    out = df.copy()
    present, eligible = _num(df["attendance_present_count"]), _num(df["attendance_eligible_count"])
    assessed = _num(df["assessed_count"])
    marks, max_marks = _num(df["average_marks"]), _num(df["maximum_marks"])
    passed, appeared = _num(df["passed_count"]), _num(df["appeared_count"])
    assigned, completed = _num(df["projects_assigned"]), _num(df["projects_completed"])
    p_score, p_max = _num(df["practical_average_score"]), _num(df["practical_max_marks"])

    att_ok = present.notna() & eligible.notna()
    out["_att_num"] = present.where(att_ok)
    out["_att_den"] = eligible.where(att_ok)

    asm_ok = marks.notna() & max_marks.notna() & (max_marks > 0) & assessed.notna()
    out["_asm_num"] = ((marks / max_marks) * 100.0 * assessed).where(asm_ok)
    out["_asm_den"] = assessed.where(asm_ok)

    pass_ok = passed.notna() & appeared.notna()
    out["_pass_num"] = passed.where(pass_ok)
    out["_pass_den"] = appeared.where(pass_ok)

    proj_ok = assigned.notna() & (assigned > 0) & completed.notna()
    out["_proj_num"] = completed.where(proj_ok)
    out["_proj_den"] = assigned.where(proj_ok)

    prac_ok = p_score.notna() & p_max.notna() & (p_max > 0) & assessed.notna()
    out["_prac_num"] = ((p_score / p_max) * 100.0 * assessed).where(prac_ok)
    out["_prac_den"] = assessed.where(prac_ok)
    return out


def _ratio(num: float, den: float, mult: float) -> float | None:
    if den is None or pd.isna(den) or den <= 0:
        return None
    return float(num) / float(den) * mult


# ---------------------------------------------------------------------------
# Scalar KPIs
# ---------------------------------------------------------------------------
def kpi_value(df: pd.DataFrame, key: str) -> float | None:
    if df.empty:
        return None
    comp = _with_components(df)
    num_col, den_col, mult = _COMPONENTS[key]
    den = comp[den_col].sum(min_count=1)
    num = comp[num_col].sum(min_count=1)
    return _ratio(num, den, mult)


def overall_attendance_pct(df: pd.DataFrame) -> float | None:
    """KPI-01."""
    return kpi_value(df, "attendance")


def average_assessment_pct(df: pd.DataFrame) -> float | None:
    """KPI-02."""
    return kpi_value(df, "assessment")


def pass_pct(df: pd.DataFrame) -> float | None:
    """KPI-03."""
    return kpi_value(df, "pass")


def project_completion_pct(df: pd.DataFrame) -> float | None:
    """KPI-04."""
    return kpi_value(df, "project")


def practical_average_pct(df: pd.DataFrame) -> float | None:
    """KPI-05."""
    return kpi_value(df, "practical")


def compute_kpis(df: pd.DataFrame) -> dict[str, float | None]:
    return {key: kpi_value(df, key) for key in config.KPI_KEYS}


def total_course_seat_enrolments(df: pd.DataFrame) -> int:
    """Sum of enrolled_count — course-seat enrolments, NOT unique students."""
    return int(_num(df["enrolled_count"]).sum()) if len(df) else 0


def kpi_components(df: pd.DataFrame) -> pd.DataFrame:
    """Numerator / denominator / rate table for every KPI (for transparency panels)."""
    comp = _with_components(df)
    rows = []
    for key in config.KPI_KEYS:
        num_col, den_col, mult = _COMPONENTS[key]
        num = comp[num_col].sum(min_count=1)
        den = comp[den_col].sum(min_count=1)
        rows.append({
            "kpi_id": config.KPI_IDS[key],
            "kpi": config.KPI_LABELS[key],
            "numerator": None if pd.isna(num) else float(num),
            "denominator": None if pd.isna(den) else float(den),
            "rows_used": int(comp[den_col].notna().sum()),
            "value": _ratio(num, den, mult),
            "formula": config.KPI_FORMULAS[key],
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Grouped KPIs
# ---------------------------------------------------------------------------
def grouped_kpis(df: pd.DataFrame, by: str | Sequence[str]) -> pd.DataFrame:
    """One row per group with every weighted KPI plus raw counts used to derive them."""
    by = [by] if isinstance(by, str) else list(by)
    columns = [*by, "records", "course_seat_enrolments", "attendance_present", "attendance_eligible",
               "appeared", "passed", "projects_assigned_used", "projects_completed_used", *config.KPI_KEYS]
    if df.empty:
        return pd.DataFrame(columns=columns)
    comp = _with_components(df)
    comp["_enrolled"] = _num(comp["enrolled_count"])
    agg_cols = ["_enrolled"] + [c for pair in _COMPONENTS.values() for c in pair[:2]]
    sums = comp.groupby(by, dropna=False, sort=True)[agg_cols].sum(min_count=1)
    counts = comp.groupby(by, dropna=False, sort=True).size().rename("records")
    out = pd.concat([counts, sums], axis=1).reset_index()
    for key, (num_col, den_col, mult) in _COMPONENTS.items():
        out[key] = [
            _ratio(n, d, mult) for n, d in zip(out[num_col], out[den_col])
        ]
        out[key] = out[key].astype("float64")
    out = out.rename(columns={
        "_enrolled": "course_seat_enrolments",
        "_att_num": "attendance_present", "_att_den": "attendance_eligible",
        "_pass_num": "passed", "_pass_den": "appeared",
        "_proj_den": "projects_assigned_used", "_proj_num": "projects_completed_used",
    })
    out["course_seat_enrolments"] = out["course_seat_enrolments"].fillna(0).astype("int64")
    out = out.sort_values(by, key=_canonical_sort_key, kind="mergesort").reset_index(drop=True)
    return out[columns]


_CANONICAL_ORDER: dict[str, dict[str, int]] = {
    "programme_name": {n: i for i, n in enumerate(config.PROGRAMME_NAMES.values())},
    "programme_code": {c: i for i, c in enumerate(config.PROGRAMME_CODES)},
    "course_category": {c: i for i, c in enumerate(config.COURSE_CATEGORIES)},
    "assessment_type": {t: i for i, t in enumerate(config.ASSESSMENT_TYPES)},
}


def _canonical_sort_key(s: pd.Series) -> pd.Series:
    order = _CANONICAL_ORDER.get(s.name)
    return s.map(order) if order else s


def group_dimension(user) -> tuple[str, str]:
    """(column, label) used for KPI-06 comparisons: programme for Dean, course for HOD."""
    if user.is_dean:
        return "programme_name", "Programme"
    return "course_code", "Course"


def kpi_extremes(df: pd.DataFrame, by: str, key: str) -> dict:
    """KPI-06: highest and lowest group for one KPI, returning every tied group."""
    table = grouped_kpis(df, by)
    valid = table.loc[table[key].notna(), [by, key]]
    if valid.empty:
        return {"highest": [], "lowest": [], "highest_value": None, "lowest_value": None, "table": valid}
    hi, lo = float(valid[key].max()), float(valid[key].min())
    highest = valid.loc[np.isclose(valid[key], hi, rtol=0, atol=1e-9), by].astype(str).tolist()
    lowest = valid.loc[np.isclose(valid[key], lo, rtol=0, atol=1e-9), by].astype(str).tolist()
    return {"highest": highest, "lowest": lowest, "highest_value": hi, "lowest_value": lo,
            "table": valid.sort_values(key, ascending=False).reset_index(drop=True)}


# ---------------------------------------------------------------------------
# Period trends (KPI-07)
# ---------------------------------------------------------------------------
def period_trend(df: pd.DataFrame, by: str | Sequence[str] | None = None) -> pd.DataFrame:
    """Weighted KPIs per period, ordered by period_sequence (1 → 4)."""
    keys = ["period_sequence", "period_label"]
    if by:
        keys = keys + ([by] if isinstance(by, str) else list(by))
    out = grouped_kpis(df, keys)
    return out.sort_values(keys).reset_index(drop=True)


def period_deltas(trend: pd.DataFrame, keys: Iterable[str] = config.KPI_KEYS,
                  by: str | Sequence[str] | None = None) -> pd.DataFrame:
    """Add ``<kpi>_pp`` = current_rate − prior_rate (percentage points) by period_sequence order."""
    out = trend.sort_values(([by] if isinstance(by, str) else list(by or [])) + ["period_sequence"]).copy()
    for key in keys:
        if by:
            out[f"{key}_pp"] = out.groupby(by, sort=False)[key].diff()
        else:
            out[f"{key}_pp"] = out[key].diff()
    return out.reset_index(drop=True)


def latest_vs_prior(df_all_periods: pd.DataFrame, selected_sequences: Iterable[int] | None = None) -> dict:
    """Compare the latest selected period with the period immediately before it (pp)."""
    if df_all_periods.empty:
        return {}
    available = sorted(int(s) for s in df_all_periods["period_sequence"].unique())
    selected = sorted(int(s) for s in (selected_sequences or available) if int(s) in available)
    if not selected:
        return {}
    current_seq = selected[-1]
    prior_seq = current_seq - 1 if (current_seq - 1) in available else None
    labels = df_all_periods.drop_duplicates("period_sequence").set_index("period_sequence")["period_label"]
    current = compute_kpis(df_all_periods[df_all_periods["period_sequence"] == current_seq])
    prior = compute_kpis(df_all_periods[df_all_periods["period_sequence"] == prior_seq]) if prior_seq else {}
    result = {"current_label": labels.get(current_seq), "prior_label": labels.get(prior_seq) if prior_seq else None}
    for key in config.KPI_KEYS:
        cur, pri = current.get(key), prior.get(key) if prior else None
        result[key] = {
            "current": cur,
            "prior": pri,
            "pp": (cur - pri) if (cur is not None and pri is not None) else None,
        }
    return result


# ---------------------------------------------------------------------------
# Domain tables
# ---------------------------------------------------------------------------
def assessment_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """KPI-02 split by assessment_type, each normalised from its native scale to %."""
    table = grouped_kpis(df, "assessment_type")
    if table.empty:
        return pd.DataFrame(columns=["assessment_type", "scale", "records", "rows_with_marks",
                                     "weighted_avg_marks", "assessment"])
    comp = _with_components(df)
    marks_rows = comp.groupby("assessment_type")["_asm_den"].count()
    assessed_w = comp.assign(_m=_num(comp["average_marks"]) * comp["_asm_den"]).groupby("assessment_type")[["_m", "_asm_den"]].sum(min_count=1)
    table["scale"] = table["assessment_type"].map(lambda t: f"/{config.ASSESSMENT_SCALE.get(t, '?')}")
    table["rows_with_marks"] = table["assessment_type"].map(marks_rows).fillna(0).astype(int)
    table["weighted_avg_marks"] = table["assessment_type"].map(
        lambda t: (assessed_w.loc[t, "_m"] / assessed_w.loc[t, "_asm_den"])
        if t in assessed_w.index and assessed_w.loc[t, "_asm_den"] > 0 else np.nan
    )
    order = {t: i for i, t in enumerate(config.ASSESSMENT_TYPES)}
    table = table.sort_values("assessment_type", key=lambda s: s.map(order)).reset_index(drop=True)
    return table[["assessment_type", "scale", "records", "rows_with_marks", "weighted_avg_marks", "assessment"]]


def low_attendance_watchlist(df: pd.DataFrame, threshold: float = config.LOW_ATTENDANCE_THRESHOLD) -> pd.DataFrame:
    """Course-period slices whose weighted attendance is below ``threshold``."""
    keys = ["programme_name", "period_sequence", "period_label", "course_code", "course_name", "course_category"]
    table = grouped_kpis(df, keys)
    if table.empty:
        return table
    out = table.loc[table["attendance"].notna() & (table["attendance"] < threshold)]
    out = out.assign(gap_pp=out["attendance"] - threshold)
    return out.sort_values("attendance").reset_index(drop=True)


def raw_vs_cleaned(raw_df: pd.DataFrame) -> pd.DataFrame:
    """KPI values under both dataset modes with the impact of cleaning in pp."""
    clean_df = cleaning.deduplicate(raw_df)
    raw_k, clean_k = compute_kpis(raw_df), compute_kpis(clean_df)
    rows = [
        {"metric": "Records (course-period rows)", "raw": float(len(raw_df)), "cleaned": float(len(clean_df)),
         "impact": float(len(clean_df) - len(raw_df)), "unit": "rows"},
        {"metric": config.ENROLMENT_LABEL, "raw": float(total_course_seat_enrolments(raw_df)),
         "cleaned": float(total_course_seat_enrolments(clean_df)),
         "impact": float(total_course_seat_enrolments(clean_df) - total_course_seat_enrolments(raw_df)),
         "unit": "seats"},
    ]
    for key in config.KPI_KEYS:
        r, c = raw_k[key], clean_k[key]
        rows.append({
            "metric": f"{config.KPI_IDS[key]} {config.KPI_LABELS[key]}",
            "raw": r, "cleaned": c,
            "impact": (c - r) if (r is not None and c is not None) else None,
            "unit": "pp",
        })
    return pd.DataFrame(rows)


def availability(df: pd.DataFrame) -> dict[str, int]:
    """How many rows can feed the project and practical metrics (structural NULLs excluded)."""
    comp = _with_components(df)
    return {
        "project_rows": int(comp["_proj_den"].notna().sum()),
        "practical_rows": int(comp["_prac_den"].notna().sum()),
        "project_rows_null_completed": int(
            (_num(df["projects_assigned"]).notna() & _num(df["projects_completed"]).isna()).sum()
        ),
    }
