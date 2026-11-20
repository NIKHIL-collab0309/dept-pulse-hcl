"""Page 07 — Statistics & EDA on row-level percentages (course-period records)."""

import streamlit as st

from src import charts, config, filters, statistics, ui_components as ui

user = ui.require_user()
f = filters.current_filters(user)
ui.page_header(user, "Statistics & EDA",
               "Distribution of row-level percentages. These describe spread; headline KPIs stay weighted.",
               f.dataset_mode)

df = filters.get_filtered_data(user, f)
if df.empty:
    ui.empty_state()
    st.stop()

c1, c2, c3 = st.columns([2, 2, 1])
metric = c1.selectbox("Metric", list(config.PCT_METRICS), format_func=lambda m: config.METRIC_LABELS[m],
                      key="eda_metric")
group_options = {"None": None, "Course category": "course_category", "Assessment type": "assessment_type"}
if user.is_dean:
    group_options = {"None": None, "Programme": "programme_name", **{k: v for k, v in group_options.items() if v}}
group_label = c2.selectbox("Group distribution by", list(group_options), key="eda_group")
group_col = group_options[group_label]
kind = c3.radio("Plot", ["Box", "Violin"], horizontal=True, key="eda_kind")

d = statistics.describe_series(df[metric])
if d["count"] == 0:
    st.info(f"{config.METRIC_LABELS[metric]}: {config.NOT_AVAILABLE_IN_DATASET} for the current filters.")
    st.stop()

ui.kpi_cards([
    ui.KpiCard("Count (non-NULL rows)", str(d["count"]), "N"),
    ui.KpiCard("Mean", ui.fmt_pct(d["mean"], 2), "MEAN", "Unweighted row mean"),
    ui.KpiCard("Median", ui.fmt_pct(d["median"], 2), "MEDIAN"),
    ui.KpiCard("Sample std (ddof=1)", "Not available" if d["std"] is None else f"{d['std']:.2f} pp", "STD"),
    ui.KpiCard("IQR", f"{d['iqr']:.2f} pp", "Q3 − Q1", f"Q1 {d['q1']:.2f}% · Q3 {d['q3']:.2f}%"),
    ui.KpiCard("IQR outliers", str(d["outliers"]), "TUKEY",
               f"Fences {d['lower_fence']:.1f}% – {d['upper_fence']:.1f}%"),
])

p1, p2 = st.columns(2, gap="medium")
with p1:
    st.plotly_chart(charts.distribution_box(df, metric, group_col, kind,
                                            title=f"{config.METRIC_LABELS[metric]} — {kind.lower()} plot"),
                    width="stretch")
with p2:
    bins = st.slider("Histogram bins", 5, 40, 20, key="eda_bins")
    st.plotly_chart(charts.distribution_histogram(df, metric, bins,
                                                  title=f"{config.METRIC_LABELS[metric]} — histogram",
                                                  fences=(d["lower_fence"], d["upper_fence"])), width="stretch")

st.subheader("Descriptive statistics — all metrics")
desc = statistics.describe_metrics(df)
num_cols = ["mean", "median", "min", "max", "std", "q1", "q3", "iqr", "lower_fence", "upper_fence", "skewness"]
st.dataframe(desc[["label", "count", *num_cols, "outliers"]], hide_index=True, width="stretch",
             column_config={"label": "Metric", **{c: st.column_config.NumberColumn(c, format="%.2f") for c in num_cols}})
st.caption("std is the sample standard deviation (ddof = 1); quartiles use linear interpolation. "
           "NULLs are dropped per metric.")

st.subheader("Pearson correlation matrix")
corr = statistics.correlation_matrix(df)
st.plotly_chart(charts.correlation_heatmap(corr, title="Pairwise Pearson r (pairwise-complete rows)"), width="stretch")
with st.expander("Observations per pair"):
    n = statistics.pairwise_n(df)
    n.index = [config.METRIC_LABELS[c] for c in n.index]
    n.columns = [config.METRIC_LABELS[c] for c in n.columns]
    st.dataframe(n, width="stretch")
    st.caption("Project and practical metrics exist only on their own course types, so some pairs share few "
               "or no rows; cells with fewer than 3 shared rows show n/a.")

flagged = statistics.flag_iqr_outliers(df, metric)
out_rows = flagged[flagged["is_outlier"]]
with st.expander(f"Outlier rows for {config.METRIC_LABELS[metric]} ({len(out_rows)})"):
    cols = ["performance_id", "programme_name", "period_label", "course_code", "course_category", metric,
            "outlier_side"]
    st.dataframe(out_rows[cols], hide_index=True, width="stretch")
