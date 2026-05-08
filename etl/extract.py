"""
Extracción del origen al staging.

Para cada tabla del origen `saleshealth` que necesitamos, copia su contenido
al schema `stg` de la BD destino `saleshealth_cltv`. La tabla destino se
crea automáticamente con la misma estructura.

Notas de diseño:
  · No usamos pandas para la copia: streaming con `COPY ... TO STDOUT` y
    `COPY ... FROM STDIN` es órdenes de magnitud más rápido y no consume
    memoria.
  · Las tablas de stg se crean clonando la estructura de origen
    (CREATE TABLE LIKE) — no es modelo dimensional aún, eso viene en
    el transform.

Uso:
    python -m etl.extract
"""
from __future__ import annotations

import sys
import time

import psycopg

from etl import config

# ----------------------------------------------------------------------------
# Tablas del origen que necesitamos copiar
# Orden importa: tablas con FKs van después de sus referenciadas
# ----------------------------------------------------------------------------
TABLES_TO_EXTRACT: list[str] = [
    # Catálogos básicos
    "category",
    "brand",
    "central_product",
    "product",
    "product_offer",
    "offer",
    "return_reason",
    "city_zone",
    "store",
    # Datos transaccionales
    "customer",
    "sale",
    "sale_item",
    "return_item",
]


def get_columns_from_source(table: str) -> list[tuple[str, str]]:
    """Devuelve [(nombre_columna, tipo_postgres)] de la tabla en origen."""
    with config.connect_source() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, character_maximum_length,
                   numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        rows = cur.fetchall()

    columns = []
    for name, dtype, char_len, num_prec, num_scale in rows:
        if dtype == "character varying" and char_len:
            full_type = f"VARCHAR({char_len})"
        elif dtype == "character" and char_len:
            full_type = f"CHAR({char_len})"
        elif dtype == "numeric" and num_prec:
            full_type = f"NUMERIC({num_prec},{num_scale or 0})"
        else:
            full_type = dtype.upper()
        columns.append((name, full_type))
    return columns


def create_stg_table(dwh_conn: psycopg.Connection, table: str,
                     columns: list[tuple[str, str]]) -> None:
    """Crea (o recrea) la tabla en stg con la misma estructura que en origen."""
    cols_sql = ",\n    ".join(f'"{n}" {t}' for n, t in columns)
    ddl = (
        f"DROP TABLE IF EXISTS stg.{table} CASCADE;\n"
        f"CREATE TABLE stg.{table} (\n    {cols_sql}\n);"
    )
    with dwh_conn.cursor() as cur:
        cur.execute(ddl)
    dwh_conn.commit()


def copy_table_data(table: str) -> int:
    """
    Copia los datos del origen a stg usando COPY ... TO/FROM STDOUT.

    Returns:
        Número de filas copiadas.
    """
    with config.connect_source() as src, config.connect_dwh() as dst:
        # Contar filas en origen
        with src.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM public.{table}")
            row_count = cur.fetchone()[0]

        # COPY origen → memoria → COPY destino, en streaming
        with src.cursor() as src_cur, dst.cursor() as dst_cur:
            with src_cur.copy(f"COPY public.{table} TO STDOUT") as src_copy:
                with dst_cur.copy(f"COPY stg.{table} FROM STDIN") as dst_copy:
                    for chunk in src_copy:
                        dst_copy.write(chunk)
        dst.commit()

    return row_count


def extract_table(table: str) -> tuple[int, float]:
    """Extracción completa de una tabla. Devuelve (filas, segundos)."""
    t0 = time.perf_counter()

    columns = get_columns_from_source(table)
    with config.connect_dwh() as dwh:
        create_stg_table(dwh, table, columns)

    n_rows = copy_table_data(table)

    elapsed = time.perf_counter() - t0
    return n_rows, elapsed


def main() -> int:
    print("=" * 70)
    print("Extract · Saleshealth CLTV")
    print("=" * 70)
    print(f"  origen  : {config.DB_NAME_SOURCE}")
    print(f"  destino : {config.DB_NAME_DWH} (schema stg)")
    print()

    total_rows = 0
    total_time = 0.0

    for i, table in enumerate(TABLES_TO_EXTRACT, 1):
        try:
            n_rows, elapsed = extract_table(table)
            total_rows += n_rows
            total_time += elapsed
            print(
                f"  [{i:2d}/{len(TABLES_TO_EXTRACT)}] {table:<20} "
                f"{n_rows:>8,} filas · {elapsed:>5.2f}s"
            )
        except Exception as exc:                                  # noqa: BLE001
            print(f"  [FAIL] {table}: {exc}")
            return 1

    print()
    print(f"  Total   : {total_rows:,} filas en {total_time:.2f}s")
    print("=" * 70)
    print("OK · staging poblado.")
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
