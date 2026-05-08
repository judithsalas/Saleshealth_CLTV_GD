"""
Tema visual del dashboard.

Paleta "boutique nude". Cifras en sans tabular, titulares en serif.
"""
from __future__ import annotations

from datetime import datetime

import plotly.graph_objects as go
import streamlit as st


COLORS = {
    "bg":         "#FAF7F2",
    "bg_card":    "#F2EDE4",
    "bg_subtle":  "#F7F2E9",
    "border":     "#E5DDD0",
    "text":       "#2C2419",
    "text_dim":   "#7A6F5F",
    "text_soft":  "#A89684",
    "primary":    "#8B6F47",
    "secondary":  "#A89684",
    "accent":     "#5C4A2F",
    "success":    "#6B8E5A",
    "warning":    "#B8895A",
    "danger":     "#A65D5D",
}

CLUSTER_COLORS = {
    "Champions":              "#6B8E5A",
    "Recurrentes leales":     "#8B6F47",
    "Nuevos prometedores":    "#A89684",
    "Ocasionales":            "#C9BCA9",
    "En riesgo de churn":     "#A65D5D",
}

SEQUENCE = [
    "#5C4A2F", "#8B6F47", "#A89684",
    "#B5A89A", "#C9BCA9", "#6B8E5A", "#A65D5D",
]


PLOTLY_LAYOUT: dict = {
    "template": "plotly_white",
    "paper_bgcolor": COLORS["bg"],
    "plot_bgcolor":  COLORS["bg"],
    "font": {
        "color": COLORS["text"],
        "family": "Inter, -apple-system, 'Segoe UI', Roboto, sans-serif",
        "size": 12,
    },
    # NOTA: no definir "title" aquí. Si lo definimos sin "text",
    # Plotly renderiza la palabra "undefined" arriba del gráfico.
    # Las páginas que necesiten título lo definen ellas con title=dict(text=...).
    "xaxis": {
        "gridcolor":  COLORS["border"],
        "linecolor":  COLORS["text_soft"],
        "color":      COLORS["text_dim"],
        "title": {"font": {"size": 11, "color": COLORS["text_dim"]}},
    },
    "yaxis": {
        "gridcolor":  COLORS["border"],
        "linecolor":  COLORS["text_soft"],
        "color":      COLORS["text_dim"],
        "title": {"font": {"size": 11, "color": COLORS["text_dim"]}},
    },
    "legend": {
        "bgcolor": "rgba(250, 247, 242, 0.85)",
        "bordercolor": COLORS["border"],
        "borderwidth": 0.5,
        "font": {"size": 11, "color": COLORS["text"]},
    },
    "hoverlabel": {
        "bgcolor":     COLORS["bg_card"],
        "bordercolor": COLORS["text_soft"],
        "font": {
            "color":  COLORS["text"],
            "family": "Inter, sans-serif",
            "size":   12,
        },
    },
    "margin": {"t": 50, "b": 50, "l": 60, "r": 30},
}


def apply_theme(
    fig: go.Figure,
    *,
    show_legend: bool = True,
    height: int | None = None,
    legend_orientation: str = "auto",
) -> go.Figure:
    """
    Aplica el layout base a una figura Plotly.

    Args:
        fig: figura a tunear.
        show_legend: si mostrar leyenda.
        height: alto fijo en píxeles (None = auto).
        legend_orientation: 'h' (horizontal abajo), 'v' (vertical derecha)
            o 'auto' (vertical, posición a la derecha).
    """
    fig.update_layout(**PLOTLY_LAYOUT)
    fig.update_layout(showlegend=show_legend)

    # Si la figura no tiene título de texto, asegurarnos de que es None
    # (no un dict vacío que renderiza "undefined").
    if not getattr(fig.layout.title, "text", None):
        fig.update_layout(title_text=None)

    if height is not None:
        fig.update_layout(height=height)

    # Leyenda: por defecto vertical a la derecha (mejor en desktop).
    # Si queremos horizontal abajo, lo indicamos explícitamente.
    if show_legend and legend_orientation == "h":
        fig.update_layout(
            legend=dict(
                orientation="h",
                yanchor="top", y=-0.18,
                xanchor="left", x=0,
                bgcolor="rgba(250, 247, 242, 0)",
                bordercolor=COLORS["border"],
                borderwidth=0,
                font=dict(size=11, color=COLORS["text"]),
            ),
            margin=dict(t=PLOTLY_LAYOUT["margin"]["t"],
                        b=80,    # más espacio abajo para la leyenda
                        l=PLOTLY_LAYOUT["margin"]["l"],
                        r=PLOTLY_LAYOUT["margin"]["r"]),
        )

    # autosize para que respete el ancho del contenedor en móvil
    fig.update_layout(autosize=True)
    return fig


