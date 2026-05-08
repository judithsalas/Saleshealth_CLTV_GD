"""
Transformación stg → dwh para los dos hechos.

  · fact_sales    → 1 fila por sale_item (línea de venta)
  · fact_returns  → 1 fila por return_item

Notas sobre el schema origen:
  · `stg.sale` usa `sale_date` (timestamp).
  · `stg.sale_item` ya trae `subtotal` calculado: lo usamos como
    `gross_amount` directamente. También trae `unit_price` por línea.
  · `stg.return_item` solo tiene `quantity` y `return_date`; el
    `refund_amount` se calcula proporcionalmente al subtotal de la
    línea original.

Reglas de negocio:
  · gross_amount = subtotal (ya calculado en origen) o quantity * unit_price
  · net_amount = gross_amount (no hay descuentos por línea aplicados aquí)
  · cost_amount = quantity * unit_cost (de dim_product)
  · margin_amount = net_amount - cost_amount
  · refund_amount = (quantity_returned / quantity_vendida) * subtotal
  · days_to_return = (return_date - sale_date), GREATEST(0, ...)

Uso:
    python -m etl.transform_facts
"""
from __future__ import annotations

import sys
import time

import psycopg

from etl import config


# ----------------------------------------------------------------------------
#  fact_sales
# ----------------------------------------------------------------------------
SQL_FACT_SALES = """
TRUNCATE dwh.fact_sales RESTART IDENTITY CASCADE;

INSERT INTO dwh.fact_sales (
    sale_id, sale_item_id,
    customer_key, product_key, location_key, date_key,
    sale_timestamp, quantity, unit_price, unit_cost,
    gross_amount, discount_amount, net_amount, cost_amount, margin_amount,
    has_discount, is_returned
)
SELECT
    s.sale_id,
    si.sale_item_id,
    dc.customer_key,
    dp.product_key,
    dl.location_key,
    dd.date_key,
    s.sale_date                                                       AS sale_timestamp,
    si.quantity,
    si.unit_price,
    dp.unit_cost,
    -- medidas: priorizar subtotal pre-calculado de origen
    COALESCE(si.subtotal, si.quantity * si.unit_price)                AS gross_amount,
    0                                                                  AS discount_amount,
    COALESCE(si.subtotal, si.quantity * si.unit_price)                AS net_amount,
    (si.quantity * dp.unit_cost)                                      AS cost_amount,
    COALESCE(si.subtotal, si.quantity * si.unit_price)
        - (si.quantity * dp.unit_cost)                                AS margin_amount,
    -- flags
    si.offer_id IS NOT NULL                                            AS has_discount,
    EXISTS (
        SELECT 1 FROM stg.return_item ri
        WHERE ri.sale_item_id = si.sale_item_id
    )                                                                  AS is_returned
FROM stg.sale_item si
JOIN stg.sale       s  ON s.sale_id      = si.sale_id
JOIN dwh.dim_customer  dc ON dc.customer_id = s.customer_id
JOIN dwh.dim_product   dp ON dp.product_id  = si.product_id
JOIN dwh.dim_location  dl ON dl.store_id    = s.store_id
JOIN dwh.dim_date      dd ON dd.full_date   = s.sale_date::DATE
ORDER BY s.sale_date, si.sale_item_id;
"""


