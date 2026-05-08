"""
Transformación stg → dwh para las 4 dimensiones.

Esta fase puebla las tablas dimensionales del schema `dwh` a partir del
staging. Todo se hace con SQL nativo de Postgres (más rápido que pandas
y más legible).

  · dim_date     → calendario sintético (2019-01-01 a 2026-12-31)
  · dim_customer → uno por cliente, con cohorte mensual
  · dim_product  → producto (catálogo local) + central_product (master)
                   → categorías y marcas vienen de central_product / brand
  · dim_location → store + city_zone

Notas sobre el schema origen:
  · `stg.product` tiene categoría como TEXTO (denormalizada) y precio en
    columna `price`. La normalización vía `category_id`/`brand_id` está
    en `stg.central_product`.
  · `stg.central_product` tiene `unit_cost` y `unit_price` (master).
  · `stg.sale` usa `sale_date` (no sale_timestamp).
  · `stg.return_item` usa `return_date` y `quantity`, sin `refund_amount`
    (se calcula a partir del subtotal proporcional de sale_item).

Uso:
    python -m etl.transform_dimensions
"""
from __future__ import annotations

import sys
import time

import psycopg

from etl import config


# ----------------------------------------------------------------------------
#  SQL · dim_date
# ----------------------------------------------------------------------------
SQL_DIM_DATE = """
TRUNCATE dwh.dim_date RESTART IDENTITY CASCADE;

INSERT INTO dwh.dim_date
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT          AS date_key,
    d                                     AS full_date,
    EXTRACT(YEAR    FROM d)::SMALLINT     AS year,
    EXTRACT(QUARTER FROM d)::SMALLINT     AS quarter,
    EXTRACT(MONTH   FROM d)::SMALLINT     AS month,
    INITCAP(TO_CHAR(d, 'TMMonth'))        AS month_name,
    EXTRACT(WEEK    FROM d)::SMALLINT     AS week_of_year,
    EXTRACT(DAY     FROM d)::SMALLINT     AS day_of_month,
    EXTRACT(ISODOW  FROM d)::SMALLINT     AS day_of_week,
    INITCAP(TO_CHAR(d, 'TMDay'))          AS day_name,
    EXTRACT(ISODOW FROM d) IN (6, 7)      AS is_weekend,
    TO_CHAR(d, 'YYYY-MM')                 AS year_month
FROM generate_series(
        '2019-01-01'::DATE,
        '2026-12-31'::DATE,
        '1 day'::INTERVAL
) AS d;
"""


# ----------------------------------------------------------------------------
#  SQL · dim_customer
# ----------------------------------------------------------------------------
SQL_DIM_CUSTOMER = """
TRUNCATE dwh.dim_customer RESTART IDENTITY CASCADE;

INSERT INTO dwh.dim_customer
    (customer_id, full_name, email, phone, signup_date, signup_year, signup_month)
SELECT
    customer_id,
    TRIM(CONCAT_WS(' ',
        NULLIF(first_name,''),
        NULLIF(last_name,''),
        NULLIF(last_name2,'')
    ))                                              AS full_name,
    email,
    phone,
    created_at::DATE                                AS signup_date,
    EXTRACT(YEAR FROM created_at)::SMALLINT         AS signup_year,
    TO_CHAR(created_at, 'YYYY-MM')                  AS signup_month
FROM stg.customer
ORDER BY customer_id;
"""


