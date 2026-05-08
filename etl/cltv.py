"""
CLTV probabilístico con modelos BG/NBD y Gamma-Gamma.

Genera la tabla `marts.customer_lifetime_value` con tres CLTV por cliente:
  · cltv_historic       Valor histórico real (lo que ya facturó)
  · cltv_predicted_12m  Predicción a 12 meses con BG/NBD + Gamma-Gamma
  · cltv_simple         CLTV de la fórmula sencilla del PDF
                        (avg_order_value * frequency * lifetime)

Y métricas auxiliares:
  · alive_probability   Probabilidad de que el cliente NO esté inactivo
  · expected_purchases_12m  Pedidos esperados en los próximos 12 meses

Modelos:
  · BG/NBD (Beta-Geometric / Negative Binomial Distribution)
    Predice número de transacciones futuras condicionado a la historia.
  · Gamma-Gamma
    Predice valor monetario futuro condicionado al valor histórico.

Ambos son los estándares de industria (lifetimes lib, originalmente
implementados por Bruce Hardie & Peter Fader).

Uso:
    python -m etl.cltv
"""
from __future__ import annotations

import sys
import warnings

import pandas as pd
import psycopg
from lifetimes import BetaGeoFitter, GammaGammaFitter
from lifetimes.utils import summary_data_from_transaction_data

from etl import config

# Silenciar avisos de convergencia esperables con datasets pequeños/ruidosos
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)


# ----------------------------------------------------------------------------
#  DDL del mart
# ----------------------------------------------------------------------------
SQL_DDL = """
DROP TABLE IF EXISTS marts.customer_lifetime_value CASCADE;

CREATE TABLE marts.customer_lifetime_value (
    customer_key                INTEGER       PRIMARY KEY
                                              REFERENCES dwh.dim_customer(customer_key),
    customer_id                 INTEGER       NOT NULL,
    full_name                   VARCHAR(310),

    -- Historia agregada (RFM básico)
    first_purchase              DATE,
    last_purchase               DATE,
    num_orders                  INTEGER       NOT NULL,
    num_units                   INTEGER       NOT NULL,
    revenue_total               NUMERIC(12,2) NOT NULL,
    margin_total                NUMERIC(12,2) NOT NULL,
    avg_order_value             NUMERIC(10,2),

    -- BG/NBD output
    frequency                   INTEGER,                 -- nº recompras
    recency_days                INTEGER,                 -- T(última) - T(primera)
    customer_age_days           INTEGER,                 -- T(observación) - T(primera)
    expected_purchases_12m      NUMERIC(10,4),
    alive_probability           NUMERIC(6,4),            -- 0..1

    -- CLTV variantes
    cltv_historic               NUMERIC(12,2) NOT NULL,
    cltv_predicted_12m          NUMERIC(12,2),
    cltv_simple                 NUMERIC(12,2),

    -- Auditoría
    snapshot_date               DATE          NOT NULL,
    loaded_at                   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_clv_predicted ON marts.customer_lifetime_value (cltv_predicted_12m DESC);
CREATE INDEX idx_clv_alive     ON marts.customer_lifetime_value (alive_probability DESC);

COMMENT ON TABLE marts.customer_lifetime_value
  IS 'CLTV multinivel — histórico, predictivo (BG/NBD + Gamma-Gamma), simple';
"""


# ----------------------------------------------------------------------------
#  Carga de transacciones desde fact_sales
# ----------------------------------------------------------------------------
SQL_TRANSACTIONS = """
SELECT
    fs.customer_key                    AS customer_id,
    fs.sale_timestamp::DATE            AS date,
    fs.net_amount                      AS monetary_value
FROM dwh.fact_sales fs
ORDER BY fs.customer_key, fs.sale_timestamp;
"""


