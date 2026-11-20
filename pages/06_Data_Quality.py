"""Page 06 — Data Quality: logged issues, live validation, IQR scan, raw vs cleaned impact."""

import streamlit as st

from src import analytics, charts, cleaning, config, filters, statistics, ui_components as ui, validation

user = ui.require_user()
f = filters.current_filters(user)
ui.page_header(user, "Data Quality",
               "Logged issues, live checks on the scoped extract, and the KPI impact of deduplication.",
               f.dataset_mode)

# Live checks always run on the RAW scoped extract so problems are never hidden by cleaning
raw_scope = filters.scoped_raw_data(user, f)
raw_scope = raw_scope[raw_scope["programme_code"].isin(f.programme_codes)]
dq = filters.scoped_quality_issues(user, f)
summary = cleaning.cleaning_summary(raw_scope)

ui.kpi_cards([
    ui.KpiCard("Logged issues in scope", str(len(dq)), "DQ LOG", "Includes dataset-level schema findings"),
    ui.KpiCard("Open issues", str(int((dq["resolution_status"] == "Open").sum())), "STATUS", "resolution_status = Open"),
    ui.KpiCard("Raw rows", str(summary["raw_rows"]), "RAW", "Unfiltered extract"),
    ui.KpiCard("Cleaned rows", str(summary["cleaned_rows"]), "CLEANED",
               f"{summary['removed_duplicates']} duplicate course-period row(s) removed"),
    ui.KpiCard("NULL average_marks", str(summary["null_average_marks_cleaned"]), "DQ-MISSING",
               "Kept as NULL — excluded from KPI-02 only"),
])

st.info(
    f"Sidebar **Dataset Mode** is currently **{f.dataset_mode}**. Switch it to see every page recompute; "
    "the table below shows both modes side by side.", icon=":material/tune:")

st.subheader("Raw vs cleaned KPI comparison")
cmp = analytics.raw_vs_cleaned(raw_scope)
cmp_view = cmp.copy()
for col in ("raw", "cleaned", "impact"):
    cmp_view[col] = [
        (ui.fmt_pp(v, 3) if (col == "impact" and u == "pp") else
         ui.fmt_pct(v, 3) if u == "pp" else
         (f"{v:+,.0f}" if col == "impact" else f"{v:,.0f}") if v is not None else config.NOT_AVAILABLE)
        for v, u in zip(cmp[col], cmp["unit"])
    ]
st.dataframe(cmp_view[["metric", "raw", "cleaned", "impact"]], hide_index=True, width="stretch",
             column_config={"metric": "Metric", "raw": "Raw (Unfiltered)",
                            "cleaned": "Cleaned (Deduplicated)", "impact": "Cleaned − Raw"})

st.subheader("Logged data-quality issues")
c1, c2 = st.columns([3, 2], gap="medium")
with c1:
    st.plotly_chart(charts.severity_breakdown(dq, title="Issues by code and severity"), width="stretch")
with c2:
    by_code = dq.groupby("issue_code").size().reindex(config.DQ_CODES, fill_value=0).rename("issues").reset_index()
    st.dataframe(by_code, hide_index=True, width="stretch", column_config={"issue_code": "Issue code"})
    by_status = dq.groupby("resolution_status").size().rename("issues").reset_index()
    st.dataframe(by_status, hide_index=True, width="stretch", column_config={"resolution_status": "Status"})

codes = st.multiselect("Show issue codes", list(config.DQ_CODES), default=list(config.DQ_CODES), key="dq_codes")
shown = dq[dq["issue_code"].isin(codes)].copy()
for col in ("programme_name", "period_label", "course_code"):
    shown[col] = shown[col].astype("object").where(shown[col].notna(), "Dataset-level")
st.dataframe(
    shown[["issue_id", "issue_code", "issue_type", "severity", "performance_id", "programme_name", "period_label",
           "course_code", "field_name", "observed_value", "issue_description", "resolution_status"]],
    hide_index=True, width="stretch",
    column_config={"performance_id": st.column_config.NumberColumn("performance_id", format="%d"),
                   "programme_name": "Programme", "period_label": "Period", "course_code": "Course"},
)
st.caption("Rows without a programme are dataset-level schema findings (performance_id is NULL).")

st.subheader("Live validation checks (raw scoped extract)")
st.dataframe(validation.run_all_checks(raw_scope), hide_index=True, width="stretch")

dups = validation.duplicate_pairs(raw_scope)
with st.expander(f"Duplicate course-period grain ({len(dups)} surplus row(s))", expanded=bool(len(dups))):
    if dups.empty:
        st.write("No duplicate (programme_id, period_id, course_id) keys in scope.")
    else:
        detail = validation.find_duplicate_keys(raw_scope)[
            ["performance_id", "programme_name", "period_label", "course_code", "assessment_type",
             "average_marks", "maximum_marks", "attendance_present_count", "passed_count"]]
        st.dataframe(dups, hide_index=True, width="stretch")
        st.dataframe(detail, hide_index=True, width="stretch")
        st.caption("Cleaned mode keeps the primary (lowest) performance_id of each grain.")

st.subheader("Live IQR outlier scan (performance_fact via view)")
st.caption("Tukey fences: Q1 − 1.5×IQR and Q3 + 1.5×IQR, computed on the raw scoped extract per metric. "
           "NULL values are skipped, never flagged.")
scan = statistics.iqr_outlier_scan(raw_scope)
fences = statistics.describe_metrics(raw_scope)[["label", "count", "q1", "q3", "iqr", "lower_fence",
                                                 "upper_fence", "outliers"]]
st.dataframe(fences, hide_index=True, width="stretch", column_config={
    c: st.column_config.NumberColumn(c, format="%.2f") for c in ("q1", "q3", "iqr", "lower_fence", "upper_fence")})
if scan.empty:
    st.success("No IQR outliers in scope.", icon=":material/check_circle:")
else:
    logged = set(dq.loc[dq["issue_code"] == "DQ-OUTLIER", "performance_id"].dropna().astype(int))
    scan = scan.assign(logged_as_DQ_OUTLIER=scan["performance_id"].astype(int).isin(logged))
    st.dataframe(scan, hide_index=True, width="stretch", column_config={
        "value": st.column_config.NumberColumn("Value", format="%.2f%%"),
        "lower_fence": st.column_config.NumberColumn("Lower fence", format="%.2f"),
        "upper_fence": st.column_config.NumberColumn("Upper fence", format="%.2f")})
    ui.csv_download(scan, f"iqr_outliers_{f.scope_slug}.csv", "Download outlier scan (CSV)", key="dq_scan_dl")
