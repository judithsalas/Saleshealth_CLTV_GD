"""
Página 4 — Stores Map.

Mapa interactivo con las 20 tiendas. Cada marcador:
  · Tamaño   → revenue de la tienda
  · Color    → margen porcentual
  · Hover    → KPIs detallados (revenue, clientes, ticket medio, devoluciones)

Bajo el mapa:
  · 4 KPIs globales de la red
  · Ranking de tiendas con barras comparativas
  · Hallazgo automático (concentración / mejor margen)

Aprovecha lat/long de dim_location y agrega métricas de fact_sales.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.theme import (
    COLORS,
    apply_theme,
    inject_css,
    render_sidebar,
    page_header,
    section_header,
    kpi_card,
    finding_box,
    fmt_eur,
    fmt_eur_compact,
    fmt_int,
    fmt_pct,
)
from app.data_access import load_stores_metrics


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Stores Map", layout="wide")
inject_css()
render_sidebar()

page_header(
    "Stores · Geographic View",
    "Mapa interactivo de las tiendas · tamaño del marcador proporcional al "
    "revenue · color según margen porcentual · hover para detalle de la tienda",
)


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
try:
    df = load_stores_metrics()
except Exception as exc:                                  # noqa: BLE001
    st.error(f"No se han podido cargar los datos: {exc}")
    st.info("¿Has ejecutado `python run.py --all`?")
    st.stop()

if len(df) == 0:
    st.warning(
        "La dimensión `dwh.dim_location` no tiene tiendas con coordenadas "
        "(latitude/longitude). El mapa requiere esos campos rellenados."
    )
    st.stop()


# ---------------------------------------------------------------------------
# KPIs globales de la red
# ---------------------------------------------------------------------------
section_header("Resumen de la red", f"{len(df)} tiendas con datos geográficos")

n_stores       = len(df)
total_revenue  = float(df["revenue"].sum())
total_margin   = float(df["margin"].sum())
margin_pct     = (total_margin / total_revenue * 100) if total_revenue else 0
total_orders   = int(df["n_orders"].sum())
avg_ticket_net = total_revenue / total_orders if total_orders else 0

c1, c2, c3, c4 = st.columns(4, gap="medium")
with c1:
    kpi_card("Tiendas", fmt_int(n_stores), delta="Red completa")
with c2:
    kpi_card("Revenue red", fmt_eur_compact(total_revenue),
             delta=f"{fmt_eur(total_revenue)}")
with c3:
    kpi_card("Margen %", f"{margin_pct:.1f} %".replace(".", ","),
             delta=fmt_eur_compact(total_margin))
with c4:
    kpi_card("Ticket medio red", fmt_eur(avg_ticket_net, 2),
             delta=f"{fmt_int(total_orders)} pedidos")


# ---------------------------------------------------------------------------
# Mapa interactivo
# ---------------------------------------------------------------------------
section_header(
    "Geolocalización",
    "Cada punto es una tienda · tamaño = revenue · color = margen porcentual",
)

# Centro y zoom automáticos sobre las tiendas
center_lat = float(df["latitude"].mean())
center_lon = float(df["longitude"].mean())

# Tamaño del marcador escalado al revenue (mín 12, máx 38)
rev_max = float(df["revenue"].max()) or 1.0
df["marker_size"] = 12 + (df["revenue"] / rev_max) * 26

# Hover text rico (HTML) ---------------------------------------------------
def _hover_text(row: pd.Series) -> str:
    return (
        f"<b style='font-size:13px;'>{row['store_name']}</b><br>"
        f"<span style='color:#7A6F5F;'>{row['address'] or ''}</span><br>"
        f"<span style='color:#7A6F5F;'>{row['district'] or ''} · "
        f"{row['postal_code']}</span>"
        f"<br><br>"
        f"<b>Revenue</b>      {fmt_eur(row['revenue'])}<br>"
        f"<b>Margen</b>       {fmt_eur(row['margin'])} ({row['margin_pct']:.1f} %)<br>"
        f"<b>Pedidos</b>      {fmt_int(int(row['n_orders']))}<br>"
        f"<b>Clientes</b>     {fmt_int(int(row['n_customers']))}<br>"
        f"<b>Ticket medio</b> {fmt_eur(row['avg_ticket'], 2)}<br>"
        f"<b>Devolución</b>   {row['return_rate_pct']:.1f} %"
    )


df["hover"] = df.apply(_hover_text, axis=1)


# Plotly: scatter_mapbox usando el estilo "carto-positron" (claro, neutro,
# encaja con la paleta nude). No requiere API key.
fig = go.Figure()
fig.add_trace(
    go.Scattermapbox(
        lat=df["latitude"],
        lon=df["longitude"],
        mode="markers",
        marker=dict(
            size=df["marker_size"],
            color=df["margin_pct"],
            colorscale=[
                [0.00, COLORS["danger"]],
                [0.35, COLORS["warning"]],
                [0.65, COLORS["secondary"]],
                [1.00, COLORS["success"]],
            ],
            cmin=float(df["margin_pct"].min()),
            cmax=float(df["margin_pct"].max()),
            opacity=0.88,
            colorbar=dict(
                title=dict(
                    text="% margen",
                    font=dict(size=11, color=COLORS["text_dim"]),
                ),
                tickfont=dict(size=10, color=COLORS["text_dim"]),
                thickness=14,
                len=0.6,
                outlinewidth=0,
                ticksuffix=" %",
            ),
        ),
        text=df["hover"],
        hovertemplate="%{text}<extra></extra>",
        name="Tiendas",
        showlegend=False,
    )
)

fig.update_layout(
    mapbox=dict(
        style="carto-positron",
        center=dict(lat=center_lat, lon=center_lon),
        zoom=10.5,
    ),
    paper_bgcolor=COLORS["bg"],
    plot_bgcolor=COLORS["bg"],
    margin=dict(t=0, b=0, l=0, r=0),
    height=560,
    hoverlabel=dict(
        bgcolor=COLORS["bg_card"],
        bordercolor=COLORS["text_soft"],
        font=dict(
            color=COLORS["text"],
            family="Inter, sans-serif",
            size=12,
        ),
        align="left",
    ),
)

st.plotly_chart(fig, use_container_width=True)

# Nota interpretativa
st.markdown(
    f'<div style="font-size:0.78rem;color:{COLORS["text_dim"]};'
    'margin-top:6px;line-height:1.5;">'
    f'Los marcadores más grandes corresponden a tiendas con mayor facturación. '
    f'El color refleja la rentabilidad: <span style="color:{COLORS["success"]};">'
    'verde oliva</span> indica margen alto, '
    f'<span style="color:{COLORS["danger"]};">terracota</span> indica margen bajo. '
    'Pasa el ratón sobre cualquier tienda para ver KPIs detallados.'
    '</div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Ranking de tiendas (con microbarras)
# ---------------------------------------------------------------------------
section_header(
    "Ranking de tiendas",
    "Ordenadas por revenue total · barra proporcional a la tienda líder",
)

# Cabecera de la tabla
st.markdown(
    '<div style="display:grid;grid-template-columns:32px 1fr 1fr 130px 110px 90px;'
    f'gap:18px;padding-bottom:10px;border-bottom:0.5px solid {COLORS["border"]};'
    'margin-bottom:4px;font-size:0.66rem;letter-spacing:0.10em;'
    f'text-transform:uppercase;color:{COLORS["text_dim"]};font-weight:600;">'
    '<div></div>'
    '<div>Tienda</div>'
    '<div>Revenue (barra)</div>'
    '<div style="text-align:right;">Revenue</div>'
    '<div style="text-align:right;">Margen</div>'
    '<div style="text-align:right;">Pedidos</div>'
    '</div>',
    unsafe_allow_html=True,
)

ranked = df.sort_values("revenue", ascending=False).reset_index(drop=True)
top_revenue = float(ranked.iloc[0]["revenue"]) if len(ranked) else 1.0

rows_html = []
for idx, r in ranked.iterrows():
    rank = idx + 1
    bar_pct = (r["revenue"] / top_revenue * 100) if top_revenue else 0

    # Color del margen para diferenciar tiendas top de las bajas
    if r["margin_pct"] >= 35:
        margin_color = COLORS["success"]
    elif r["margin_pct"] >= 25:
        margin_color = COLORS["warning"]
    else:
        margin_color = COLORS["danger"]

    rows_html.append(
        '<div style="display:grid;'
        'grid-template-columns:32px 1fr 1fr 130px 110px 90px;'
        f'align-items:center;gap:18px;padding:13px 0;'
        f'border-bottom:0.5px solid {COLORS["border"]};">'

        # Rank
        f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
        f'font-size:0.9rem;color:{COLORS["primary"]};">{rank:02d}</div>'

        # Tienda
        '<div>'
        f'<div style="font-size:0.94rem;color:{COLORS["text"]};">{r["store_name"]}</div>'
        f'<div style="font-size:0.74rem;color:{COLORS["text_dim"]};margin-top:2px;">'
        f'{r["district"] or "—"} · {r["postal_code"]}</div>'
        '</div>'

        # Microbarra
        f'<div style="background:{COLORS["bg_card"]};height:6px;border-radius:3px;'
        'overflow:hidden;">'
        f'<div style="background:{COLORS["primary"]};height:100%;width:{bar_pct:.1f}%;"></div>'
        '</div>'

        # Revenue
        f'<div style="font-family:Inter;font-variant-numeric:tabular-nums;'
        f'font-weight:500;font-size:1rem;color:{COLORS["text"]};'
        'text-align:right;letter-spacing:-0.01em;white-space:nowrap;">'
        f'{fmt_eur(float(r["revenue"]))}</div>'

        # Margen
        f'<div style="font-family:Inter;font-variant-numeric:tabular-nums;'
        f'font-size:0.92rem;color:{margin_color};text-align:right;'
        'font-weight:500;">'
        f'{r["margin_pct"]:.1f} %</div>'

        # Pedidos
        f'<div style="font-family:Inter;font-variant-numeric:tabular-nums;'
        f'font-size:0.88rem;color:{COLORS["text_dim"]};text-align:right;">'
        f'{fmt_int(int(r["n_orders"]))}</div>'

        '</div>'
    )

st.markdown("".join(rows_html), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Hallazgo automático
# ---------------------------------------------------------------------------
top_stores = ranked.head(3)
top3_revenue = float(top_stores["revenue"].sum())
top3_pct     = (top3_revenue / total_revenue * 100) if total_revenue else 0

best_margin    = ranked.sort_values("margin_pct", ascending=False).iloc[0]
worst_margin   = ranked.sort_values("margin_pct", ascending=True).iloc[0]
margin_gap     = float(best_margin["margin_pct"] - worst_margin["margin_pct"])

headline = (
    f"Las 3 tiendas con más facturación generan {top3_pct:.0f} % "
    f"del revenue de la red."
)

body = (
    f"<b>{', '.join(top_stores['store_name'].head(3).tolist())}</b> "
    f"concentran <b>{fmt_eur(top3_revenue)}</b> de los "
    f"<b>{fmt_eur(total_revenue)}</b> totales. "
    f"La diferencia de rentabilidad entre la tienda más eficiente "
    f"(<b>{best_margin['store_name']}</b>, {best_margin['margin_pct']:.1f} %) "
    f"y la menos eficiente "
    f"(<b>{worst_margin['store_name']}</b>, {worst_margin['margin_pct']:.1f} %) "
    f"es de <b>{margin_gap:.1f} puntos porcentuales</b>, "
    "lo que sugiere oportunidades de homogenización de mix de producto, "
    "precio o gestión de descuentos."
)

finding_box(headline=headline, body=body)


# ---------------------------------------------------------------------------
# Pie
# ---------------------------------------------------------------------------
st.markdown(
    f'<div style="margin-top:48px;padding-top:18px;'
    f'border-top:0.5px solid {COLORS["border"]};display:flex;'
    f'justify-content:space-between;font-size:0.78rem;color:{COLORS["text_dim"]};">'
    '<div>Datos: <code>dwh.dim_location</code> · <code>dwh.fact_sales</code></div>'
    '<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
    'letter-spacing:0.05em;">UAX · Gestión de Datos · 2025/26</div>'
    '</div>',
    unsafe_allow_html=True,
)