SQL_CUSTOMER_BASE = """
SELECT
    dc.customer_key,
    dc.customer_id,
    dc.full_name,
    MIN(fs.sale_timestamp::DATE)        AS first_purchase,
    MAX(fs.sale_timestamp::DATE)        AS last_purchase,
    COUNT(DISTINCT fs.sale_id)          AS num_orders,
    SUM(fs.quantity)::INT               AS num_units,
    SUM(fs.net_amount)::NUMERIC(12,2)   AS revenue_total,
    SUM(fs.margin_amount)::NUMERIC(12,2) AS margin_total,
    AVG(fs.net_amount)::NUMERIC(10,2)   AS avg_order_value
FROM dwh.dim_customer dc
LEFT JOIN dwh.fact_sales fs ON fs.customer_key = dc.customer_key
GROUP BY dc.customer_key, dc.customer_id, dc.full_name
ORDER BY dc.customer_key;
"""


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Carga transacciones agregadas por (cliente, día) y la base de clientes."""
    with config.connect_dwh() as conn:
        # Clientes (uno por fila)
        df_customers = pd.read_sql(SQL_CUSTOMER_BASE, conn)

        # Transacciones (varias por cliente)
        df_tx = pd.read_sql(SQL_TRANSACTIONS, conn)
        df_tx["date"] = pd.to_datetime(df_tx["date"])

    snapshot_date = df_tx["date"].max()
    return df_customers, df_tx, snapshot_date


def fit_models(
    df_tx: pd.DataFrame,
    snapshot_date: pd.Timestamp,
) -> tuple[pd.DataFrame, BetaGeoFitter, GammaGammaFitter]:
    """
    Ajusta BG/NBD y Gamma-Gamma. Devuelve summary RFM con predicciones.

    BG/NBD se entrena con TODOS los clientes (incluso los de 1 sola compra).
    Gamma-Gamma SOLO con los repetidores (frequency >= 1) y monetary > 0,
    porque su asunción de independencia frecuencia/valor lo requiere.

    Estrategia robusta: si la convergencia falla con un penalizer pequeño,
    se reintenta con valores progresivamente mayores. Si todos fallan,
    `cltv_predicted_12m`, `alive_probability` y `expected_purchases_12m` se
    rellenan con valores por defecto y el pipeline continúa: la fórmula
    sencilla del PDF (`cltv_simple`) y el `cltv_historic` siguen siendo
    válidos y cumplen el entregable de CLTV.
    """
    from lifetimes.utils import ConvergenceError

    summary = summary_data_from_transaction_data(
        df_tx,
        customer_id_col="customer_id",
        datetime_col="date",
        monetary_value_col="monetary_value",
        observation_period_end=snapshot_date,
        freq="D",
    )
    # frequency aquí = nº de RECOMPRAS (no de pedidos totales)
    # T = customer_age en días (al final del periodo)
    # recency = días entre primera y última compra (no es "días desde la última")

    # Filtrar outliers extremos que rompen la optimización numérica
    # (clientes con monetary_value desorbitado por anomalías de datos)
    if len(summary) > 0 and summary["monetary_value"].std() > 0:
        upper = summary["monetary_value"].quantile(0.999)
        summary.loc[summary["monetary_value"] > upper, "monetary_value"] = upper

    # ---- BG/NBD --------------------------------------------------------
    # Probar varios penalizers en orden ascendente
    bgf = None
    for penalizer in [0.001, 0.01, 0.1, 1.0, 10.0]:
        try:
            bgf_try = BetaGeoFitter(penalizer_coef=penalizer)
            bgf_try.fit(
                frequency=summary["frequency"],
                recency=summary["recency"],
                T=summary["T"],
            )
            bgf = bgf_try
            print(f"      · BG/NBD convergió con penalizer={penalizer}")
            break
        except (ConvergenceError, Exception) as exc:
            print(f"      · BG/NBD penalizer={penalizer} falló: {type(exc).__name__}")
            continue

    # ---- Predicciones BG/NBD ------------------------------------------
    if bgf is not None:
        summary["alive_probability"] = bgf.conditional_probability_alive(
            summary["frequency"], summary["recency"], summary["T"]
        )
        summary["expected_purchases_12m"] = bgf.predict(
            t=365,
            frequency=summary["frequency"],
            recency=summary["recency"],
            T=summary["T"],
        )
    else:
        # Fallback heurístico: alive según recency vs T
        # (cliente más reciente → más probable que esté vivo)
        print("      · BG/NBD no convergió, usando heurística simple")
        T_safe = summary["T"].replace(0, 1)
        summary["alive_probability"] = (1 - summary["recency"] / T_safe).clip(0.05, 0.95)
        # purchases esperadas: extrapolar frecuencia histórica al año siguiente
        summary["expected_purchases_12m"] = (
            summary["frequency"] * (365.0 / T_safe)
        ).clip(lower=0)

    # ---- Gamma-Gamma ---------------------------------------------------
    repeaters = summary[(summary["frequency"] > 0) & (summary["monetary_value"] > 0)]
    summary["cltv_predicted_12m"] = 0.0

    ggf = None
    if len(repeaters) > 0:
        for penalizer in [0.001, 0.01, 0.1, 1.0, 10.0]:
            try:
                ggf_try = GammaGammaFitter(penalizer_coef=penalizer)
                ggf_try.fit(
                    frequency=repeaters["frequency"],
                    monetary_value=repeaters["monetary_value"],
                )
                ggf = ggf_try
                print(f"      · Gamma-Gamma convergió con penalizer={penalizer}")
                break
            except (ConvergenceError, Exception) as exc:
                print(f"      · Gamma-Gamma penalizer={penalizer} falló: {type(exc).__name__}")
                continue

    if ggf is not None and bgf is not None and len(repeaters) > 0:
        try:
            clv = ggf.customer_lifetime_value(
                transaction_prediction_model=bgf,
                frequency=repeaters["frequency"],
                recency=repeaters["recency"],
                T=repeaters["T"],
                monetary_value=repeaters["monetary_value"],
                time=12,
                discount_rate=0.01,
                freq="D",
            )
            summary.loc[repeaters.index, "cltv_predicted_12m"] = clv
        except Exception as exc:
            print(f"      · CLV combinado falló: {exc}, usando aprox.")
            # Fallback: monetary medio × purchases esperadas
            summary.loc[repeaters.index, "cltv_predicted_12m"] = (
                repeaters["monetary_value"] * summary.loc[repeaters.index, "expected_purchases_12m"]
            )
    else:
        # Fallback total: aproximación monetary × purchases esperadas
        if len(repeaters) > 0:
            summary.loc[repeaters.index, "cltv_predicted_12m"] = (
                repeaters["monetary_value"] *
                summary.loc[repeaters.index, "expected_purchases_12m"]
            )

    return summary.reset_index(), bgf, ggf


def calculate_simple_cltv(df_customers: pd.DataFrame) -> pd.Series:
    """
    CLTV "fórmula del PDF":
        avg_order_value * frequency_per_year * customer_lifetime_years
    """
    df = df_customers.copy()
    df["lifetime_days"] = (
        pd.to_datetime(df["last_purchase"]) - pd.to_datetime(df["first_purchase"])
    ).dt.days.fillna(0).clip(lower=1)

    df["frequency_per_year"] = df["num_orders"] / (df["lifetime_days"] / 365)
    df["lifetime_years"] = df["lifetime_days"] / 365

    cltv_simple = (
        df["avg_order_value"].fillna(0)
        * df["frequency_per_year"].fillna(0)
        * df["lifetime_years"].fillna(0)
    )
    return cltv_simple.round(2)


def insert_into_mart(df: pd.DataFrame, snapshot_date: pd.Timestamp) -> int:
    """Inserta el dataframe en marts.customer_lifetime_value."""
    cols = [
        "customer_key", "customer_id", "full_name",
        "first_purchase", "last_purchase",
        "num_orders", "num_units", "revenue_total", "margin_total", "avg_order_value",
        "frequency", "recency_days", "customer_age_days",
        "expected_purchases_12m", "alive_probability",
        "cltv_historic", "cltv_predicted_12m", "cltv_simple",
        "snapshot_date",
    ]

    rows = [tuple(r) for r in df[cols].itertuples(index=False, name=None)]

    insert_sql = f"""
        INSERT INTO marts.customer_lifetime_value ({", ".join(cols)})
        VALUES ({", ".join(["%s"] * len(cols))})
    """

    with config.connect_dwh() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE marts.customer_lifetime_value RESTART IDENTITY")
        cur.executemany(insert_sql, rows)
        conn.commit()
    return len(rows)


def main() -> int:
    print("=" * 70)
    print("CLTV · BG/NBD + Gamma-Gamma + simple")
    print("=" * 70)

    # 1. DDL del mart
    print("[1/5] Creando tabla marts.customer_lifetime_value...")
    with config.connect_dwh() as conn, conn.cursor() as cur:
        # CREATE SCHEMA si no existe
        cur.execute("CREATE SCHEMA IF NOT EXISTS marts")
        cur.execute(SQL_DDL)
        conn.commit()

    # 2. Cargar datos
    print("[2/5] Cargando transacciones desde dwh.fact_sales...")
    df_customers, df_tx, snapshot_date = load_data()
    print(f"      · {len(df_customers):,} clientes")
    print(f"      · {len(df_tx):,} transacciones")
    print(f"      · snapshot: {snapshot_date.date()}")

    # 3. Ajustar modelos
    print("[3/5] Ajustando modelos BG/NBD y Gamma-Gamma...")
    summary, bgf, ggf = fit_models(df_tx, snapshot_date)

    # Compactar columnas de summary
    summary.rename(
        columns={
            "customer_id": "customer_key",
            "recency": "recency_days",
            "T":       "customer_age_days",
        },
        inplace=True,
    )
    summary["recency_days"]      = summary["recency_days"].astype(int)
    summary["customer_age_days"] = summary["customer_age_days"].astype(int)
    summary["frequency"]         = summary["frequency"].astype(int)
    summary["alive_probability"] = summary["alive_probability"].round(4)
    summary["expected_purchases_12m"] = summary["expected_purchases_12m"].round(4)
    summary["cltv_predicted_12m"]     = summary["cltv_predicted_12m"].round(2)

    if bgf is not None:
        print(f"      · BG/NBD ajustado correctamente")
    else:
        print(f"      · BG/NBD usando heurística (no convergió)")
    print(f"      · alive_probability media = "
          f"{summary['alive_probability'].mean():.3f}")

    # 4. Combinar con base de clientes y CLTV histórico/simple
    print("[4/5] Calculando CLTV histórico y simple...")
    base = df_customers.merge(
        summary[["customer_key", "frequency", "recency_days", "customer_age_days",
                 "alive_probability", "expected_purchases_12m",
                 "cltv_predicted_12m"]],
        on="customer_key",
        how="left",
    )
    base["cltv_historic"] = base["margin_total"].fillna(0).round(2)
    base["cltv_simple"]   = calculate_simple_cltv(base)
    base["snapshot_date"] = snapshot_date.date()

    # Rellenar nulos para clientes sin compras
    fill_zero = ["num_orders", "num_units", "revenue_total", "margin_total",
                 "frequency", "recency_days", "customer_age_days",
                 "expected_purchases_12m", "cltv_predicted_12m",
                 "cltv_historic", "cltv_simple"]
    for col in fill_zero:
        base[col] = base[col].fillna(0)

    # 5. Insertar
    print("[5/5] Insertando en marts.customer_lifetime_value...")
    n = insert_into_mart(base, snapshot_date)
    print(f"      · {n:,} filas insertadas")

    # Resumen
    print()
    with config.connect_dwh() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*)                                         AS n,
                COUNT(*) FILTER (WHERE num_orders >= 2)          AS repeaters,
                ROUND(AVG(alive_probability)::NUMERIC, 3)        AS avg_alive,
                ROUND(SUM(cltv_historic)::NUMERIC, 0)            AS total_historic,
                ROUND(SUM(cltv_predicted_12m)::NUMERIC, 0)       AS total_pred_12m,
                ROUND(AVG(cltv_predicted_12m)::NUMERIC, 2)       AS avg_pred_12m
            FROM marts.customer_lifetime_value
        """)
        n, rep, alive, hist, pred, avg_pred = cur.fetchone()
        print(f"  Resumen:")
        print(f"    Clientes              {n:>10,}")
        print(f"    Repetidores (≥2)      {rep:>10,}")
        print(f"    Alive prob. media     {alive:>10}")
        print(f"    CLTV histórico Σ      {hist:>10,.0f} €")
        print(f"    CLTV pred. 12m Σ      {pred:>10,.0f} €")
        print(f"    CLTV pred. 12m media  {avg_pred:>10,.2f} €")

    print()
    print("=" * 70)
    print("OK · CLTV calculado.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except psycopg.OperationalError as exc:
        print(f"\nERROR de conexión: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
