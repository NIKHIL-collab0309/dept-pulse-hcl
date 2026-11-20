"""Page 04 — Results Analysis (KPI-02, KPI-03, KPI-07)."""

import streamlit as st

from src import analytics, charts, config, filters, statistics, ui_components as ui

user = ui.require_user()
f = filters.current_filters(user)
ui.page_header(user, "Results Analysis",
               "Pass rates, assessment scores on a common % scale, and the attendance–marks relationship.",
               f.dataset_mode)

df = filters.get_filtered_data(user, f)
df_all_periods = filters.get_filtered_data(user, f, apply_periods=False)
if df.empty:
    ui.empty_state()
    st.stop()

kpis = analytics.compute_kpis(df)
deltas = analytics.latest_vs_prior(df_all_periods, f.period_sequences)
ui.kpi_cards(ui.kpi_cards_from_values(kpis, deltas, keys=["pass", "assessment"]) + [
    ui.KpiCard("Students appeared", ui.fmt_int(df["appeared_count"].sum()), "COUNT", "Course-seat basis"),
    ui.KpiCard("Students passed", ui.fmt_int(df["passed_count"].sum()), "COUNT", "Course-seat basis"),
])

group_col, group_label = ("programme_name", "Programme") if user.is_dean else ("course_category", "Course category")

st.subheader("Pass % across semesters")
trend = analytics.period_deltas(analytics.period_trend(df_all_periods, group_col), ["pass"], by=group_col)
trend = trend[trend["period_label"].isin(f.period_labels)]
c1, c2 = st.columns([3, 2], gap="medium")
with c1:
    st.plotly_chart(charts.kpi_trend_line(trend, "pass", group_col, title=f"Pass % by period and {group_label.lower()}"),
                    width="stretch")
with c2:
    st.dataframe(trend[[group_col, "period_label", "appeared", "passed", "pass", "pass_pp"]],
                 hide_index=True, width="stretch", height=380, column_config={
                     group_col: group_label, "period_label": "Period",
                     "appeared": st.column_config.NumberColumn("Appeared", format="%d"),
                     "passed": st.column_config.NumberColumn("Passed", format="%d"),
                     "pass": ui.pct_column("Pass %"), "pass_pp": ui.pp_column("Δ vs prior")})

st.subheader("Appeared vs passed")
by_group = analytics.grouped_kpis(df, group_col)
st.plotly_chart(charts.appeared_vs_passed(by_group, group_col, group_label,
                                          title=f"Appeared and passed by {group_label.lower()}"), width="stretch")

st.subheader("Assessment-type score comparison")
st.caption("Each type is normalised from its native scale (Internal /50, End-Semester /100, Practical /50) "
           "and weighted by assessed_count. Rows with NULL average_marks are excluded, not zeroed.")
breakdown = analytics.assessment_breakdown(df)
c3, c4 = st.columns([2, 3], gap="medium")
with c3:
    st.dataframe(breakdown, hide_index=True, width="stretch", column_config={
        "assessment_type": "Assessment type", "scale": "Native scale",
        "records": st.column_config.NumberColumn("Rows", format="%d"),
        "rows_with_marks": st.column_config.NumberColumn("Rows with marks", format="%d"),
        "weighted_avg_marks": st.column_config.NumberColumn("Weighted avg (native)", format="%.2f"),
        "assessment": ui.pct_column("Normalised %")})
with c4:
    st.plotly_chart(charts.single_kpi_bar(breakdown, "assessment_type", "Assessment type", "assessment",
                                          title="Average assessment % by type"), width="stretch")

st.subheader("Attendance vs marks")
scatter_color = "programme_name" if user.is_dean and len(f.programme_codes) > 1 else "course_category"
st.plotly_chart(charts.scatter_with_trendline(df, "attendance_pct", "average_marks_pct", scatter_color,
                                              title="Row-level attendance % vs average marks % (OLS trendline)"),
                width="stretch")
fit = statistics.ols_fit(df["attendance_pct"], df["average_marks_pct"])
corr = statistics.pearson_test(df["attendance_pct"], df["average_marks_pct"])
if fit["slope"] is not None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rows used", fit["n"])
    m2.metric("Slope", f"{fit['slope']:.2f} pp per pp")
    m3.metric("R²", f"{fit['r_squared']:.3f}")
    m4.metric("Pearson r", f"{corr['r']:.3f}", help=f"p-value = {corr['p_value']:.2g}")
    st.caption("Association only — synthetic data, and correlation does not imply causation.")
else:
    st.info(config.NOT_AVAILABLE_IN_DATASET)

ui.formula_expander(["pass", "assessment"])
