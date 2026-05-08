"""
Página 1 — Customer Value.

KPIs detallados, evolución temporal de ingresos/margen y distribución del
CLTV con curva de Pareto.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from app.theme import (
    COLORS,
    apply_theme,
    inject_css,
    render_sidebar,
    page_header,
    section_header,
    fmt_eur,
    fmt_int,
    fmt_pct,
)
from app.data_access import (
    load_global_kpis,
    load_monthly_sales,
    load_customer_value,
)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Customer Value", layout="wide")
inject_css()
render_sidebar()

page_header(
    "Customer Value",
    "Vista ejecutiva del valor del cliente · KPIs, evolución temporal "
    "y distribución del CLTV",
)


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
kpis     = load_global_kpis()
df_month = load_monthly_sales()
df_value = load_customer_value()


# ---------------------------------------------------------------------------
# KPIs (8 tarjetas, 2 filas)
# ---------------------------------------------------------------------------
section_header("Resumen del negocio")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Ingresos totales", fmt_eur(kpis["total_revenue"]))
with c2:
    st.metric(
        "Margen bruto",
        fmt_eur(kpis["total_margin"]),
        delta=f"{kpis['margin_pct']:.1f} % sobre ingresos",
    )
with c3:
    st.metric("Clientes únicos", fmt_int(kpis["total_customers"]))
with c4:
    st.metric(
        "Pedidos",
        fmt_int(int(kpis["total_orders"])),
        delta=f"{fmt_int(int(kpis['total_lines']))} líneas de venta",
    )

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(
        "Margen perdido en devoluciones",
        fmt_eur(kpis["margin_lost"]),
    )
with c2:
    avg_clv_pred = float(df_value["cltv_predicted_12m"].mean())
    st.metric(
        "CLTV medio · 12m",
        fmt_eur(avg_clv_pred, 2),
        delta="BG/NBD + Gamma-Gamma",
    )
with c3:
    avg_alive = float(df_value["alive_probability"].mean()) * 100
    st.metric(
        "Probabilidad alive media",
        fmt_pct(avg_alive),
        delta="No churn",
    )
with c4:
    pct_repeaters = (df_value["frequency"] > 0).mean() * 100
    st.metric(
        "Recurrentes (≥ 2 pedidos)",
        fmt_pct(pct_repeaters),
    )


# ---------------------------------------------------------------------------
# Evolución mensual: área de ingresos y margen
# ---------------------------------------------------------------------------
section_header(
    "Evolución mensual",
    "Ingresos y margen por mes",
)

fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True,
    vertical_spacing=0.10,
    subplot_titles=("Ingresos mensuales", "Margen bruto mensual"),
    row_heights=[0.55, 0.45],
)

fig.add_trace(
    go.Scatter(
        x=df_month["year_month"],
        y=df_month["revenue"],
        mode="lines",
        name="Ingresos",
        line=dict(color=COLORS["primary"], width=1.6),
        fill="tozeroy",
        fillcolor="rgba(139, 111, 71, 0.18)",
        hovertemplate="<b>%{x}</b><br>Ingresos: %{y:,.0f} €<extra></extra>",
    ),
    row=1, col=1,
)
fig.add_trace(
    go.Scatter(
        x=df_month["year_month"],
        y=df_month["margin"],
        mode="lines",
        name="Margen",
        line=dict(color=COLORS["success"], width=1.6),
        fill="tozeroy",
        fillcolor="rgba(107, 142, 90, 0.16)",
        hovertemplate="<b>%{x}</b><br>Margen: %{y:,.0f} €<extra></extra>",
    ),
    row=2, col=1,
)
fig.update_yaxes(title_text="€", row=1, col=1)
fig.update_yaxes(title_text="€", row=2, col=1)
fig.update_xaxes(title_text="Mes", row=2, col=1)
fig.update_annotations(font=dict(family="Cormorant Garamond, Georgia, serif", size=14))

fig = apply_theme(fig, show_legend=False, height=480)
st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Distribución CLTV + Curva Pareto
# ---------------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    section_header("Distribución del CLTV proyectado · 12m")

    # Limitar el upper bound al p95 para que el histograma sea legible
    upper = float(df_value["cltv_predicted_12m"].quantile(0.95))
    clv_clipped = df_value["cltv_predicted_12m"].clip(upper=upper)

    fig_h = go.Figure()
    fig_h.add_trace(
        go.Histogram(
            x=clv_clipped,
            name="Distribución CLTV",
            nbinsx=40,
            marker=dict(
                color=COLORS["primary"],
                line=dict(color=COLORS["bg_card"], width=0.5),
            ),
            opacity=0.85,
            showlegend=False,
            hovertemplate="CLTV: %{x:,.0f} €<br>Clientes: %{y}<extra></extra>",
        )
    )

    median_v = float(df_value["cltv_predicted_12m"].median())
    mean_v   = float(df_value["cltv_predicted_12m"].mean())
    fig_h.add_vline(
        x=median_v, line_dash="dash", line_color=COLORS["accent"], line_width=1,
        annotation_text=f"Mediana · {fmt_eur(median_v)}",
        annotation_position="top right",
        annotation_font_color=COLORS["accent"],
        annotation_font_size=10,
    )
    fig_h.add_vline(
        x=mean_v, line_dash="dot", line_color=COLORS["success"], line_width=1,
        annotation_text=f"Media · {fmt_eur(mean_v)}",
        annotation_position="bottom right",
        annotation_font_color=COLORS["success"],
        annotation_font_size=10,
    )
    fig_h = apply_theme(fig_h, show_legend=False, height=380)
    fig_h.update_layout(
        xaxis_title=f"CLTV proyectado 12m (€) · capped a P95",
        yaxis_title="Nº clientes",
        bargap=0.05,
    )
    st.plotly_chart(fig_h, use_container_width=True)

with col2:
    section_header("Curva de Pareto del CLTV")

    df_sorted = df_value.sort_values("cltv_predicted_12m", ascending=False).reset_index(drop=True)
    df_sorted["cum_pct_customers"] = (df_sorted.index + 1) / len(df_sorted) * 100
    cltv_sum = float(df_sorted["cltv_predicted_12m"].sum()) or 1
    df_sorted["cum_pct_cltv"] = df_sorted["cltv_predicted_12m"].cumsum() / cltv_sum * 100

    fig_p = go.Figure()
    fig_p.add_trace(
        go.Scatter(
            x=df_sorted["cum_pct_customers"],
            y=df_sorted["cum_pct_cltv"],
            mode="lines",
            name="Curva Pareto",
            line=dict(color=COLORS["accent"], width=2),
            fill="tozeroy",
            fillcolor="rgba(92, 74, 47, 0.12)",
            showlegend=False,
            hovertemplate=(
                "Top %{x:.1f} % clientes<br>%{y:.1f} % CLTV<extra></extra>"
            ),
        )
    )
    fig_p.add_vline(
        x=20, line_dash="dash", line_color=COLORS["warning"], line_width=1,
        annotation_text="Top 20 %", annotation_position="top",
        annotation_font_color=COLORS["warning"], annotation_font_size=10,
    )
    fig_p.add_hline(
        y=80, line_dash="dot", line_color=COLORS["text_dim"], line_width=1,
        annotation_text="80 % del CLTV",
        annotation_position="bottom right",
        annotation_font_color=COLORS["text_dim"], annotation_font_size=10,
    )
    fig_p = apply_theme(fig_p, show_legend=False, height=380)
    fig_p.update_layout(
        xaxis_title="% acumulado de clientes (ordenados por CLTV)",
        yaxis_title="% CLTV acumulado",
    )
    st.plotly_chart(fig_p, use_container_width=True)


# ---------------------------------------------------------------------------
# Tabla resumen anual
# ---------------------------------------------------------------------------
section_header(
    "Resumen anual",
    "Agregado por año desde fact_sales",
)

df_month_y = df_month.copy()
df_month_y["year"] = df_month_y["year_month"].astype(str).str[:4]
df_year = (
    df_month_y.groupby("year")
    .agg(n_orders=("n_orders", "sum"),
         revenue=("revenue", "sum"),
         margin=("margin", "sum"))
    .reset_index()
)
df_year["margin_pct"] = (df_year["margin"] / df_year["revenue"] * 100).round(2)

display = df_year.copy()
display["revenue"]    = display["revenue"].apply(fmt_eur)
display["margin"]     = display["margin"].apply(fmt_eur)
display["margin_pct"] = display["margin_pct"].apply(lambda v: f"{v:.2f} %".replace(".", ","))
display["n_orders"]   = display["n_orders"].apply(fmt_int)
display.columns = ["Año", "Pedidos", "Ingresos", "Margen", "Margen %"]

st.dataframe(display, use_container_width=True, hide_index=True)
