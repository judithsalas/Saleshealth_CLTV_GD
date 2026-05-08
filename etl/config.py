"""
Configuración central del proyecto Saleshealth CLTV.

Lee variables de entorno desde `.env` (raíz del proyecto) y expone:
  - constantes de conexión (DB_HOST, DB_PORT, etc.)
  - función `connect()` para abrir una conexión a una BD concreta
  - función `connect_source()` y `connect_dwh()` como atajos
  - rutas absolutas del proyecto (PROJECT_ROOT, ETL_DIR, etc.)
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ETL_DIR      = PROJECT_ROOT / "etl"
APP_DIR      = PROJECT_ROOT / "app"
DATA_DIR     = PROJECT_ROOT / "data"
DOCS_DIR     = PROJECT_ROOT / "docs"

EXPORTS_DIR  = DATA_DIR / "exports"
SCHEMA_FILE  = ETL_DIR  / "schema.sql"

# Cargar .env desde la raíz del proyecto
load_dotenv(PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Variables de conexión
# ---------------------------------------------------------------------------
DB_HOST          = os.getenv("DB_HOST", "localhost")
DB_PORT          = int(os.getenv("DB_PORT", "5432"))
DB_USER          = os.getenv("DB_USER", "postgres")
DB_PASSWORD      = os.getenv("DB_PASSWORD", "")
DB_NAME_SOURCE   = os.getenv("DB_NAME_SOURCE", "saleshealth")
DB_NAME_DWH      = os.getenv("DB_NAME_DWH", "saleshealth_cltv")


# ---------------------------------------------------------------------------
# Helpers de conexión
# ---------------------------------------------------------------------------
def _conninfo(database: str) -> str:
    """Construye la cadena de conexión psycopg para una BD concreta."""
    return (
        f"host={DB_HOST} port={DB_PORT} "
        f"user={DB_USER} password={DB_PASSWORD} dbname={database}"
    )


def connect(database: str) -> psycopg.Connection:
    """
    Abre una conexión a la BD indicada.

    Args:
        database: nombre de la BD (ej. 'saleshealth' o 'saleshealth_cltv').

    Returns:
        Una conexión psycopg activa. Recordar cerrarla con `.close()`
        o usar como context manager (`with connect(...) as conn:`).
    """
    if not DB_PASSWORD:
        raise RuntimeError(
            "DB_PASSWORD vacía. Comprueba que .env existe en la raíz del "
            "proyecto y contiene la variable DB_PASSWORD con la contraseña "
            "real de Postgres."
        )
    return psycopg.connect(_conninfo(database))


def connect_source() -> psycopg.Connection:
    """Conexión a la BD origen (saleshealth). Solo lectura."""
    return connect(DB_NAME_SOURCE)


def connect_dwh() -> psycopg.Connection:
    """Conexión a la BD destino (saleshealth_cltv). Lectura y escritura."""
    return connect(DB_NAME_DWH)


def connect_admin() -> psycopg.Connection:
    """
    Conexión a la BD 'postgres' del servidor (BD administrativa por defecto).

    Útil para operaciones que requieren AUTOCOMMIT y no pueden ejecutarse
    dentro de una transacción, como CREATE DATABASE o DROP DATABASE.
    """
    conn = psycopg.connect(_conninfo("postgres"))
    conn.autocommit = True
    return conn
