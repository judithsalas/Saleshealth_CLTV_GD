"""
Página 3 — Customer Detail.

Ficha completa por cliente individual: KPIs personales, histórico de
compras y posición relativa frente al resto de la base.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.theme import (
    COLORS,
    CLUSTER_COLORS,
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
    load_customer_value,
    load_customer_orders,
)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Customer Detail", layout="wide")
inject_css()
render_sidebar()

page_header(
    "Customer Detail",
    "Ficha individual del cliente · CLTV, histórico de compras y comparativa",
)


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
df = load_customer_value()


# ---------------------------------------------------------------------------
# Buscador de cliente
# ---------------------------------------------------------------------------
st.markdown(
    f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
    f'font-size:1.05rem;color:{COLORS["text"]};margin-bottom:8px;">'
    'Selección de cliente</div>',
    unsafe_allow_html=True,
)

# Construimos lista display
df = df.copy()
df["display"] = (
    df["customer_id"].astype(str) + " · " + df["full_name"].fillna("(sin nombre)")
)

mode_col, sel_col = st.columns([1, 3])
with mode_col:
    mode = st.radio(
        "Modo",
        options=["Top CLTV", "Buscar por nombre o ID"],
        label_visibility="collapsed",
    )

with sel_col:
    if mode == "Top CLTV":
        opts = df.head(50)["display"].tolist()
    else:
        opts = df["display"].tolist()
    selected = st.selectbox(
        "Cliente", opts, label_visibility="collapsed",
        placeholder="Escribe un ID o nombre…",
    )

if not selected:
    st.stop()

customer_id = int(selected.split(" · ")[0])
cliente = df[df["customer_id"] == customer_id].iloc[0]


# ---------------------------------------------------------------------------
# Ficha del cliente
# ---------------------------------------------------------------------------
cluster_name = str(cliente.get("cluster_name") or "—")
cluster_col  = CLUSTER_COLORS.get(cluster_name, COLORS["secondary"])

st.markdown(
    f'<div style="background:{COLORS["bg_card"]};border-radius:10px;'
    f'padding:24px 30px;margin:18px 0 28px 0;'
    f'border-left:2px solid {cluster_col};">'

    '<div style="display:flex;justify-content:space-between;align-items:flex-start;'
    'flex-wrap:wrap;gap:12px;">'

    '<div>'
    f'<div style="color:{COLORS["text_dim"]};font-size:0.72rem;'
    'letter-spacing:0.12em;text-transform:uppercase;'
    'font-family:\'Cormorant Garamond\',Georgia,serif;font-weight:500;">'
    f'Cliente nº {cliente["customer_id"]}</div>'

    f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
    f'font-size:1.85rem;color:{COLORS["text"]};line-height:1.1;margin-top:4px;">'
    f'{cliente.get("full_name") or "(sin nombre)"}</div>'

    f'<div style="color:{COLORS["text_dim"]};font-size:0.88rem;margin-top:10px;">'
    f'Cliente desde · {cliente.get("first_purchase", "—")}'
    '</div></div>'

    '<div style="display:flex;flex-direction:column;gap:8px;align-items:flex-end;">'
    f'<span style="font-size:0.78rem;background:{COLORS["bg"]};'
    f'color:{cluster_col};padding:5px 14px;border-radius:14px;'
    f'border:0.5px solid {cluster_col};font-weight:500;">{cluster_name}</span>'
    '</div>'

    '</div></div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# KPIs del cliente
# ---------------------------------------------------------------------------
section_header("Métricas del cliente")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("CLTV histórico", fmt_eur(float(cliente.get("cltv_historic", 0)), 2))
with c2:
    st.metric("CLTV proyectado · 12m", fmt_eur(float(cliente.get("cltv_predicted_12m", 0)), 2))
with c3:
    st.metric(
        "Pedidos",
        fmt_int(int(cliente.get("num_orders", 0))),
        delta=f"{int(cliente.get('num_units', 0) or 0)} unidades",
    )
with c4:
    st.metric("Ticket medio", fmt_eur(float(cliente.get("avg_order_value", 0)), 2))

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(
        "Última compra",
        f"{int(cliente.get('recency_days', 0))} días",
    )
with c2:
    st.metric(
        "Antigüedad",
        f"{int(cliente.get('customer_age_days', 0))} días",
    )
with c3:
    alive = float(cliente.get("alive_probability", 0)) * 100
    st.metric(
        "Prob. alive",
        fmt_pct(alive),
        delta="(no churn)",
    )
with c4:
    exp = float(cliente.get("expected_purchases_12m", 0))
    st.metric(
        "Compras esperadas · 12m",
        f"{exp:.2f}".replace(".", ","),
        delta="BG/NBD",
    )


# ---------------------------------------------------------------------------
# Histórico de pedidos
# ---------------------------------------------------------------------------
section_header(
    "Histórico de pedidos",
    "Pedidos del cliente ordenados por fecha · más recientes primero",
)

orders = load_customer_orders(int(cliente["customer_key"]))

if len(orders) == 0:
    st.info("Este cliente no tiene pedidos registrados.")
else:
    col1, col2 = st.columns([2, 1])

    with col1:
        # Timeline scatter
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=orders["date"],
            y=orders["amount"],
            mode="markers+lines",
            name="Pedidos",
            line=dict(color=COLORS["secondary"], width=1, dash="dot"),
            marker=dict(
                size=orders["units"] * 3.5 + 8,
                color=COLORS["primary"],
                opacity=0.75,
                line=dict(width=0.4, color=COLORS["bg_card"]),
            ),
            showlegend=False,
            customdata=orders[["sale_id", "units", "n_lines"]].values,
            hovertemplate=(
                "<b>Venta nº %{customdata[0]}</b><br>"
                "Fecha: %{x|%Y-%m-%d}<br>"
                "Importe: %{y:,.2f} €<br>"
                "Unidades: %{customdata[1]}<br>"
                "Líneas: %{customdata[2]}<extra></extra>"
            ),
        ))
        fig = apply_theme(fig, show_legend=False, height=360)
        fig.update_layout(xaxis_title="Fecha", yaxis_title="Importe (€)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        n         = len(orders)
        total     = float(orders["amount"].sum())
        ticket    = float(orders["amount"].mean())
        n_returns = int(orders["has_return"].sum())

        st.markdown(
            f'<div style="background:{COLORS["bg_card"]};border-radius:8px;'
            'padding:20px 22px;margin-top:8px;">'

            f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
            f'font-size:1rem;color:{COLORS["text"]};margin-bottom:14px;">'
            'Estadísticas del histórico</div>'

            '<div style="display:flex;flex-direction:column;gap:14px;">'
            + "".join([
                f'<div>'
                f'<div style="color:{COLORS["text_dim"]};font-size:0.7rem;'
                f'text-transform:uppercase;letter-spacing:0.08em;">{label}</div>'
                f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
                f'font-size:1.4rem;color:{COLORS["text"]};">{value}</div>'
                f'</div>'
                for label, value in [
                    ("Total pedidos",          fmt_int(n)),
                    ("Total gastado",          fmt_eur(total, 2)),
                    ("Ticket medio",           fmt_eur(ticket, 2)),
                    ("Pedidos con devolución", fmt_int(n_returns)),
                ]
            ])
            + '</div></div>',
            unsafe_allow_html=True,
        )

    # Tabla detalle (collapsable)
    with st.expander(f"Ver detalle de los {n} pedidos", expanded=False):
        ord_disp = orders.copy()
        ord_disp["date"]    = pd.to_datetime(ord_disp["date"]).dt.strftime("%Y-%m-%d")
        ord_disp["amount"]  = ord_disp["amount"].apply(lambda v: fmt_eur(v, 2))
        ord_disp["margin"]  = ord_disp["margin"].apply(lambda v: fmt_eur(v, 2))
        ord_disp["has_return"] = ord_disp["has_return"].map({True: "Sí", False: "—"})
        ord_disp.columns = ["Sale ID", "Fecha", "Líneas", "Unidades", "Importe", "Margen", "Devolución"]
        st.dataframe(ord_disp, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Posición relativa (percentiles)
# ---------------------------------------------------------------------------
section_header(
    "Posición relativa frente al resto",
    f"Percentil del cliente vs los {fmt_int(len(df))} clientes de la base",
)

metrics_cmp = {
    "CLTV histórico":         "cltv_historic",
    "CLTV proyectado 12m":    "cltv_predicted_12m",
    "Frecuencia (pedidos)":   "num_orders",
    "Ticket medio":           "avg_order_value",
    "Volumen (unidades)":     "num_units",
}

percentiles = {}
for label, col in metrics_cmp.items():
    val = cliente.get(col)
    if pd.notna(val) and df[col].std() > 0:
        pct = float((df[col] < val).sum()) / len(df) * 100
        percentiles[label] = pct

if percentiles:
    labels = list(percentiles.keys())
    pcts = list(percentiles.values())
    bar_colors = [
        COLORS["danger"] if p < 33
        else COLORS["warning"] if p < 66
        else COLORS["success"]
        for p in pcts
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Percentil",
        y=labels, x=pcts,
        orientation="h",
        marker_color=bar_colors,
        marker_line_width=0,
        text=[f"P{p:.0f}" for p in pcts],
        textposition="outside",
        textfont=dict(color=COLORS["text"], size=11),
        hovertemplate="<b>%{y}</b><br>Percentil %{x:.1f}<extra></extra>",
        showlegend=False,
    ))
    fig.add_vline(
        x=50, line_dash="dot", line_color=COLORS["text_dim"], line_width=1,
        annotation_text="Mediana", annotation_position="top",
        annotation_font_color=COLORS["text_dim"], annotation_font_size=10,
    )
    fig = apply_theme(fig, show_legend=False, height=340)
    fig.update_layout(
        xaxis_title="Percentil (0 = peor, 100 = mejor de la base)",
        yaxis_title="",
        xaxis=dict(range=[0, 110]),
        yaxis=dict(autorange="reversed"),
        margin=dict(t=40, b=60, l=160, r=40),
    )
    st.plotly_chart(fig, use_container_width=True)
