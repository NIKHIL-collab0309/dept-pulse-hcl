"""Page 03 — Attendance Analysis (KPI-01)."""

import streamlit as st

from src import analytics, charts, config, filters, ui_components as ui

user = ui.require_user()
f = filters.current_filters(user)
ui.page_header(user, "Attendance Analysis",
               "Weighted attendance: present student-sessions ÷ eligible student-sessions.", f.dataset_mode)

df = filters.get_filtered_data(user, f)
df_all_periods = filters.get_filtered_data(user, f, apply_periods=False)
if df.empty:
    ui.empty_state()
    st.stop()

deltas = analytics.latest_vs_prior(df_all_periods, f.period_sequences)
comp = analytics.kpi_components(df).set_index("kpi_id").loc["KPI-01"]
ui.kpi_cards([
    ui.KpiCard("Overall Attendance %", ui.fmt_pct(comp["value"]), "KPI-01", "Weighted ratio of sums",
               deltas.get("attendance", {}).get("pp"),
               f"{deltas.get('current_label')} vs {deltas.get('prior_label')}" if deltas.get("prior_label")
               else "No prior period"),
    ui.KpiCard("Present student-sessions", ui.fmt_int(comp["numerator"]), "NUMERATOR",
               "SUM(attendance_present_count)"),
    ui.KpiCard("Eligible student-sessions", ui.fmt_int(comp["denominator"]), "DENOMINATOR",
               "SUM(attendance_eligible_count)"),
])

group_col, group_label = ("programme_name", "Programme") if user.is_dean else ("course_category", "Course category")

st.subheader("Numerator / denominator breakdown")
breakdown = analytics.grouped_kpis(df, [group_col, "period_sequence", "period_label"])
st.dataframe(
    breakdown[[group_col, "period_label", "attendance_present", "attendance_eligible", "attendance"]],
    hide_index=True, width="stretch",
    column_config={
        group_col: group_label, "period_label": "Period",
        "attendance_present": st.column_config.NumberColumn("Present sessions", format="%d"),
        "attendance_eligible": st.column_config.NumberColumn("Eligible sessions", format="%d"),
        "attendance": ui.pct_column("Attendance %", config.KPI_FORMULAS["attendance"]),
    },
)

c1, c2 = st.columns(2, gap="medium")
with c1:
    trend = analytics.period_trend(df_all_periods, group_col)
    trend = trend[trend["period_label"].isin(f.period_labels)]
    st.plotly_chart(charts.kpi_trend_line(trend, "attendance", group_col,
                                          title=f"Attendance trend (period sequence 1 → 4) by {group_label.lower()}"),
                    width="stretch")
with c2:
    by_group = analytics.grouped_kpis(df, group_col)
    st.plotly_chart(charts.attendance_composition(by_group, group_col, group_label,
                                                  title="Present vs absent eligible sessions"), width="stretch")

st.subheader("Course-category attendance comparison")
by_cat = analytics.grouped_kpis(df, "course_category")
st.plotly_chart(charts.single_kpi_bar(by_cat, "course_category", "Course category", "attendance",
                                      title="Attendance % by course category",
                                      reference=config.LOW_ATTENDANCE_THRESHOLD), width="stretch")

st.subheader("Low-attendance watchlist")
threshold = st.slider("Flag course-period slices below (%)", 50.0, 95.0, config.LOW_ATTENDANCE_THRESHOLD, 1.0,
                      key="att_threshold")
watch = analytics.low_attendance_watchlist(df, threshold)
if watch.empty:
    st.success(f"No course-period slice is below {threshold:.0f}% attendance.", icon=":material/check_circle:")
else:
    st.dataframe(
        watch[["programme_name", "period_label", "course_code", "course_name", "course_category",
               "attendance_present", "attendance_eligible", "attendance", "gap_pp"]],
        hide_index=True, width="stretch",
        column_config={
            "programme_name": "Programme", "period_label": "Period", "course_code": "Course",
            "course_name": "Course name", "course_category": "Category",
            "attendance_present": st.column_config.NumberColumn("Present", format="%d"),
            "attendance_eligible": st.column_config.NumberColumn("Eligible", format="%d"),
            "attendance": ui.pct_column("Attendance %"),
            "gap_pp": ui.pp_column("Gap to threshold"),
        },
    )
    ui.csv_download(watch, f"attendance_watchlist_{f.scope_slug}.csv", "Download watchlist (CSV)",
                    key="att_watch_dl")

ui.formula_expander(["attendance"])
