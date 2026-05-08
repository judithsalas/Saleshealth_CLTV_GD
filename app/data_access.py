"""
Capa de acceso a datos para el dashboard.

Funciones de carga con `@st.cache_data` para evitar consultas repetidas.
Todas leen del DWH `saleshealth_cltv` (los marts ya están pre-calculados).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Permitir importar etl/* desde app/
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from etl import config


# ---------------------------------------------------------------------------
#  Engine reutilizable
# ---------------------------------------------------------------------------
def _read_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Ejecuta una query con conexión nueva y devuelve DataFrame."""
    with config.connect_dwh() as conn:
        return pd.read_sql(sql, conn, params=params or {})


# ---------------------------------------------------------------------------
#  KPIs globales
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def load_global_kpis() -> dict:
    """Métricas agregadas del negocio."""
    sql = """
        SELECT
            (SELECT COUNT(*)                       FROM dwh.dim_customer)        AS total_customers,
            (SELECT COUNT(*)                       FROM dwh.fact_sales)          AS total_lines,
            (SELECT COUNT(DISTINCT sale_id)        FROM dwh.fact_sales)          AS total_orders,
            (SELECT COALESCE(SUM(net_amount), 0)::FLOAT     FROM dwh.fact_sales) AS total_revenue,
            (SELECT COALESCE(SUM(margin_amount), 0)::FLOAT  FROM dwh.fact_sales) AS total_margin,
            (SELECT COALESCE(SUM(refund_amount), 0)::FLOAT  FROM dwh.fact_returns) AS total_refunds,
            (SELECT COALESCE(SUM(margin_lost), 0)::FLOAT    FROM dwh.fact_returns) AS margin_lost
    """
    df = _read_sql(sql)
    row = df.iloc[0].to_dict()
    row["margin_pct"] = (
        row["total_margin"] / row["total_revenue"] * 100
        if row["total_revenue"] else 0
    )
    return row


@st.cache_data(ttl=600, show_spinner=False)
def load_monthly_sales() -> pd.DataFrame:
    """Evolución mensual de ingresos, margen y devoluciones."""
    sql = """
        SELECT
            d.year_month                                 AS year_month,
            COUNT(DISTINCT s.sale_id)                    AS n_orders,
            COUNT(DISTINCT s.customer_key)               AS n_customers,
            SUM(s.net_amount)::FLOAT                     AS revenue,
            SUM(s.margin_amount)::FLOAT                  AS margin,
            COUNT(*) FILTER (WHERE s.is_returned)::INT   AS items_returned,
            COUNT(*)::INT                                AS items_total
        FROM dwh.fact_sales s
        JOIN dwh.dim_date   d ON s.date_key = d.date_key
        GROUP BY d.year_month
        ORDER BY d.year_month
    """
    df = _read_sql(sql)
    df["margin_pct"]      = (df["margin"]         / df["revenue"]     * 100).round(2)
    df["return_rate_pct"] = (df["items_returned"] / df["items_total"] * 100).round(2)
    return df


# ---------------------------------------------------------------------------
#  Customer-level
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def load_customer_value() -> pd.DataFrame:
    """
    Tabla principal del dashboard: cliente + CLTV + cluster.

    Combina marts.customer_lifetime_value con marts.customer_segments.
    """
    sql = """
        SELECT
            clv.customer_key,
            clv.customer_id,
            clv.full_name,
            clv.first_purchase,
            clv.last_purchase,
            clv.num_orders,
            clv.num_units,
            clv.revenue_total,
            clv.margin_total,
            clv.avg_order_value,
            clv.frequency,
            clv.recency_days,
            clv.customer_age_days,
            clv.expected_purchases_12m,
            clv.alive_probability,
            clv.cltv_historic,
            clv.cltv_predicted_12m,
            clv.cltv_simple,
            seg.cluster_id,
            seg.cluster_name,
            seg.pca_x,
            seg.pca_y,
            seg.umap_x,
            seg.umap_y
        FROM marts.customer_lifetime_value  clv
        LEFT JOIN marts.customer_segments   seg ON seg.customer_key = clv.customer_key
        ORDER BY clv.cltv_predicted_12m DESC NULLS LAST
    """
    return _read_sql(sql)


