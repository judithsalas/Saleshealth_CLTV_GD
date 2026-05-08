"""
Página 2 — Segmentation.

Visualización rigurosa de la segmentación K-Means:
  · Triple validación de K (Elbow, Silhouette, Davies-Bouldin)
  · Scatter 2D de los clusters (PCA y UMAP)
  · Perfil radial de cada cluster
  · Tabla detalle
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
)
from app.data_access import (
    load_customer_value,
    load_cluster_summary,
    load_cluster_metrics,
)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Segmentation", layout="wide")
inject_css()
render_sidebar()

page_header(
    "Segmentation",
    "Clustering K-Means con validación rigurosa de K · "
    "Elbow + Silhouette + Davies-Bouldin · Visualización con PCA y UMAP",
)


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------
df_value = load_customer_value().dropna(subset=["cluster_name"])
df_clust = load_cluster_summary()
df_metrics = load_cluster_metrics()


# ---------------------------------------------------------------------------
# KPIs por cluster
# ---------------------------------------------------------------------------
section_header(
    f"Resumen del modelo · {len(df_clust)} clusters",
    f"{fmt_int(len(df_value))} clientes asignados",
)

cols = st.columns(len(df_clust))
for i, (_, row) in enumerate(df_clust.iterrows()):
    with cols[i]:
        st.metric(
            row["cluster_name"],
            fmt_int(int(row["n_customers"])),
            delta=f"CLTV 12m {fmt_eur(float(row['avg_cltv_12m']))}",
        )


# ---------------------------------------------------------------------------
# Triple validación de K
# ---------------------------------------------------------------------------
if df_metrics is not None:
    section_header(
        "Selección de K",
        "Tres métricas independientes evalúan distintos K de 2 a 10. "
        "El K óptimo se elige combinando las tres (sombreado en oro).",
    )

    optimal_k = int(df_metrics.loc[df_metrics["optimal"], "k"].iloc[0])

    col1, col2, col3 = st.columns(3)

    with col1:
        # Elbow: inercia
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_metrics["k"], y=df_metrics["inertia"],
            mode="lines+markers",
            name="Inercia",
            line=dict(color=COLORS["primary"], width=1.8),
            marker=dict(size=8, color=COLORS["primary"]),
            showlegend=False,
            hovertemplate="K=%{x}<br>Inercia: %{y:,.0f}<extra></extra>",
        ))
        fig.add_vline(x=optimal_k, line_dash="dash", line_color=COLORS["accent"],
                      annotation_text=f"K={optimal_k}",
                      annotation_position="top",
                      annotation_font_color=COLORS["accent"],
                      annotation_font_size=11)
        fig = apply_theme(fig, show_legend=False, height=300)
        fig.update_layout(
            title="Elbow · inercia (menor = mejor compactación)",
            xaxis_title="K", yaxis_title="Inercia",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Silhouette: a más alto, mejor
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_metrics["k"], y=df_metrics["silhouette"],
            mode="lines+markers",
            name="Silhouette",
            line=dict(color=COLORS["success"], width=1.8),
            marker=dict(size=8, color=COLORS["success"]),
            showlegend=False,
            hovertemplate="K=%{x}<br>Silhouette: %{y:.3f}<extra></extra>",
        ))
        fig.add_vline(x=optimal_k, line_dash="dash", line_color=COLORS["accent"],
                      annotation_text=f"K={optimal_k}",
                      annotation_position="top",
                      annotation_font_color=COLORS["accent"],
                      annotation_font_size=11)
        fig = apply_theme(fig, show_legend=False, height=300)
        fig.update_layout(
            title="Silhouette · separación (mayor = mejor)",
            xaxis_title="K", yaxis_title="Silhouette score",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col3:
        # Davies-Bouldin: a más bajo, mejor
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_metrics["k"], y=df_metrics["davies_bouldin"],
            mode="lines+markers",
            name="Davies-Bouldin",
            line=dict(color=COLORS["warning"], width=1.8),
            marker=dict(size=8, color=COLORS["warning"]),
            showlegend=False,
            hovertemplate="K=%{x}<br>Davies-Bouldin: %{y:.3f}<extra></extra>",
        ))
        fig.add_vline(x=optimal_k, line_dash="dash", line_color=COLORS["accent"],
                      annotation_text=f"K={optimal_k}",
                      annotation_position="top",
                      annotation_font_color=COLORS["accent"],
                      annotation_font_size=11)
        fig = apply_theme(fig, show_legend=False, height=300)
        fig.update_layout(
            title="Davies-Bouldin · solapamiento (menor = mejor)",
            xaxis_title="K", yaxis_title="DB index",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown(
        f'<div style="margin-top:8px;padding:14px 20px;'
        f'background:{COLORS["bg_card"]};border-radius:6px;'
        f'border-left:2px solid {COLORS["accent"]};">'
        f'<div style="font-size:0.85rem;color:{COLORS["text"]};line-height:1.6;">'
        f'<b>K óptimo seleccionado: {optimal_k}</b>. La elección combina '
        '0.5 · Silhouette + 0.3 · Davies-Bouldin + 0.2 · ganancia marginal de inercia '
        '(elbow). Esto evita decidir K por inspección visual ad hoc.'
        '</div></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Scatter 2D · PCA y UMAP
# ---------------------------------------------------------------------------
section_header(
    "Proyección 2D",
    "PCA preserva varianza global · UMAP preserva estructura local",
)

projection = st.radio(
    "Proyección",
    options=["UMAP", "PCA"],
    horizontal=True,
    label_visibility="collapsed",
)

x_col = "umap_x" if projection == "UMAP" else "pca_x"
y_col = "umap_y" if projection == "UMAP" else "pca_y"

fig = go.Figure()
for cname in df_clust["cluster_name"]:
    sub = df_value[df_value["cluster_name"] == cname]
    color = CLUSTER_COLORS.get(cname, COLORS["secondary"])
    fig.add_trace(go.Scatter(
        x=sub[x_col],
        y=sub[y_col],
        mode="markers",
        name=f"{cname} · n={len(sub)}",
        marker=dict(
            size=7,
            color=color,
            opacity=0.65,
            line=dict(width=0.4, color=COLORS["bg_card"]),
        ),
        customdata=sub[["customer_id", "full_name", "cltv_predicted_12m", "num_orders"]].values,
        hovertemplate=(
            "<b>%{customdata[1]}</b> (#%{customdata[0]})<br>"
            f"Cluster: {cname}<br>"
            "CLTV 12m: %{customdata[2]:,.0f} €<br>"
            "Pedidos: %{customdata[3]}<extra></extra>"
        ),
    ))

fig = apply_theme(fig, show_legend=True, height=520, legend_orientation="h")
fig.update_layout(
    xaxis_title=f"{projection} · componente 1",
    yaxis_title=f"{projection} · componente 2",
)
st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Tabla detalle
# ---------------------------------------------------------------------------
section_header("Detalle numérico por cluster")

display = df_clust.copy()
display.columns = [
    "ID", "Cluster", "Nº", "Pedidos μ", "Revenue μ", "Margen μ",
    "CLTV 12m μ", "Alive μ", "CLTV 12m total", "Margen total",
]
display["Revenue μ"]      = display["Revenue μ"].apply(lambda v: fmt_eur(float(v)))
display["Margen μ"]       = display["Margen μ"].apply(lambda v: fmt_eur(float(v)))
display["CLTV 12m μ"]     = display["CLTV 12m μ"].apply(lambda v: fmt_eur(float(v)))
display["CLTV 12m total"] = display["CLTV 12m total"].apply(lambda v: fmt_eur(float(v)))
display["Margen total"]   = display["Margen total"].apply(lambda v: fmt_eur(float(v)))
display["Alive μ"]        = display["Alive μ"].apply(lambda v: f"{float(v):.2f}".replace(".", ","))
display["Pedidos μ"]      = display["Pedidos μ"].apply(lambda v: f"{float(v):.1f}".replace(".", ","))
display["Nº"]             = display["Nº"].apply(fmt_int)

st.dataframe(display, use_container_width=True, hide_index=True)
