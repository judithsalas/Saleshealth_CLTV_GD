"""
Validaciones de calidad de datos del DWH.

Bateria declarativa de checks que se ejecutan tras el ETL. Cada check tiene:
  · category   : grupo lógico (counts, integrity, business, consistency)
  · name       : descripción humana
  · sql        : consulta que debe devolver una fila con (actual, expected)
  · severity   : 'error' aborta el pipeline; 'warning' solo avisa

Cuando un check falla:
  · Si severity='error' → exit code 1 (rompe el `python run.py --all`).
  · Si severity='warning' → log y continúa.

Uso:
    python -m etl.validate
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

import psycopg

from etl import config


# ----------------------------------------------------------------------------
#  Definición de checks
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Check:
    category: str
    name: str
    sql: str
    severity: str = "error"          # 'error' | 'warning'


CHECKS: list[Check] = [
    # ----- Counts: las filas cargadas tienen sentido --------------------
    Check(
        category="counts",
        name="dim_date tiene calendario completo (>2900 filas)",
        sql="""
            SELECT COUNT(*) AS actual, 2900 AS expected
            FROM dwh.dim_date
        """,
    ),
    Check(
        category="counts",
        name="dim_customer no está vacía",
        sql="""
            SELECT COUNT(*) AS actual, 1 AS expected
            FROM dwh.dim_customer
        """,
    ),
    Check(
        category="counts",
        name="dim_product no está vacía",
        sql="""
            SELECT COUNT(*) AS actual, 1 AS expected
            FROM dwh.dim_product
        """,
    ),
    Check(
        category="counts",
        name="dim_location no está vacía",
        sql="""
            SELECT COUNT(*) AS actual, 1 AS expected
            FROM dwh.dim_location
        """,
    ),
    Check(
        category="counts",
        name="fact_sales contiene ventas",
        sql="""
            SELECT COUNT(*) AS actual, 1 AS expected
            FROM dwh.fact_sales
        """,
    ),
    Check(
        category="counts",
        name="fact_returns contiene devoluciones",
        sql="""
            SELECT COUNT(*) AS actual, 1 AS expected
            FROM dwh.fact_returns
        """,
    ),

    # ----- Counts: paridad stg vs dwh -----------------------------------
    Check(
        category="counts",
        name="dim_customer == stg.customer (sin pérdida)",
        sql="""
            SELECT
                (SELECT COUNT(*) FROM dwh.dim_customer)  AS actual,
                (SELECT COUNT(*) FROM stg.customer)      AS expected
        """,
    ),
    Check(
        category="counts",
        name="dim_product == stg.product (sin pérdida)",
        sql="""
            SELECT
                (SELECT COUNT(*) FROM dwh.dim_product)   AS actual,
                (SELECT COUNT(*) FROM stg.product)       AS expected
        """,
    ),
    Check(
        category="counts",
        name="fact_sales == stg.sale_item (sin pérdida)",
        sql="""
            SELECT
                (SELECT COUNT(*) FROM dwh.fact_sales)    AS actual,
                (SELECT COUNT(*) FROM stg.sale_item)     AS expected
        """,
    ),
    Check(
        category="counts",
        name="fact_returns == stg.return_item (sin pérdida)",
        sql="""
            SELECT
                (SELECT COUNT(*) FROM dwh.fact_returns)  AS actual,
                (SELECT COUNT(*) FROM stg.return_item)   AS expected
        """,
    ),

    # ----- Integrity: no hay FKs huérfanas (deben ser 0) ----------------
    Check(
        category="integrity",
        name="0 huérfanas customer_key en fact_sales",
        sql="""
            SELECT COUNT(*) AS actual, 0 AS expected
            FROM dwh.fact_sales fs
            LEFT JOIN dwh.dim_customer dc ON dc.customer_key = fs.customer_key
            WHERE dc.customer_key IS NULL
        """,
    ),
    Check(
        category="integrity",
        name="0 huérfanas product_key en fact_sales",
        sql="""
            SELECT COUNT(*) AS actual, 0 AS expected
            FROM dwh.fact_sales fs
            LEFT JOIN dwh.dim_product dp ON dp.product_key = fs.product_key
            WHERE dp.product_key IS NULL
        """,
    ),
    Check(
        category="integrity",
        name="0 huérfanas date_key en fact_sales",
        sql="""
            SELECT COUNT(*) AS actual, 0 AS expected
            FROM dwh.fact_sales fs
            LEFT JOIN dwh.dim_date dd ON dd.date_key = fs.date_key
            WHERE dd.date_key IS NULL
        """,
    ),

    # ----- Business: reglas que deben cumplirse -------------------------
    Check(
        category="business",
        name="0 ventas con quantity ≤ 0",
        sql="""
            SELECT COUNT(*) AS actual, 0 AS expected
            FROM dwh.fact_sales
            WHERE quantity <= 0
        """,
    ),
    Check(
        category="business",
        name="0 ventas con net_amount negativo",
        sql="""
            SELECT COUNT(*) AS actual, 0 AS expected
            FROM dwh.fact_sales
            WHERE net_amount < 0
        """,
    ),
    Check(
        category="business",
        name="0 devoluciones sin venta correspondiente",
        sql="""
            SELECT COUNT(*) AS actual, 0 AS expected
            FROM dwh.fact_returns fr
            LEFT JOIN dwh.fact_sales fs ON fs.sale_item_key = fr.sale_item_key
            WHERE fs.sale_item_key IS NULL
        """,
    ),
    Check(
        category="business",
        name="days_to_return >= 0 en todas las devoluciones",
        sql="""
            SELECT COUNT(*) AS actual, 0 AS expected
            FROM dwh.fact_returns
            WHERE days_to_return < 0
        """,
    ),

    # ----- Consistency: flag is_returned coherente ----------------------
    Check(
        category="consistency",
        name="is_returned coincide con existencia en fact_returns",
        sql="""
            SELECT COUNT(*) AS actual, 0 AS expected
            FROM dwh.fact_sales fs
            WHERE
              fs.is_returned IS DISTINCT FROM EXISTS (
                  SELECT 1 FROM dwh.fact_returns fr
                  WHERE fr.sale_item_key = fs.sale_item_key
              )
        """,
    ),

    # ----- Warnings (no bloquean) ---------------------------------------
    Check(
        category="quality",
        name="< 30% de productos tienen coste imputado",
        severity="warning",
        sql="""
            SELECT
                ROUND(100.0 * SUM(CASE WHEN cost_was_imputed THEN 1 ELSE 0 END)
                     / COUNT(*), 1)::INT AS actual,
                30 AS expected
            FROM dwh.dim_product
        """,
    ),
    Check(
        category="quality",
        name="tasa de devolución global < 15 %",
        severity="warning",
        sql="""
            SELECT
                ROUND(100.0 *
                    (SELECT COUNT(*) FROM dwh.fact_returns)::NUMERIC
                    / NULLIF((SELECT COUNT(*) FROM dwh.fact_sales), 0), 1)::INT
                                                          AS actual,
                15                                        AS expected
        """,
    ),
]


# ----------------------------------------------------------------------------
#  Runner
# ----------------------------------------------------------------------------
def run_check(conn, check: Check) -> tuple[bool, int, int]:
    """Ejecuta un check y devuelve (passed, actual, expected)."""
    with conn.cursor() as cur:
        cur.execute(check.sql)
        row = cur.fetchone()
    actual, expected = int(row[0] or 0), int(row[1] or 0)

    # Reglas:
    #   · severity error: actual debe coincidir con expected o superarlo
    #     (depende del check; usamos comparación >= para counts mínimos
    #     y == para integrity/business).
    #
    # En la práctica, expected en counts es el VALOR MÍNIMO esperado
    # (>=) y en integrity/business es 0 (debe ser exacto).
    if check.category == "counts":
        passed = actual >= expected
    elif check.severity == "warning":
        passed = actual <= expected
    else:
        passed = actual == expected

    return passed, actual, expected


def main() -> int:
    print("=" * 70)
    print("Validate · Calidad de datos del DWH")
    print("=" * 70)

    by_cat: dict[str, list[tuple[Check, bool, int, int]]] = {}
    n_errors   = 0
    n_warnings = 0

    with config.connect_dwh() as conn:
        for check in CHECKS:
            passed, actual, expected = run_check(conn, check)
            by_cat.setdefault(check.category, []).append(
                (check, passed, actual, expected)
            )
            if not passed:
                if check.severity == "error":
                    n_errors += 1
                else:
                    n_warnings += 1

    # Imprimir resultado por categoría
    for cat, results in by_cat.items():
        print(f"\n  [{cat.upper()}]")
        for check, passed, actual, expected in results:
            status = "✓" if passed else ("⚠" if check.severity == "warning" else "✗")
            line = f"    {status} {check.name}"
            if not passed:
                line += f"   (actual={actual:,} / expected={expected:,})"
            print(line)

    # Resumen final
    n_total = len(CHECKS)
    n_pass  = sum(1 for results in by_cat.values()
                  for _, p, _, _ in results if p)
    print()
    print("=" * 70)
    if n_errors:
        print(f"FALLO · {n_errors} error(es) crítico(s) · "
              f"{n_warnings} warning(s) · {n_pass}/{n_total} OK")
        return 1
    if n_warnings:
        print(f"OK con avisos · {n_warnings} warning(s) · {n_pass}/{n_total} OK")
    else:
        print(f"OK · {n_total}/{n_total} checks pasados.")
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
