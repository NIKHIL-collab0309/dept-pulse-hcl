"""Page 05 — Project & Practical Analysis (KPI-04, KPI-05). NULLs shown as 'Not available', never 0."""

import streamlit as st

from src import analytics, charts, config, filters, ui_components as ui

user = ui.require_user()
f = filters.current_filters(user)
ui.page_header(user, "Project & Practical Analysis",
               "Project completion (completed ÷ assigned) and practical score performance.", f.dataset_mode)

df = filters.get_filtered_data(user, f)
df_all_periods = filters.get_filtered_data(user, f, apply_periods=False)
if df.empty:
    ui.empty_state()
    st.stop()

NA = config.NOT_AVAILABLE_IN_DATASET
kpis = analytics.compute_kpis(df)
avail = analytics.availability(df)
deltas = analytics.latest_vs_prior(df_all_periods, f.period_sequences)
ui.kpi_cards(ui.kpi_cards_from_values(kpis, deltas, keys=["project", "practical"], na_text=NA) + [
    ui.KpiCard("Rows with project data", str(avail["project_rows"]), "COVERAGE",
               "projects_assigned > 0 and completed not NULL"),
    ui.KpiCard("Rows with practical scores", str(avail["practical_rows"]), "COVERAGE",
               "practical_average_score not NULL"),
])
st.caption(
    "Project and practical fields are NULL on courses where they do not apply. Those rows are excluded from "
    "KPI-04/KPI-05 denominators and are never counted as 0. "
    + (f"{avail['project_rows_null_completed']} project row(s) have assignments but no completion figure yet."
       if avail["project_rows_null_completed"] else "")
)

group_col, group_label = ("programme_name", "Programme") if user.is_dean else ("course_code", "Course")

tab_proj, tab_prac = st.tabs(["Project completion (KPI-04)", "Practical scores (KPI-05)"])

with tab_proj:
    if kpis["project"] is None:
        st.info(f"Project completion: **{NA}** for the current filters.", icon=":material/info:")
    else:
        proj = analytics.grouped_kpis(df, [group_col] + (["course_name"] if not user.is_dean else []))
        proj = proj[proj["projects_assigned_used"].notna()]
        view = ui.na_text_frame(proj, ["project"], NA)
        st.dataframe(view[[c for c in [group_col, "course_name", "projects_assigned_used",
                                        "projects_completed_used", "project"] if c in view]],
                     hide_index=True, width="stretch", column_config={
                         group_col: group_label, "course_name": "Course name",
                         "projects_assigned_used": st.column_config.NumberColumn("Projects assigned", format="%d"),
                         "projects_completed_used": st.column_config.NumberColumn("Projects completed", format="%d"),
                         "project": "Completion %"})
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.plotly_chart(charts.single_kpi_bar(proj, group_col, group_label, "project",
                                                  title=f"Project completion % by {group_label.lower()}",
                                                  horizontal=not user.is_dean), width="stretch")
        with c2:
            trend = analytics.period_trend(df_all_periods, "programme_name" if user.is_dean else None)
            trend = trend[trend["period_label"].isin(f.period_labels)]
            st.plotly_chart(charts.kpi_trend_line(trend, "project", "programme_name" if user.is_dean else None,
                                                  title="Project completion % by period"), width="stretch")

with tab_prac:
    if kpis["practical"] is None:
        st.info(f"Practical average: **{NA}** for the current filters.", icon=":material/info:")
    else:
        prac = analytics.grouped_kpis(df, [group_col] + (["course_name"] if not user.is_dean else []))
        prac = prac[prac["practical"].notna()]
        st.dataframe(prac[[c for c in [group_col, "course_name", "records", "practical"] if c in prac]],
                     hide_index=True, width="stretch", column_config={
                         group_col: group_label, "course_name": "Course name",
                         "records": st.column_config.NumberColumn("Rows", format="%d"),
                         "practical": ui.pct_column("Practical average %", config.KPI_FORMULAS["practical"])})
        c3, c4 = st.columns(2, gap="medium")
        with c3:
            st.plotly_chart(charts.single_kpi_bar(prac, group_col, group_label, "practical",
                                                  title=f"Practical average % by {group_label.lower()}",
                                                  horizontal=not user.is_dean), width="stretch")
        with c4:
            trend = analytics.period_trend(df_all_periods, "programme_name" if user.is_dean else None)
            trend = trend[trend["period_label"].isin(f.period_labels)]
            st.plotly_chart(charts.kpi_trend_line(trend, "practical", "programme_name" if user.is_dean else None,
                                                  title="Practical average % by period"), width="stretch")

ui.formula_expander(["project", "practical"])