# ---------------------------------------------------------------------------
#  CSS global
# ---------------------------------------------------------------------------
_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Cormorant+Garamond:wght@400;500;600&display=swap');

html, body, [class*="css"], .main, .block-container {
    font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif;
    color: #2C2419;
    font-feature-settings: "tnum" 1, "lnum" 1;
}

.main { background: #FAF7F2 !important; }

.block-container {
    padding-top: 2.5rem !important;
    padding-bottom: 4rem !important;
    max-width: 1320px;
}

h1, h2, h3, h4 {
    font-family: 'Cormorant Garamond', Georgia, serif !important;
    font-weight: 500 !important;
    color: #2C2419 !important;
    letter-spacing: -0.01em;
}
h1 { font-size: 2.6rem !important;  line-height: 1.1 !important;  margin-top: 0 !important; }
h2 { font-size: 1.85rem !important; line-height: 1.2 !important;  margin-top: 1.5rem !important; }
h3 { font-size: 1.4rem !important;  line-height: 1.25 !important; }

[data-testid="stSidebar"] {
    background: #F2EDE4 !important;
    border-right: 0.5px solid #E5DDD0 !important;
    min-width: 280px !important;
}
[data-testid="stSidebar"] > div { padding-top: 3rem !important; }

[data-testid="stSidebarNav"] li a {
    color: #7A6F5F !important;
    font-size: 0.92rem !important;
    padding: 8px 14px !important;
    border-radius: 6px !important;
    letter-spacing: 0.01em;
}
[data-testid="stSidebarNav"] li a:hover {
    background: #E5DDD0 !important;
    color: #2C2419 !important;
}
[data-testid="stSidebarNav"] li a[aria-current="page"] {
    background: #FAF7F2 !important;
    color: #5C4A2F !important;
    font-weight: 500 !important;
    border-left: 2px solid #8B6F47;
}

/* Que TODAS las columnas tengan misma altura → cards alineadas */
[data-testid="stHorizontalBlock"] {
    align-items: stretch !important;
}
[data-testid="column"] > div {
    height: 100%;
}
[data-testid="column"] > div > [data-testid="stVerticalBlock"] {
    height: 100%;
}

[data-testid="stMetric"] {
    background: #F2EDE4;
    border: none;
    border-radius: 8px;
    padding: 20px 22px 18px 22px;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 0.5px solid #E5DDD0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 0 !important;
    padding: 10px 4px !important;
    color: #7A6F5F !important;
    border-bottom: 2px solid transparent !important;
    margin-bottom: -2px !important;
}
.stTabs [aria-selected="true"] {
    color: #5C4A2F !important;
    font-weight: 500 !important;
    border-bottom-color: #8B6F47 !important;
}

.stTextInput input, .stNumberInput input, .stSelectbox > div > div {
    background: #FAF7F2 !important;
    color: #2C2419 !important;
    border: 0.5px solid #E5DDD0 !important;
    border-radius: 6px !important;
}
.stTextInput input:focus, .stNumberInput input:focus {
    border-color: #8B6F47 !important;
    box-shadow: 0 0 0 2px rgba(139, 111, 71, 0.12) !important;
}

.stButton button {
    background: #8B6F47 !important;
    color: #FAF7F2 !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 8px 18px !important;
    font-weight: 500 !important;
}
.stButton button:hover { background: #5C4A2F !important; }

.streamlit-expanderHeader,
[data-testid="stExpander"] details summary {
    background: #F2EDE4 !important;
    color: #2C2419 !important;
    border-radius: 6px !important;
    border: none !important;
}

[data-baseweb="notification"][kind="positive"] {
    background: rgba(107, 142, 90, 0.10) !important;
    color: #4A6240 !important;
    border-left: 2px solid #6B8E5A !important;
}
[data-baseweb="notification"][kind="info"] {
    background: rgba(139, 111, 71, 0.08) !important;
    color: #5C4A2F !important;
    border-left: 2px solid #8B6F47 !important;
}
[data-baseweb="notification"][kind="warning"] {
    background: rgba(184, 137, 90, 0.10) !important;
    color: #7A5A35 !important;
    border-left: 2px solid #B8895A !important;
}
[data-baseweb="notification"][kind="negative"] {
    background: rgba(166, 93, 93, 0.10) !important;
    color: #7A3F3F !important;
    border-left: 2px solid #A65D5D !important;
}

[data-testid="stDataFrame"] {
    border: 0.5px solid #E5DDD0;
    border-radius: 6px;
    overflow: hidden;
}
[data-testid="stDataFrame"] [role="columnheader"] {
    background: #F2EDE4 !important;
    color: #5C4A2F !important;
    font-weight: 500 !important;
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

[data-testid="stPlotlyChart"] {
    background: #FAF7F2;
    border-radius: 6px;
}

[data-testid="stHeader"] {
    background: #FAF7F2 !important;
    border-bottom: 0.5px solid #E5DDD0;
}

hr { border-color: #E5DDD0 !important; margin: 2rem 0 !important; }
a { color: #8B6F47 !important; text-decoration: none; }
a:hover { color: #5C4A2F !important; text-decoration: underline; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: #FAF7F2; }
::-webkit-scrollbar-thumb { background: #C9BCA9; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #A89684; }

/* KPI cards: idénticas en altura, sin saltos de línea */
.kpi-card {
    background: #F2EDE4;
    border-radius: 8px;
    padding: 22px 22px 20px 22px;
    height: 100%;
    min-height: 130px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-sizing: border-box;
}
.kpi-card.hero {
    border-left: 3px solid #8B6F47;
    padding: 24px 28px 22px 28px;
    min-height: 130px;
}
.kpi-label {
    color: #7A6F5F;
    font-size: 0.66rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.10em;
    margin: 0;
}
.kpi-value {
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    color: #2C2419;
    line-height: 1.05;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum" 1;
    margin: 8px 0;
    /* Que el texto NO se rompa nunca, encoja si hace falta */
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.kpi-value.size-hero { font-size: 1.95rem; }
.kpi-value.size-card { font-size: 1.55rem; }
.kpi-value.size-small { font-size: 1.3rem; }
.kpi-delta {
    color: #7A6F5F;
    font-size: 0.78rem;
    margin: 0;
}

/* =====================================================================
   RESPONSIVE · ajustes solo para pantallas pequeñas
   No afectan al diseño desktop (≥ 900px), que queda exactamente igual.
   ===================================================================== */

/* Tablet vertical y portátil pequeño (≤ 1100px) */
@media (max-width: 1100px) {
    .block-container {
        padding-top: 2rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        max-width: 100% !important;
    }
}

/* Tablet pequeña / móvil grande (≤ 900px) */
@media (max-width: 900px) {
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 3rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }

    /* Títulos algo más pequeños para no comerse la pantalla */
    h1 { font-size: 2.1rem !important; }
    h2 { font-size: 1.55rem !important; }
    h3 { font-size: 1.2rem !important; }

    /* Las columnas de Streamlit pasan a apilarse en vertical */
    [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
        gap: 12px !important;
    }
    [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }

    /* KPI cards: ajuste de tamaño y padding */
    .kpi-card,
    .kpi-card.hero {
        padding: 16px 18px 14px 18px;
        min-height: auto;
    }
    .kpi-value.size-hero { font-size: 1.7rem; }
    .kpi-value.size-card { font-size: 1.35rem; }
    .kpi-value.size-small { font-size: 1.15rem; }

    /* Sidebar: en móvil Streamlit ya la oculta tras el botón hamburguesa.
       Ajustamos por si se abre, que se vea bien. */
    [data-testid="stSidebar"] {
        min-width: 240px !important;
    }
    [data-testid="stSidebar"] > div { padding-top: 2rem !important; }

    /* Las grids personalizadas (top clientes, distribución por cluster,
       ranking de tiendas) que usamos en cada página tenían un layout fijo.
       En móvil las hacemos apilarse en vertical, ocupando todo el ancho. */
    div[style*="display:grid;grid-template-columns"] {
        grid-template-columns: 1fr !important;
        gap: 8px !important;
        padding: 12px 0 !important;
    }
    /* Excepción: las cabeceras de tabla las ocultamos en móvil porque
       no aplican al layout vertical */
    div[style*="text-transform:uppercase"][style*="grid-template-columns"] {
        display: none !important;
    }

    /* Microbarras y badges respetan el ancho disponible */
    div[style*="height:6px"] { width: 100% !important; }
    div[style*="height:5px"] { width: 100% !important; }

    /* Datos del finding box más compactos */
    div[style*="font-size:1.45rem"] {
        font-size: 1.2rem !important;
    }

    /* ================================================================
       PLOTLY · responsive en pantallas pequeñas
       ================================================================ */

    /* Que Plotly use todo el ancho del contenedor sin márgenes raros */
    [data-testid="stPlotlyChart"] {
        margin-left: -4px !important;
        margin-right: -4px !important;
    }
    [data-testid="stPlotlyChart"] > div {
        width: 100% !important;
    }
    .js-plotly-plot, .plot-container {
        width: 100% !important;
    }

    /* Leyenda de Plotly: en móvil, debajo del gráfico, no a la derecha */
    .js-plotly-plot .legend {
        font-size: 10px !important;
    }

    /* Ejes de Plotly más compactos */
    .js-plotly-plot .xtick text,
    .js-plotly-plot .ytick text {
        font-size: 9px !important;
    }
    .js-plotly-plot .xtitle,
    .js-plotly-plot .ytitle {
        font-size: 10px !important;
    }

    /* Anotaciones más pequeñas */
    .js-plotly-plot .annotation-text {
        font-size: 9px !important;
    }
}

/* Móvil estrecho (≤ 480px) */
@media (max-width: 480px) {
    h1 { font-size: 1.85rem !important; }
    h2 { font-size: 1.35rem !important; }

    /* Page header: el eyebrow + fecha en columna en lugar de línea */
    div[style*="justify-content:space-between"][style*="align-items:baseline"] {
        flex-direction: column !important;
        gap: 6px !important;
        align-items: flex-start !important;
    }

    /* Tabla nativa de Streamlit con scroll horizontal por si acaso */
    [data-testid="stDataFrame"] {
        overflow-x: auto;
    }

    /* Plotly: que aproveche todo el ancho disponible (incluso fuera del padding) */
    [data-testid="stPlotlyChart"] {
        margin-left: -10px !important;
        margin-right: -10px !important;
    }

    /* Reducir aún más fuentes en móvil estrecho */
    .js-plotly-plot .xtick text,
    .js-plotly-plot .ytick text {
        font-size: 8px !important;
    }
    .js-plotly-plot .legend {
        font-size: 9px !important;
    }
    .js-plotly-plot .annotation-text {
        font-size: 8px !important;
    }
}
"""


def inject_css() -> None:
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------
def _today_es() -> str:
    months = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
              7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}
    now = datetime.now()
    return f"{now.day} {months[now.month]} {now.year}"


def page_header(
    title: str,
    subtitle: str | None = None,
    *,
    show_date: bool = True,
) -> None:
    today = _today_es() if show_date else ""
    sub_html = (
        f'<div style="color:{COLORS["text_dim"]};font-size:0.95rem;'
        f'margin-top:12px;max-width:760px;line-height:1.55;">{subtitle}</div>'
        if subtitle else ""
    )
    date_html = (
        f'<span style="color:{COLORS["text_soft"]};font-size:0.72rem;'
        f'letter-spacing:0.10em;text-transform:uppercase;font-family:Inter;">'
        f'{today}</span>'
        if show_date else ""
    )

    st.markdown(
        f'<div style="padding:0 0 22px 0;'
        f'border-bottom:0.5px solid {COLORS["border"]};margin-bottom:32px;">'
        f'<div style="display:flex;justify-content:space-between;'
        f'align-items:baseline;margin-bottom:10px;">'
        f'<div style="color:{COLORS["primary"]};font-size:0.7rem;'
        'font-weight:600;text-transform:uppercase;letter-spacing:0.20em;'
        'font-family:\'Cormorant Garamond\',Georgia,serif;">'
        '— SALESHEALTH ANALYTICS</div>'
        f'{date_html}'
        '</div>'
        f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
        f'font-size:3rem;font-weight:500;color:{COLORS["text"]};'
        f'letter-spacing:-0.02em;line-height:1.05;">{title}</div>'
        f'{sub_html}</div>',
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str | None = None) -> None:
    sub_html = (
        f'<div style="color:{COLORS["text_dim"]};font-size:0.85rem;'
        f'margin-top:4px;line-height:1.5;">{subtitle}</div>'
        if subtitle else ""
    )
    st.markdown(
        f'<div style="margin:36px 0 16px 0;">'
        f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
        f'font-size:1.85rem;font-weight:500;color:{COLORS["text"]};'
        f'line-height:1.2;letter-spacing:-0.01em;">{title}</div>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def _kpi_html(label: str, value: str, delta: str | None,
              hero: bool = False, size: str = "card") -> str:
    """HTML de una KPI card. Misma estructura, misma altura."""
    delta_html = f'<div class="kpi-delta">{delta}</div>' if delta else '<div class="kpi-delta">&nbsp;</div>'
    classes = f"kpi-card{' hero' if hero else ''}"
    return (
        f'<div class="{classes}">'
        f'  <div class="kpi-label">{label}</div>'
        f'  <div class="kpi-value size-{size}">{value}</div>'
        f'  {delta_html}'
        f'</div>'
    )


def kpi_hero(label: str, value: str, delta: str | None = None) -> None:
    st.markdown(_kpi_html(label, value, delta, hero=True, size="hero"),
                unsafe_allow_html=True)


def kpi_card(label: str, value: str, delta: str | None = None,
             size: str = "card") -> None:
    st.markdown(_kpi_html(label, value, delta, hero=False, size=size),
                unsafe_allow_html=True)


def finding_box(headline: str, body: str, color: str | None = None) -> None:
    accent = color or COLORS["primary"]
    st.markdown(
        f'<div style="margin-top:24px;padding:28px 32px;'
        f'background:{COLORS["bg_card"]};border-radius:8px;'
        f'border-left:3px solid {accent};">'
        f'<div style="font-size:0.7rem;letter-spacing:0.20em;'
        f'text-transform:uppercase;color:{accent};'
        'font-family:\'Cormorant Garamond\',Georgia,serif;font-weight:600;'
        'margin-bottom:14px;">'
        '— Hallazgo principal</div>'
        f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
        f'font-size:1.45rem;font-weight:500;color:{COLORS["text"]};'
        'line-height:1.25;letter-spacing:-0.01em;max-width:920px;'
        'margin-bottom:12px;">'
        f'{headline}</div>'
        f'<div style="font-size:0.92rem;line-height:1.65;'
        f'color:{COLORS["text_dim"]};max-width:820px;">{body}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
#  Formateadores
# ---------------------------------------------------------------------------
def fmt_eur(value: float | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    fmt = f"{{:,.{decimals}f}}"
    formatted = fmt.format(value).replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"


def fmt_eur_compact(value: float | None) -> str:
    """Formato compacto para cifras grandes en KPIs estrechas: 9,68 M €"""
    if value is None:
        return "—"
    if abs(value) >= 1_000_000:
        v = value / 1_000_000
        return f"{v:.2f}".replace(".", ",") + " M €"
    if abs(value) >= 1_000:
        v = value / 1_000
        return f"{v:.1f}".replace(".", ",") + " k €"
    return f"{value:.0f} €"


def fmt_int(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}".replace(",", ".")


def fmt_pct(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f} %".replace(".", ",")


# ---------------------------------------------------------------------------
#  Sidebar común a todas las páginas
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    """
    Sidebar reutilizable: monograma + lockup de marca + snapshot ejecutivo.

    Carga los KPIs ella sola (con cache) para que cualquier página pueda
    llamarla con una línea sin tener que cargar nada antes.
    """
    import streamlit as st  # noqa: F401  (asegurar import perezoso)
    from app.data_access import (
        load_global_kpis,
        load_customer_value,
    )

    # Cargar datos. Si fallan, mostrar sidebar mínimo (no romper la página).
    kpis = None
    n_total = n_champions = pct_champ_base = None
    try:
        kpis = load_global_kpis()
        df = load_customer_value()
        n_total = len(df)
        n_champions = int((df["cluster_name"] == "Champions").sum())
        pct_champ_base = (n_champions / n_total * 100) if n_total else 0
    except Exception:
        pass

    # Bloque 1: monograma + marca
    st.sidebar.markdown(
        f'<div style="padding:0 6px 24px 6px;">'
        f'<div style="width:38px;height:38px;border-radius:50%;'
        f'background:{COLORS["bg"]};border:0.5px solid {COLORS["primary"]};'
        'display:flex;align-items:center;justify-content:center;'
        'margin-bottom:18px;">'
        f'<span style="font-family:\'Cormorant Garamond\',Georgia,serif;'
        f'font-size:1.2rem;color:{COLORS["primary"]};font-weight:500;'
        'letter-spacing:0;">S</span>'
        '</div>'
        f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
        f'font-size:0.66rem;letter-spacing:0.20em;color:{COLORS["primary"]};'
        'font-weight:600;text-transform:uppercase;">'
        'Customer Analytics</div>'
        f'<div style="font-family:\'Cormorant Garamond\',Georgia,serif;'
        f'font-size:1.55rem;color:{COLORS["text"]};margin-top:6px;line-height:1.05;'
        'letter-spacing:-0.01em;">'
        'Saleshealth</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Bloque 2: snapshot (solo si los datos cargaron)
    if kpis is not None and n_total is not None:
        st.sidebar.markdown(
            f'<div style="padding:0 6px 14px 6px;">'
            f'<div style="height:0.5px;background:{COLORS["border"]};margin-bottom:18px;"></div>'
            f'<div style="font-size:0.66rem;letter-spacing:0.10em;'
            f'text-transform:uppercase;color:{COLORS["text_dim"]};margin-bottom:14px;'
            'font-weight:600;">'
            'Snapshot</div>'
            f'<div style="font-size:0.85rem;color:{COLORS["text"]};line-height:2;'
            'font-variant-numeric:tabular-nums;">'
            f'  <div style="display:flex;justify-content:space-between;">'
            f'    <span style="color:{COLORS["text_dim"]};">Clientes</span>'
            f'    <span>{fmt_int(n_total)}</span></div>'
            f'  <div style="display:flex;justify-content:space-between;">'
            f'    <span style="color:{COLORS["text_dim"]};">Pedidos</span>'
            f'    <span>{fmt_int(int(kpis["total_orders"]))}</span></div>'
            f'  <div style="display:flex;justify-content:space-between;">'
            f'    <span style="color:{COLORS["text_dim"]};">Margen</span>'
            f'    <span>{kpis["margin_pct"]:.1f} %</span></div>'
            f'  <div style="display:flex;justify-content:space-between;">'
            f'    <span style="color:{COLORS["text_dim"]};">Champions</span>'
            f'    <span>{n_champions} ({pct_champ_base:.0f} %)</span></div>'
            '</div></div>',
            unsafe_allow_html=True,
        )
