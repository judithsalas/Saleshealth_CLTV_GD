"""
Bootstrap de la base de datos del proyecto.

Crea la BD `saleshealth_cltv` (eliminándola primero si existía) y ejecuta
el DDL completo en `etl/schema.sql`. Pensado para ejecutarse una sola vez
al principio del proyecto, o cada vez que se quiera resetear todo.

Uso:
    python -m etl.bootstrap
"""
from __future__ import annotations

import sys

import psycopg

from etl import config


def database_exists(name: str) -> bool:
    """Devuelve True si la BD existe en el servidor."""
    with config.connect_admin() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (name,),
        )
        return cur.fetchone() is not None


def drop_database_if_exists(name: str) -> None:
    """Elimina la BD si existe. Cierra primero conexiones activas."""
    if not database_exists(name):
        return

    with config.connect_admin() as conn, conn.cursor() as cur:
        # Cerrar conexiones activas a esa BD para poder eliminarla
        cur.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (name,),
        )
        cur.execute(f'DROP DATABASE "{name}"')
    print(f"  · BD '{name}' eliminada")


def create_database(name: str) -> None:
    """Crea la BD con encoding UTF-8."""
    with config.connect_admin() as conn, conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}" ENCODING \'UTF8\'')
    print(f"  · BD '{name}' creada")


def execute_schema_file(database: str, schema_file) -> None:
    """Ejecuta el contenido del archivo SQL en la BD indicada."""
    sql = schema_file.read_text(encoding="utf-8")
    with config.connect(database) as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
    print(f"  · DDL aplicado ({len(sql):,} caracteres)")


def verify_schema(database: str) -> None:
    """Verifica que las tablas esperadas existen y muestra resumen."""
    with config.connect(database) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema IN ('stg', 'dwh', 'marts')
            ORDER BY table_schema, table_name
            """
        )
        tables = cur.fetchall()

    print(f"\n  Tablas creadas ({len(tables)}):")
    current_schema = None
    for schema, table in tables:
        if schema != current_schema:
            print(f"    [{schema}]")
            current_schema = schema
        print(f"      · {table}")


def main() -> int:
    print("=" * 70)
    print("Bootstrap · Saleshealth CLTV")
    print("=" * 70)
    print(f"  servidor : {config.DB_HOST}:{config.DB_PORT}")
    print(f"  usuario  : {config.DB_USER}")
    print(f"  BD       : {config.DB_NAME_DWH}")
    print()

    # 1. Verificar que la BD origen existe (no la tocamos, solo verificamos)
    print("[1/4] Verificando BD origen...")
    if not database_exists(config.DB_NAME_SOURCE):
        print(
            f"  ERROR · la BD origen '{config.DB_NAME_SOURCE}' no existe.\n"
            "  El proyecto necesita esa BD con los datos cargados."
        )
        return 1
    print(f"  · BD '{config.DB_NAME_SOURCE}' encontrada")

    # 2. Drop + create de la BD destino
    print("\n[2/4] Recreando BD destino...")
    drop_database_if_exists(config.DB_NAME_DWH)
    create_database(config.DB_NAME_DWH)

    # 3. Ejecutar DDL
    print("\n[3/4] Aplicando DDL...")
    execute_schema_file(config.DB_NAME_DWH, config.SCHEMA_FILE)

    # 4. Verificación
    print("\n[4/4] Verificación")
    verify_schema(config.DB_NAME_DWH)

    print()
    print("=" * 70)
    print("OK · BD lista para el ETL.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except psycopg.OperationalError as exc:
        print(f"\nERROR de conexión: {exc}", file=sys.stderr)
        print(
            "\n  · ¿Está PostgreSQL en marcha?\n"
            "  · ¿Las credenciales del .env son correctas?\n",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"\nERROR inesperado: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
