"""Plotly figure builders (dark theme, validated categorical palette, single y-axis only)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src import config

T = config.THEME
PERIOD_ORDER = list(config.PERIOD_LABELS)
PCT_HOVER = "%{y:.1f}%"


def _style(fig: go.Figure, title: str | None = None, y_title: str | None = None,
           x_title: str | None = None, height: int = 400, pct_axis: bool = True) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        title=dict(text=title or "", x=0, xanchor="left", font=dict(size=15, color=T["text"])),
        paper_bgcolor=T["surface"],
        plot_bgcolor=T["surface"],
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", color=T["text_secondary"], size=12),
        height=height,
        margin=dict(l=56, r=24, t=64 if title else 32, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title_text="",
                    font=dict(color=T["text_secondary"])),
        hoverlabel=dict(bgcolor=T["background"], bordercolor=T["grid"], font=dict(color=T["text"])),
        bargap=0.25,
        bargroupgap=0.06,
        barcornerradius=4,
    )
    fig.update_xaxes(title_text=x_title or "", showgrid=False, linecolor=T["baseline"],
                     tickfont=dict(color=T["muted"]), zeroline=False)
    fig.update_yaxes(title_text=y_title or "", gridcolor=T["grid"], gridwidth=1, linecolor=T["baseline"],
                     tickfont=dict(color=T["muted"]), zeroline=False)
    if pct_axis:
        fig.update_yaxes(ticksuffix="%")
    fig.update_traces(selector=dict(type="bar"), marker_line_color=T["surface"], marker_line_width=2)
    return fig


def _color_map_for(column: str) -> Mapping[str, str] | None:
    return {
        "programme_name": config.PROGRAMME_COLORS,
        "course_category": config.CATEGORY_COLORS,
        "assessment_type": config.ASSESSMENT_COLORS,
        "KPI": config.KPI_COLORS,
    }.get(column)


def _category_orders(columns: Sequence[str]) -> dict[str, list[str]]:
    orders = {
        "programme_name": list(config.PROGRAMME_NAMES.values()),
        "course_category": list(config.COURSE_CATEGORIES),
        "assessment_type": list(config.ASSESSMENT_TYPES),
        "period_label": PERIOD_ORDER,
        "KPI": list(config.KPI_LABELS.values()),
    }
    return {c: orders[c] for c in columns if c in orders}


def empty_figure(message: str = config.NOT_AVAILABLE_IN_DATASET, height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=14, color=T["muted"]),
                       xref="paper", yref="paper", x=0.5, y=0.5)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _style(fig, height=height, pct_axis=False)


def kpi_grouped_bar(table: pd.DataFrame, group_col: str, group_label: str,
                    kpis: Sequence[str] = config.KPI_KEYS, title: str | None = None) -> go.Figure:
    """Grouped bars: one cluster per group, one bar per KPI (all on one % axis)."""
    cols = [k for k in kpis if k in table]
    long = table.melt(id_vars=[group_col], value_vars=cols, var_name="kpi_key", value_name="value")
    long = long.dropna(subset=["value"])
    if long.empty:
        return empty_figure()
    long["KPI"] = long["kpi_key"].map(config.KPI_LABELS)
    fig = px.bar(long, x=group_col, y="value", color="KPI", barmode="group",
                 color_discrete_map=config.KPI_COLORS, category_orders=_category_orders([group_col, "KPI"]),
                 labels={group_col: group_label, "value": "Rate (%)"})
    fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: " + PCT_HOVER + "<extra></extra>")
    return _style(fig, title, "Rate (%)", group_label, height=430)


def single_kpi_bar(table: pd.DataFrame, group_col: str, group_label: str, kpi: str,
                   title: str | None = None, color_col: str | None = None, horizontal: bool = False,
                   reference: float | None = None) -> go.Figure:
    data = table.dropna(subset=[kpi])
    if data.empty:
        return empty_figure()
    color_col = color_col or (group_col if _color_map_for(group_col) else None)
    kwargs = dict(color=color_col, color_discrete_map=_color_map_for(color_col) if color_col else None,
                  category_orders=_category_orders([group_col] + ([color_col] if color_col else [])),
                  labels={group_col: group_label, kpi: config.KPI_LABELS.get(kpi, kpi)})
    if horizontal:
        data = data.sort_values(kpi)
        fig = px.bar(data, y=group_col, x=kpi, orientation="h", **kwargs)
        fig.update_traces(hovertemplate="%{y}: %{x:.1f}%<extra></extra>")
        fig = _style(fig, title, None, config.KPI_LABELS.get(kpi, kpi), height=max(320, 26 * len(data) + 120),
                     pct_axis=False)
        fig.update_xaxes(ticksuffix="%", gridcolor=T["grid"], showgrid=True)
        fig.update_yaxes(showgrid=False)
        if reference is not None:
            fig.add_vline(x=reference, line_dash="dash", line_color=T["muted"],
                          annotation_text=f"{reference:.0f}% threshold", annotation_font_color=T["muted"])
        return fig
    fig = px.bar(data, x=group_col, y=kpi, **kwargs)
    fig.update_traces(hovertemplate="%{x}: " + PCT_HOVER + "<extra></extra>")
    fig = _style(fig, title, config.KPI_LABELS.get(kpi, kpi), group_label)
    if color_col == group_col:
        fig.update_layout(showlegend=False)
    if reference is not None:
        fig.add_hline(y=reference, line_dash="dash", line_color=T["muted"],
                      annotation_text=f"{reference:.0f}% threshold", annotation_font_color=T["muted"])
    return fig


def kpi_trend_line(trend: pd.DataFrame, kpi: str, color_col: str | None = None,
                   title: str | None = None) -> go.Figure:
    """KPI across period_sequence 1 → 4 (x labelled with period_label)."""
    data = trend.dropna(subset=[kpi]).sort_values("period_sequence")
    if data.empty:
        return empty_figure()
    fig = px.line(data, x="period_label", y=kpi, color=color_col, markers=True,
                  color_discrete_map=_color_map_for(color_col) if color_col else None,
                  category_orders=_category_orders(["period_label"] + ([color_col] if color_col else [])),
                  labels={"period_label": "Academic period", kpi: config.KPI_LABELS.get(kpi, kpi)})
    if not color_col:
        fig.update_traces(line_color=config.SERIES_COLORS[0], marker_color=config.SERIES_COLORS[0])
    fig.update_traces(line_width=2, marker_size=9, hovertemplate="%{x}: " + PCT_HOVER + "<extra>%{fullData.name}</extra>")
    return _style(fig, title, config.KPI_LABELS.get(kpi, kpi), "Academic period")


def multi_kpi_trend(trend: pd.DataFrame, kpis: Sequence[str] = config.KPI_KEYS,
                    title: str | None = None) -> go.Figure:
    cols = [k for k in kpis if k in trend]
    long = trend.melt(id_vars=["period_sequence", "period_label"], value_vars=cols,
                      var_name="kpi_key", value_name="value").dropna(subset=["value"])
    if long.empty:
        return empty_figure()
    long["KPI"] = long["kpi_key"].map(config.KPI_LABELS)
    long = long.sort_values("period_sequence")
    fig = px.line(long, x="period_label", y="value", color="KPI", markers=True,
                  color_discrete_map=config.KPI_COLORS, category_orders=_category_orders(["period_label", "KPI"]),
                  labels={"period_label": "Academic period", "value": "Rate (%)"})
    fig.update_traces(line_width=2, marker_size=9, hovertemplate="%{x}: " + PCT_HOVER + "<extra>%{fullData.name}</extra>")
    return _style(fig, title, "Rate (%)", "Academic period", height=430)


def attendance_composition(table: pd.DataFrame, group_col: str, group_label: str,
                           title: str | None = None) -> go.Figure:
    """Stacked present vs absent eligible sessions (counts, not %)."""
    data = table.dropna(subset=["attendance_eligible"]).copy()
    if data.empty:
        return empty_figure()
    data["Absent (eligible − present)"] = data["attendance_eligible"] - data["attendance_present"]
    data["Present"] = data["attendance_present"]
    long = data.melt(id_vars=[group_col], value_vars=["Present", "Absent (eligible − present)"],
                     var_name="Sessions", value_name="count")
    fig = px.bar(long, x=group_col, y="count", color="Sessions", barmode="stack",
                 color_discrete_map={"Present": config.SERIES_COLORS[0],
                                     "Absent (eligible − present)": config.SERIES_COLORS[1]},
                 category_orders=_category_orders([group_col]), labels={group_col: group_label})
    fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:,.0f} sessions<extra></extra>")
    return _style(fig, title, "Student-sessions", group_label, pct_axis=False)


def appeared_vs_passed(table: pd.DataFrame, group_col: str, group_label: str,
                       title: str | None = None) -> go.Figure:
    data = table.dropna(subset=["appeared"])
    if data.empty:
        return empty_figure()
    long = data.melt(id_vars=[group_col], value_vars=["appeared", "passed"], var_name="Count", value_name="n")
    long["Count"] = long["Count"].map({"appeared": "Appeared", "passed": "Passed"})
    fig = px.bar(long, x=group_col, y="n", color="Count", barmode="group",
                 color_discrete_map={"Appeared": config.SERIES_COLORS[0], "Passed": config.SERIES_COLORS[2]},
                 category_orders=_category_orders([group_col]), labels={group_col: group_label})
    fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:,.0f}<extra></extra>")
    return _style(fig, title, "Students (course-seat basis)", group_label, pct_axis=False)


def scatter_with_trendline(df: pd.DataFrame, x: str, y: str, color_col: str | None = None,
                           title: str | None = None) -> go.Figure:
    """Row-level scatter with one overall OLS trendline (statsmodels)."""
    data = df.dropna(subset=[x, y])
    if len(data) < 3:
        return empty_figure()
    # Scatter puts every colour pair side by side; only the first 3 slots stay CVD-distinct, so cap at 3
    if color_col and data[color_col].nunique() > 3:
        color_col = None
    fig = px.scatter(
        data, x=x, y=y, color=color_col, trendline="ols", trendline_scope="overall",
        trendline_color_override=T["primary"],
        color_discrete_map=_color_map_for(color_col) if color_col else None,
        category_orders=_category_orders([color_col]) if color_col else None,
        hover_data={c: True for c in ("course_code", "period_label") if c in data},
        labels={x: config.METRIC_LABELS.get(x, x), y: config.METRIC_LABELS.get(y, y)},
    )
    fig.update_traces(selector=dict(mode="markers"), marker=dict(size=9, line=dict(width=1.5, color=T["surface"])),
                      opacity=0.9)
    if not color_col:
        fig.update_traces(selector=dict(mode="markers"), marker_color=config.SERIES_COLORS[0])
    fig = _style(fig, title, config.METRIC_LABELS.get(y, y), config.METRIC_LABELS.get(x, x), height=460)
    fig.update_xaxes(ticksuffix="%", showgrid=True, gridcolor=T["grid"])
    return fig


def distribution_box(df: pd.DataFrame, metric: str, group_col: str | None, kind: str = "Box",
                     title: str | None = None) -> go.Figure:
    data = df.dropna(subset=[metric])
    if data.empty:
        return empty_figure()
    cmap = _color_map_for(group_col) if group_col else None
    common = dict(y=metric, x=group_col, color=group_col, color_discrete_map=cmap,
                  category_orders=_category_orders([group_col]) if group_col else None,
                  labels={metric: config.METRIC_LABELS.get(metric, metric)})
    if kind == "Violin":
        fig = px.violin(data, box=True, points="outliers", **common)
    else:
        fig = px.box(data, points="outliers", **common)
    if not group_col:
        fig.update_traces(marker_color=config.SERIES_COLORS[0], line_color=config.SERIES_COLORS[0])
    fig = _style(fig, title, config.METRIC_LABELS.get(metric, metric), None)
    fig.update_layout(showlegend=False)
    return fig


def distribution_histogram(df: pd.DataFrame, metric: str, bins: int = 20, title: str | None = None,
                           fences: tuple[float | None, float | None] | None = None) -> go.Figure:
    data = df.dropna(subset=[metric])
    if data.empty:
        return empty_figure()
    fig = px.histogram(data, x=metric, nbins=bins, labels={metric: config.METRIC_LABELS.get(metric, metric)})
    fig.update_traces(marker_color=config.SERIES_COLORS[0], hovertemplate="%{x}: %{y} rows<extra></extra>")
    fig = _style(fig, title, "Course-period rows", config.METRIC_LABELS.get(metric, metric), pct_axis=False)
    fig.update_xaxes(ticksuffix="%")
    fig.update_layout(bargap=0.04)
    if fences:
        for value, label in zip(fences, ("Lower fence", "Upper fence")):
            if value is not None:
                fig.add_vline(x=value, line_dash="dash", line_color=T["muted"],
                              annotation_text=f"{label} {value:.1f}%", annotation_font_color=T["muted"])
    return fig


def correlation_heatmap(corr: pd.DataFrame, title: str | None = None) -> go.Figure:
    if corr.empty:
        return empty_figure()
    labels = [config.METRIC_LABELS.get(c, c) for c in corr.columns]
    text = corr.map(lambda v: "n/a" if pd.isna(v) else f"{v:.2f}").to_numpy()
    fig = go.Figure(go.Heatmap(
        z=corr.to_numpy(), x=labels, y=labels, zmin=-1, zmax=1, colorscale=config.DIVERGING_SCALE,
        text=text, texttemplate="%{text}", textfont=dict(color=T["text"]),
        hovertemplate="%{y} × %{x}<br>r = %{z:.3f}<extra></extra>", xgap=2, ygap=2,
        colorbar=dict(title=dict(text="Pearson r"), tickfont=dict(color=T["muted"])),
    ))
    fig = _style(fig, title, None, None, height=460, pct_axis=False)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return fig


def severity_breakdown(dq: pd.DataFrame, title: str | None = None) -> go.Figure:
    """Issues per DQ code stacked by severity (status colours, with labels — never colour alone)."""
    if dq.empty:
        return empty_figure("No data-quality issues in scope")
    counts = dq.groupby(["issue_code", "severity"]).size().reset_index(name="issues")
    fig = px.bar(counts, x="issue_code", y="issues", color="severity", barmode="stack", text="issues",
                 color_discrete_map=config.STATUS_COLORS,
                 category_orders={"issue_code": list(config.DQ_CODES), "severity": list(config.SEVERITIES)},
                 labels={"issue_code": "Issue code", "severity": "Severity"})
    fig.update_traces(textposition="inside", hovertemplate="%{x}<br>%{fullData.name}: %{y}<extra></extra>")
    for trace in fig.data:  # dark ink only on the light "warning" fill
        trace.textfont = dict(color="#0b0b0b" if trace.name == "Medium" else "#ffffff")
    return _style(fig, title, "Issues", "Issue code", pct_axis=False)