# ----------------------------------------------------------------------------
#  SQL · dim_product
# ----------------------------------------------------------------------------
#  Joins:
#    stg.product (catálogo local) + stg.central_product (master con coste y
#    relaciones) + stg.category (nombre de categoría) + stg.brand (marca y
#    fabricante).
#
#  Notas:
#    · Algunos productos pueden NO existir en central_product. En ese caso,
#      tomamos `category` desde stg.product (texto), y dejamos brand/sku
#      en NULL. Marcamos cost_was_imputed=TRUE.
#    · El precio "oficial" lo cogemos de central_product.unit_price si
#      está, y si no, de stg.product.price.
#    · El coste se imputa al 60% del precio si no hay central_product.
# ----------------------------------------------------------------------------
SQL_DIM_PRODUCT = """
TRUNCATE dwh.dim_product RESTART IDENTITY CASCADE;

INSERT INTO dwh.dim_product
    (product_id, product_name, sku, barcode, category_name, brand_name,
     manufacturer, unit_price, unit_cost, margin_pct, cost_was_imputed)
SELECT
    p.product_id,
    p.name                                          AS product_name,
    cp.sku,
    cp.barcode,
    -- categoría: la del master si existe (vía join), sino la denormalizada de product
    COALESCE(c.name, p.category)                    AS category_name,
    b.name                                          AS brand_name,
    -- manufacturer: el de stg.product (stg.brand no tiene esa columna)
    p.manufacturer                                  AS manufacturer,
    COALESCE(cp.unit_price, p.price)                AS unit_price,
    COALESCE(cp.unit_cost,
             ROUND((COALESCE(cp.unit_price, p.price) * 0.6)::NUMERIC, 2))
                                                    AS unit_cost,
    CASE
        WHEN COALESCE(cp.unit_price, p.price) > 0
        THEN ROUND(
            ((COALESCE(cp.unit_price, p.price) -
              COALESCE(cp.unit_cost, COALESCE(cp.unit_price, p.price) * 0.6))
              / COALESCE(cp.unit_price, p.price) * 100)::NUMERIC, 2
        )
        ELSE NULL
    END                                             AS margin_pct,
    cp.unit_cost IS NULL                            AS cost_was_imputed
FROM stg.product p
LEFT JOIN stg.central_product cp ON cp.product_id  = p.product_id
LEFT JOIN stg.category        c  ON c.category_id  = cp.category_id
LEFT JOIN stg.brand           b  ON b.brand_id     = cp.brand_id
ORDER BY p.product_id;
"""


# ----------------------------------------------------------------------------
#  SQL · dim_location
# ----------------------------------------------------------------------------
SQL_DIM_LOCATION = """
TRUNCATE dwh.dim_location RESTART IDENTITY CASCADE;

INSERT INTO dwh.dim_location
    (store_id, store_name, address, postal_code, district, city,
     area_type, zone_orientation, latitude, longitude, opened_date)
SELECT
    s.store_id,
    s.name                              AS store_name,
    s.address,
    s.postal_code,
    cz.district,
    COALESCE(cz.city, s.city, 'Madrid') AS city,
    cz.area_type,
    cz.zone_orientation,
    s.latitude,
    s.longitude,
    s.opened_date
FROM stg.store s
LEFT JOIN stg.city_zone cz ON cz.postal_code = s.postal_code
ORDER BY s.store_id;
"""


# ----------------------------------------------------------------------------
#  Verificaciones rápidas tras cargar
# ----------------------------------------------------------------------------
SQL_COUNTS = """
SELECT 'dim_date'     AS table_name, COUNT(*) AS rows FROM dwh.dim_date
UNION ALL SELECT 'dim_customer', COUNT(*) FROM dwh.dim_customer
UNION ALL SELECT 'dim_product',  COUNT(*) FROM dwh.dim_product
UNION ALL SELECT 'dim_location', COUNT(*) FROM dwh.dim_location
ORDER BY 1;
"""


def run_sql(conn, label: str, sql: str) -> float:
    """Ejecuta un bloque SQL y devuelve el tiempo en segundos."""
    t0 = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    return time.perf_counter() - t0


def main() -> int:
    print("=" * 70)
    print("Transform · dimensiones (stg → dwh)")
    print("=" * 70)

    with config.connect_dwh() as conn:
        steps = [
            ("dim_date",     SQL_DIM_DATE),
            ("dim_customer", SQL_DIM_CUSTOMER),
            ("dim_product",  SQL_DIM_PRODUCT),
            ("dim_location", SQL_DIM_LOCATION),
        ]
        for i, (name, sql) in enumerate(steps, 1):
            elapsed = run_sql(conn, name, sql)
            print(f"  [{i}/{len(steps)}] {name:<14}  {elapsed:>5.2f}s")

        # Resumen
        print()
        with conn.cursor() as cur:
            cur.execute(SQL_COUNTS)
            for table_name, rows in cur.fetchall():
                print(f"    {table_name:<14}  {rows:>8,} filas")

    print()
    print("=" * 70)
    print("OK · dimensiones pobladas.")
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
