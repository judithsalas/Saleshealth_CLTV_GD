"""
Saleshealth Analytics — Página principal.

Snapshot ejecutivo: KPIs alineados (4 columnas iguales), distribución
por cluster, top clientes con microbarra, hallazgo editorial.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.theme import (
    COLORS,
    CLUSTER_COLORS,
    inject_css,
    page_header,
    section_header,
    kpi_card,
    finding_box,
    fmt_eur,
    fmt_eur_compact,
    fmt_int,
    fmt_pct,
)
from app.data_access import (
    load_global_kpis,
    load_customer_value,
    load_cluster_summary,
)


st.set_page_config(
    page_title="Saleshealth · Customer Insights",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
try:
    kpis      = load_global_kpis()
    df_value  = load_customer_value()
    df_clust  = load_cluster_summary()
except Exception as exc:                                  # noqa: BLE001
    st.error(f"No se han podido cargar los datos del DWH: {exc}")
    st.info("¿Has ejecutado `python run.py --all` antes de abrir el dashboard?")
    st.stop()


n_total      = len(df_value)
n_active     = int((df_value["alive_probability"] > 0.5).sum())
cltv_total   = float(df_value["cltv_historic"].sum())
cltv_pred    = float(df_value["cltv_predicted_12m"].sum())

champion_mask  = df_value["cluster_name"] == "Champions"
cltv_champ     = float(df_value.loc[champion_mask, "cltv_predicted_12m"].sum())
n_champions    = int(champion_mask.sum())
pct_champ_cltv = (cltv_champ / cltv_pred * 100) if cltv_pred else 0
pct_champ_base = (n_champions / n_total * 100) if n_total else 0


# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------
page_header(
    "Customer Insights",
    "Análisis del valor del cliente · CLTV probabilístico (BG/NBD + Gamma-Gamma) "
    "y segmentación K-Means con triple validación de K · "
    f"{fmt_int(n_total)} clientes · {fmt_int(int(kpis['total_orders']))} pedidos",
)


# ---------------------------------------------------------------------------
# Resumen ejecutivo: 4 KPIs IGUALES, alineadas
# ---------------------------------------------------------------------------
section_header("Resumen ejecutivo", "Cifras clave del periodo analizado")

# 4 columnas iguales para alineación perfecta
c1, c2, c3, c4 = st.columns(4, gap="medium")

with c1:
    kpi_card(
        "Facturación neta",
        fmt_eur_compact(kpis["total_revenue"]),
        delta=f"{fmt_eur(kpis['total_revenue'])}",
    )
with c2:
    kpi_card(
        "Clientes",
        fmt_int(n_total),
        delta=f"{fmt_int(n_active)} activos",
    )
with c3:
    kpi_card(
        "CLTV histórico",
        fmt_eur_compact(cltv_total),
        delta=f"Margen {kpis['margin_pct']:.1f} %",
    )
with c4:
    kpi_card(
        "CLTV proyectado · 12 m",
        fmt_eur_compact(cltv_pred),
        delta="BG/NBD + Γ-Γ",
    )


# ---------------------------------------------------------------------------
# Distribución por cluster
# ---------------------------------------------------------------------------
section_header(
    "Distribución por cluster",
    "Segmentación K-Means · proporción de la base y CLTV proyectado a 12 meses",
)

# Cabecera
st.markdown(
    '<div style="display:grid;grid-template-columns:200px 1fr 90px 130px;'
    f'gap:18px;padding-bottom:10px;border-bottom:0.5px solid {COLORS["border"]};'
    'margin-bottom:4px;font-size:0.66rem;letter-spacing:0.10em;'
    f'text-transform:uppercase;color:{COLORS["text_dim"]};font-weight:600;">'
    '<div>Cluster</div>'
    '<div style="text-align:left;padding-left:6px;">% de la base</div>'
    '<div style="text-align:right;">N</div>'
    '<div style="text-align:right;">CLTV 12 m</div>'
    '</div>',
    unsafe_allow_html=True,
)

rows_html = []
for _, row in df_clust.iterrows():
    seg = row["cluster_name"]
    n   = int(row["n_customers"])
    c   = float(row["total_cltv_12m"])
    pct_base = n / n_total * 100 if n_total else 0
    bar_color = CLUSTER_COLORS.get(seg, COLORS["secondary"])
    bar_width_pct = max(pct_base, 0.5)

    rows_html.append(
        '<div style="display:grid;grid-template-columns:200px 1fr 90px 130px;'
        f'align-items:center;gap:18px;padding:14px 0;'
        f'border-bottom:0.5px solid {COLORS["border"]};">'

        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<span style="width:6px;height:6px;border-radius:50%;'
        f'background:{bar_color};display:inline-block;flex-shrink:0;"></span>'
        f'<span style="font-size:0.94rem;color:{COLORS["text"]};">{seg}</span>'
        '</div>'

        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<div style="background:{COLORS["bg_card"]};height:6px;border-radius:3px;'
        f'overflow:hidden;flex-grow:1;min-width:60px;">'
        f'<div style="background:{bar_color};height:100%;width:{bar_width_pct:.1f}%;"></div>'
        '</div>'
        f'<span style="font-family:Inter;font-variant-numeric:tabular-nums;'
        f'font-size:0.82rem;color:{COLORS["text_dim"]};min-width:48px;'
        'text-align:right;flex-shrink:0;">'
        f'{pct_base:.1f} %</span>'
        '</div>'

        f'<div style="font-family:Inter;font-variant-numeric:tabular-nums;'
        f'font-size:0.92rem;color:{COLORS["text"]};text-align:right;">'
        f'{fmt_int(n)}</div>'

        f'<div style="font-family:Inter;font-variant-numeric:tabular-nums;'
        f'font-weight:500;font-size:1rem;color:{COLORS["text"]};'
        'text-align:right;letter-spacing:-0.01em;white-space:nowrap;">'
        f'{fmt_eur(c)}</div>'

        '</div>'
    )

st.markdown("".join(rows_html), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Top clientes con microbarra
# ---------------------------------------------------------------------------
section_header(
    "Top clientes por CLTV proyectado",
    "Cinco primeros · proyección a 12 meses con BG/NBD + Gamma-Gamma",
)

top = df_value.head(5).reset_index(drop=True)
max_cltv = float(top["cltv_predicted_12m"].max()) if len(top) else 1.0

rows_top = []
for idx, cli in top.iterrows():
    rank      = idx + 1
    name      = str(cli.get("full_name") or f"Cliente #{cli['customer_id']}")
    n_orders  = int(cli["num_orders"]) if cli["num_orders"] else 0
    cltv      = float(cli["cltv_predicted_12m"])
    cluster   = str(cli.get("cluster_name") or "—")
    clu_color = CLUSTER_COLORS.get(cluster, COLORS["secondary"])
    alive_pct = float(cli["alive_probability"]) * 100
    bar_pct   = (cltv / max_cltv * 100) if max_cltv else 0

    rows_top.append(
        '<div style="display:grid;'
        'grid-template-columns:36px 1fr 160px 110px 120px;'
        f'align-items:center;gap:18px;padding:16px 0;'
        f'border-bottom:0.5px solid {COLORS["border"]};">'

        f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
        f'font-size:0.95rem;color:{COLORS["primary"]};">{rank:02d}</div>'

        '<div>'
        f'<div style="font-size:0.94rem;color:{COLORS["text"]};">{name}</div>'
        f'<div style="font-size:0.76rem;color:{COLORS["text_dim"]};margin-top:3px;">'
        f'{n_orders} pedidos · alive {alive_pct:.0f} %</div>'
        '</div>'

        f'<div style="background:{COLORS["bg_card"]};height:5px;border-radius:3px;'
        'overflow:hidden;">'
        f'<div style="background:{clu_color};height:100%;width:{bar_pct:.1f}%;"></div>'
        '</div>'

        f'<div style="font-family:Inter;font-variant-numeric:tabular-nums;'
        f'font-weight:500;font-size:1.05rem;color:{COLORS["text"]};'
        'text-align:right;letter-spacing:-0.01em;white-space:nowrap;">'
        f'{fmt_eur(cltv)}</div>'

        '<div style="text-align:right;">'
        f'<span style="font-size:0.72rem;background:{COLORS["bg_card"]};'
        f'color:{clu_color};padding:5px 11px;border-radius:12px;'
        f'border:0.5px solid {clu_color};white-space:nowrap;">{cluster}</span></div>'

        '</div>'
    )

st.markdown("".join(rows_top), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Hallazgo
# ---------------------------------------------------------------------------
finding_box(
    headline=f"{n_champions} clientes generan {pct_champ_cltv:.0f} de cada 100 € futuros.",
    body=(
        f"Los <b>{n_champions}</b> clientes ({pct_champ_base:.1f} % de la base) "
        f"clasificados como <b>Champions</b> concentran el {pct_champ_cltv:.1f} % "
        f"del CLTV proyectado a 12 meses, frente al {100 - pct_champ_cltv:.1f} % "
        f"aportado por los {fmt_int(n_total - n_champions)} clientes restantes. "
        "La selección de K se valida con tres métricas independientes "
        "(Elbow, Silhouette y Davies-Bouldin), garantizando que la "
        "segmentación no es arbitraria."
    ),
)


# ---------------------------------------------------------------------------
# Pie
# ---------------------------------------------------------------------------
st.markdown(
    f'<div style="margin-top:48px;padding-top:18px;'
    f'border-top:0.5px solid {COLORS["border"]};display:flex;'
    f'justify-content:space-between;font-size:0.78rem;color:{COLORS["text_dim"]};">'
    '<div>Datos: <code>marts.customer_lifetime_value</code> y '
    '<code>marts.customer_segments</code></div>'
    '<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
    'letter-spacing:0.05em;">UAX · Gestión de Datos · 2025/26</div>'
    '</div>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sidebar (común a todas las páginas)
# ---------------------------------------------------------------------------
from app.theme import render_sidebar
render_sidebar()
