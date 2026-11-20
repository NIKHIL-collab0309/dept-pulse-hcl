"""Page 01 — Overview: consolidated KPIs, pp deltas, summary table, trends, scoped CSV."""

import streamlit as st

from src import analytics, charts, config, filters, ui_components as ui

user = ui.require_user()
f = filters.current_filters(user)
ui.page_header(user, "Overview", "Consolidated weighted KPIs for your scope and selected filters.", f.dataset_mode)

df = filters.get_filtered_data(user, f)
df_all_periods = filters.get_filtered_data(user, f, apply_periods=False)
if df.empty:
    ui.empty_state()
    st.stop()

kpis = analytics.compute_kpis(df)
deltas = analytics.latest_vs_prior(df_all_periods, f.period_sequences)

cards = ui.kpi_cards_from_values(kpis, deltas)
cards.append(ui.KpiCard(
    label=config.ENROLMENT_LABEL, kpi_id="VOLUME",
    value=ui.fmt_int(analytics.total_course_seat_enrolments(df)),
    sub="Not unique students — sum of seats across courses",
))
ui.kpi_cards(cards)
st.caption(
    f"Cards show the selected period(s) combined. Delta badges compare the latest selected period "
    f"({deltas.get('current_label') or '—'}) with the one before it, in percentage points. "
    + config.ENROLMENT_CAUTION
)

group_col, group_label = analytics.group_dimension(user)
summary_by = [group_col] if user.is_dean else ["course_code", "course_name", "course_category"]
summary = analytics.grouped_kpis(df, summary_by)

st.subheader(f"{group_label} summary")
labels = {"programme_name": "Programme"} if user.is_dean else {
    "course_code": "Course", "course_name": "Course name", "course_category": "Category"}
ui.show_kpi_table(summary, labels)
st.caption("Blank KPI cells mean the metric is not available for that slice (no eligible records) — never 0.")

left, right = st.columns(2, gap="medium")
with left:
    if user.is_dean:
        st.plotly_chart(charts.kpi_grouped_bar(summary, "programme_name", "Programme",
                                               title="KPIs by programme"), width="stretch")
    else:
        by_cat = analytics.grouped_kpis(df, "course_category")
        st.plotly_chart(charts.kpi_grouped_bar(by_cat, "course_category", "Course category",
                                               title="KPIs by course category"), width="stretch")
with right:
    trend = analytics.period_trend(df_all_periods)
    trend = trend[trend["period_label"].isin(f.period_labels)]
    st.plotly_chart(charts.multi_kpi_trend(trend, title="KPI trend by academic period"), width="stretch")

with st.expander("KPI numerators and denominators"):
    comp = analytics.kpi_components(df)
    st.dataframe(comp, hide_index=True, width="stretch", column_config={
        "value": ui.pct_column("Value"),
        "numerator": st.column_config.NumberColumn("Numerator", format="%.1f"),
        "denominator": st.column_config.NumberColumn("Denominator", format="%.1f"),
    })
ui.formula_expander()

scope = "ALL" if user.is_dean and len(f.programme_codes) == 4 else "-".join(f.programme_codes)
mode = "cleaned" if f.dataset_mode == config.MODE_CLEANED else "raw"
ui.csv_download(df, f"dpa_{scope}_{mode}_{config.DATA_VERSION}.csv", key="overview_download")