@st.cache_data(ttl=600, show_spinner=False)
def load_customer_orders(customer_key: int) -> pd.DataFrame:
    """Histórico de pedidos de un cliente concreto."""
    sql = """
        SELECT
            fs.sale_id,
            fs.sale_timestamp::DATE     AS date,
            COUNT(*)                    AS n_lines,
            SUM(fs.quantity)::INT       AS units,
            SUM(fs.net_amount)::FLOAT   AS amount,
            SUM(fs.margin_amount)::FLOAT AS margin,
            BOOL_OR(fs.is_returned)     AS has_return
        FROM dwh.fact_sales fs
        WHERE fs.customer_key = %(customer_key)s
        GROUP BY fs.sale_id, fs.sale_timestamp
        ORDER BY fs.sale_timestamp DESC
    """
    return _read_sql(sql, {"customer_key": customer_key})


# ---------------------------------------------------------------------------
#  Cluster-level
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def load_cluster_summary() -> pd.DataFrame:
    """Resumen agregado por cluster."""
    sql = """
        SELECT
            seg.cluster_id,
            seg.cluster_name,
            COUNT(*)                                            AS n_customers,
            ROUND(AVG(clv.num_orders)::NUMERIC, 1)              AS avg_orders,
            ROUND(AVG(clv.revenue_total)::NUMERIC, 0)           AS avg_revenue,
            ROUND(AVG(clv.margin_total)::NUMERIC, 0)            AS avg_margin,
            ROUND(AVG(clv.cltv_predicted_12m)::NUMERIC, 0)      AS avg_cltv_12m,
            ROUND(AVG(clv.alive_probability)::NUMERIC, 3)       AS avg_alive,
            ROUND(SUM(clv.cltv_predicted_12m)::NUMERIC, 0)      AS total_cltv_12m,
            ROUND(SUM(clv.margin_total)::NUMERIC, 0)            AS total_margin
        FROM marts.customer_segments      seg
        JOIN marts.customer_lifetime_value clv ON clv.customer_key = seg.customer_key
        GROUP BY seg.cluster_id, seg.cluster_name
        ORDER BY total_cltv_12m DESC
    """
    return _read_sql(sql)


@st.cache_data(ttl=600, show_spinner=False)
def load_cluster_metrics() -> pd.DataFrame | None:
    """Métricas Elbow + Silhouette + Davies-Bouldin del análisis de K."""
    path = config.EXPORTS_DIR / "cluster_metrics.csv"
    if not path.exists():
        return None
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
#  Tiendas (mapa interactivo)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def load_stores_metrics() -> pd.DataFrame:
    """
    Métricas agregadas por tienda · para el mapa interactivo.

    Devuelve una fila por tienda con coordenadas y métricas de negocio:
    revenue total, margen, % margen, número de clientes, número de pedidos,
    ratio de devolución, ticket medio.
    """
    sql = """
        WITH sales_agg AS (
            SELECT
                fs.location_key,
                SUM(fs.net_amount)::FLOAT             AS revenue,
                SUM(fs.margin_amount)::FLOAT          AS margin,
                SUM(fs.quantity)::INT                 AS units,
                COUNT(DISTINCT fs.sale_id)            AS n_orders,
                COUNT(DISTINCT fs.customer_key)       AS n_customers,
                COUNT(*)                              AS n_lines,
                COUNT(*) FILTER (WHERE fs.is_returned)::INT AS n_returned
            FROM dwh.fact_sales fs
            GROUP BY fs.location_key
        )
        SELECT
            dl.location_key,
            dl.store_id,
            dl.store_name,
            dl.address,
            dl.postal_code,
            dl.district,
            dl.city,
            dl.area_type,
            dl.zone_orientation,
            dl.latitude::FLOAT          AS latitude,
            dl.longitude::FLOAT         AS longitude,
            dl.opened_date,
            COALESCE(s.revenue, 0)      AS revenue,
            COALESCE(s.margin, 0)       AS margin,
            COALESCE(s.units, 0)        AS units,
            COALESCE(s.n_orders, 0)     AS n_orders,
            COALESCE(s.n_customers, 0)  AS n_customers,
            COALESCE(s.n_returned, 0)   AS n_returned,
            COALESCE(s.n_lines, 0)      AS n_lines
        FROM dwh.dim_location dl
        LEFT JOIN sales_agg s ON s.location_key = dl.location_key
        WHERE dl.latitude IS NOT NULL AND dl.longitude IS NOT NULL
        ORDER BY revenue DESC
    """
    df = _read_sql(sql)
    if len(df):
        df["margin_pct"] = (df["margin"] / df["revenue"].replace(0, 1) * 100).round(2)
        df["return_rate_pct"] = (df["n_returned"] / df["n_lines"].replace(0, 1) * 100).round(2)
        df["avg_ticket"] = (df["revenue"] / df["n_orders"].replace(0, 1)).round(2)
    return df
