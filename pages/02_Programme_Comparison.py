"""Page 02 — Programme Comparison (Dean) / Course & Category Comparison within the department (HOD)."""

import streamlit as st

from src import analytics, charts, config, filters, ui_components as ui

user = ui.require_user()
f = filters.current_filters(user)

if user.is_dean:
    title = "Programme Comparison"
    subtitle = "Side-by-side weighted KPIs across B.Tech, MCA, BCA and MBA."
else:
    title = "Course & Category Comparison (My Department)"
    subtitle = f"Core, Elective, Practical and Project courses within {user.programme_name} only."
ui.page_header(user, title, subtitle, f.dataset_mode)

df = filters.get_filtered_data(user, f)
df_all_periods = filters.get_filtered_data(user, f, apply_periods=False)
if df.empty:
    ui.empty_state()
    st.stop()

kpi_key = st.selectbox(
    "KPI to rank", list(config.KPI_KEYS), format_func=lambda k: f"{config.KPI_IDS[k]} {config.KPI_LABELS[k]}",
    key="cmp_kpi",
)
kpi_label = config.KPI_LABELS[kpi_key]

if user.is_dean:
    # ---- Cross-programme comparison -------------------------------------
    if len(f.programme_codes) < 2:
        st.info("Select **All Programmes** in the sidebar to compare programmes side by side.",
                icon=":material/info:")
    table = analytics.grouped_kpis(df, "programme_name")
    ui.extremes_callouts(kpi_label, analytics.kpi_extremes(df, "programme_name", kpi_key), "Programme")

    st.subheader("All KPIs by programme")
    ui.show_kpi_table(table, {"programme_name": "Programme"})
    st.plotly_chart(charts.kpi_grouped_bar(table, "programme_name", "Programme",
                                           title="Weighted KPIs by programme"), width="stretch")

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        trend = analytics.period_trend(df_all_periods, "programme_name")
        trend = trend[trend["period_label"].isin(f.period_labels)]
        st.plotly_chart(charts.kpi_trend_line(trend, kpi_key, "programme_name",
                                              title=f"{kpi_label} by period and programme"), width="stretch")
    with c2:
        by_cat = analytics.grouped_kpis(df, ["programme_name", "course_category"])
        fig = charts.single_kpi_bar(by_cat, "programme_name", "Programme", kpi_key,
                                    title=f"{kpi_label} by programme and course category",
                                    color_col="course_category")
        fig.update_layout(barmode="group")
        st.plotly_chart(fig, width="stretch")

    st.subheader("Period-over-period movement (pp)")
    deltas = analytics.period_deltas(analytics.period_trend(df_all_periods, "programme_name"),
                                     [kpi_key], by="programme_name")
    deltas = deltas[deltas["period_label"].isin(f.period_labels)]
    st.dataframe(deltas[["programme_name", "period_label", kpi_key, f"{kpi_key}_pp"]], hide_index=True,
                 width="stretch", column_config={
                     "programme_name": "Programme", "period_label": "Period",
                     kpi_key: ui.pct_column(kpi_label), f"{kpi_key}_pp": ui.pp_column("Change vs prior period")})
else:
    # ---- Within-department comparison ----------------------------------
    cat_table = analytics.grouped_kpis(df, "course_category")
    course_table = analytics.grouped_kpis(df, ["course_code", "course_name", "course_category"])

    tab_cat, tab_course = st.tabs(["By course category", "By course"])
    with tab_cat:
        ui.extremes_callouts(kpi_label, analytics.kpi_extremes(df, "course_category", kpi_key), "Category")
        ui.show_kpi_table(cat_table, {"course_category": "Category"})
        st.plotly_chart(charts.kpi_grouped_bar(cat_table, "course_category", "Course category",
                                               title=f"Weighted KPIs by course category — {user.programme_name}"),
                        width="stretch")
        trend = analytics.period_trend(df_all_periods, "course_category")
        trend = trend[trend["period_label"].isin(f.period_labels)]
        st.plotly_chart(charts.kpi_trend_line(trend, kpi_key, "course_category",
                                              title=f"{kpi_label} by period and category"), width="stretch")
    with tab_course:
        ui.extremes_callouts(kpi_label, analytics.kpi_extremes(df, "course_code", kpi_key), "Course")
        ui.show_kpi_table(course_table, {"course_code": "Course", "course_name": "Course name",
                                         "course_category": "Category"})
        st.plotly_chart(charts.single_kpi_bar(course_table, "course_code", "Course", kpi_key,
                                              title=f"{kpi_label} by course", color_col="course_category",
                                              horizontal=True), width="stretch")

ui.formula_expander([kpi_key])