# ----------------------------------------------------------------------------
#  fact_returns
# ----------------------------------------------------------------------------
#  Notas:
#    · stg.return_item NO trae refund_amount → lo calculamos proporcional.
#    · stg.return_item.quantity = unidades devueltas.
# ----------------------------------------------------------------------------
SQL_FACT_RETURNS = """
TRUNCATE dwh.fact_returns RESTART IDENTITY CASCADE;

INSERT INTO dwh.fact_returns (
    return_id, sale_item_id, sale_item_key,
    customer_key, product_key, location_key, date_key,
    return_timestamp, sale_timestamp, days_to_return,
    return_reason, quantity_returned,
    refund_amount, cost_recovered, margin_lost
)
SELECT
    ri.return_id,
    ri.sale_item_id,
    fs.sale_item_key,
    fs.customer_key,
    fs.product_key,
    fs.location_key,
    dd.date_key,
    ri.return_date                                                   AS return_timestamp,
    fs.sale_timestamp,
    GREATEST(
        0,
        EXTRACT(DAY FROM (ri.return_date - fs.sale_timestamp))::INT
    )                                                                AS days_to_return,
    rr.reason                                                        AS return_reason,
    ri.quantity                                                      AS quantity_returned,
    -- refund proporcional: (qty_devuelta / qty_vendida) * subtotal
    CASE WHEN fs.quantity > 0
         THEN ROUND(
            ((ri.quantity::NUMERIC / fs.quantity) * fs.net_amount)::NUMERIC, 2
         )
         ELSE 0
    END                                                              AS refund_amount,
    -- coste recuperado (proporcional)
    CASE WHEN fs.quantity > 0
         THEN ROUND(
            ((ri.quantity::NUMERIC / fs.quantity) * fs.cost_amount)::NUMERIC, 2
         )
         ELSE 0
    END                                                              AS cost_recovered,
    -- margen perdido = refund proporcional - coste recuperado
    CASE WHEN fs.quantity > 0
         THEN ROUND(
            ((ri.quantity::NUMERIC / fs.quantity)
              * (fs.net_amount - fs.cost_amount))::NUMERIC, 2
         )
         ELSE 0
    END                                                              AS margin_lost
FROM stg.return_item ri
JOIN dwh.fact_sales      fs ON fs.sale_item_id = ri.sale_item_id
LEFT JOIN stg.return_reason rr ON rr.reason_id = ri.reason_id
JOIN dwh.dim_date        dd ON dd.full_date = ri.return_date::DATE
ORDER BY ri.return_date;
"""


SQL_COUNTS = """
SELECT 'fact_sales'   AS table_name, COUNT(*) AS rows FROM dwh.fact_sales
UNION ALL SELECT 'fact_returns', COUNT(*) FROM dwh.fact_returns
ORDER BY 1;
"""


SQL_BUSINESS_METRICS = """
SELECT
    SUM(net_amount)::NUMERIC(14,2)      AS total_revenue,
    SUM(margin_amount)::NUMERIC(14,2)   AS total_margin,
    COUNT(DISTINCT customer_key)        AS unique_customers,
    COUNT(DISTINCT sale_id)             AS total_orders
FROM dwh.fact_sales;
"""


def run_sql(conn, sql: str) -> float:
    t0 = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    return time.perf_counter() - t0


def main() -> int:
    print("=" * 70)
    print("Transform · hechos (stg → dwh)")
    print("=" * 70)

    with config.connect_dwh() as conn:
        # 1. fact_sales
        elapsed = run_sql(conn, SQL_FACT_SALES)
        print(f"  [1/2] fact_sales     {elapsed:>5.2f}s")

        # 2. fact_returns
        elapsed = run_sql(conn, SQL_FACT_RETURNS)
        print(f"  [2/2] fact_returns   {elapsed:>5.2f}s")

        # Resumen
        print()
        with conn.cursor() as cur:
            cur.execute(SQL_COUNTS)
            for name, rows in cur.fetchall():
                print(f"    {name:<14}  {rows:>8,} filas")

            print()
            cur.execute(SQL_BUSINESS_METRICS)
            row = cur.fetchone()
            if row:
                rev, margin, customers, orders = row
                print(f"  Métricas de negocio:")
                print(f"    Revenue total      {rev:>15,.2f} €")
                print(f"    Margen total       {margin:>15,.2f} €")
                print(f"    Clientes únicos    {customers:>15,}")
                print(f"    Pedidos totales    {orders:>15,}")

    print()
    print("=" * 70)
    print("OK · hechos poblados.")
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
