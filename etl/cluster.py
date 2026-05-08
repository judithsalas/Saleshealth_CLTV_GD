"""
Segmentación de clientes con K-Means + triple validación de K.

Genera la tabla `marts.customer_segments` con la asignación de cada cliente
a un cluster. Sigue un proceso riguroso:

  1. Construir features sobre marts.customer_lifetime_value (8 variables)
  2. Estandarizar con StandardScaler
  3. Reducir dimensionalidad con PCA (preservando 95% varianza)
  4. Para K = 2..10, calcular tres métricas:
       · Inertia (para Elbow)
       · Silhouette Score
       · Davies-Bouldin Index
  5. Elegir K óptimo combinando las tres métricas
  6. Entrenar K-Means definitivo con el K óptimo
  7. Calcular UMAP 2D para visualización en el dashboard
  8. Caracterizar y nombrar cada cluster
  9. Persistir en marts.customer_segments

Las decisiones intermedias (K probado, métricas, K óptimo) también se
guardan en data/exports/cluster_metrics.csv para incluir en el documento
técnico.

Uso:
    python -m etl.cluster
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd
import psycopg
import umap
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import (
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.preprocessing import StandardScaler

from etl import config

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)


# ----------------------------------------------------------------------------
#  Configuración
# ----------------------------------------------------------------------------
FEATURES = [
    "num_orders",
    "num_units",
    "revenue_total",
    "margin_total",
    "avg_order_value",
    "alive_probability",
    "expected_purchases_12m",
    "cltv_predicted_12m",
]

K_RANGE = list(range(2, 11))           # K = 2..10
RANDOM_STATE = 42


# ----------------------------------------------------------------------------
#  DDL
# ----------------------------------------------------------------------------
SQL_DDL = """
DROP TABLE IF EXISTS marts.customer_segments CASCADE;

CREATE TABLE marts.customer_segments (
    customer_key      INTEGER       PRIMARY KEY
                                    REFERENCES dwh.dim_customer(customer_key),
    cluster_id        SMALLINT      NOT NULL,
    cluster_name      VARCHAR(40)   NOT NULL,
    pca_x             NUMERIC(10,6),
    pca_y             NUMERIC(10,6),
    umap_x            NUMERIC(10,6),
    umap_y            NUMERIC(10,6),
    snapshot_date     DATE          NOT NULL,
    loaded_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_segments_cluster ON marts.customer_segments (cluster_id);

COMMENT ON TABLE marts.customer_segments
  IS 'Asignación de cluster por cliente · K-Means con triple validación de K';
"""


SQL_LOAD_BASE = """
SELECT
    customer_key,
    customer_id,
    full_name,
    num_orders,
    num_units,
    revenue_total,
    margin_total,
    avg_order_value,
    alive_probability,
    expected_purchases_12m,
    cltv_historic,
    cltv_predicted_12m,
    snapshot_date
FROM marts.customer_lifetime_value
WHERE num_orders > 0;
"""


# ----------------------------------------------------------------------------
#  Selección de K
# ----------------------------------------------------------------------------
def evaluate_k(X: np.ndarray, k_range: list[int]) -> pd.DataFrame:
    """Para cada K, devuelve inercia, silhouette y Davies-Bouldin."""
    results = []
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE)
        labels = km.fit_predict(X)
        results.append(
            {
                "k": k,
                "inertia": float(km.inertia_),
                "silhouette": float(silhouette_score(X, labels)),
                "davies_bouldin": float(davies_bouldin_score(X, labels)),
            }
        )
    return pd.DataFrame(results)


def select_optimal_k(metrics: pd.DataFrame) -> int:
    """
    Combina las tres métricas con un score normalizado.

    · Silhouette: cuanto mayor, mejor → normalizar y pesar +1.
    · Davies-Bouldin: cuanto menor, mejor → normalizar invirtiendo y pesar +1.
    · Elbow (inertia): se penaliza la K que reduce poco la inercia.
        Calculamos la "ganancia marginal" de pasar de K-1 a K. Donde la
        ganancia se aplana, ahí está el codo.

    Pesos: 0.5 silhouette + 0.3 Davies-Bouldin + 0.2 elbow.

    Devuelve la K con score más alto.
    """
    m = metrics.copy().sort_values("k").reset_index(drop=True)

    # Normalizar silhouette (más alto = mejor)
    sil_min, sil_max = m["silhouette"].min(), m["silhouette"].max()
    m["sil_norm"] = (m["silhouette"] - sil_min) / (sil_max - sil_min + 1e-9)

    # Normalizar Davies-Bouldin invertido (más bajo = mejor)
    db_min, db_max = m["davies_bouldin"].min(), m["davies_bouldin"].max()
    m["db_norm"] = 1 - (m["davies_bouldin"] - db_min) / (db_max - db_min + 1e-9)

    # Elbow: ganancia marginal = (inercia[k-1] - inercia[k]) / inercia[k-1]
    m["delta_inertia"] = m["inertia"].diff(-1) / m["inertia"]
    m["delta_inertia"] = m["delta_inertia"].fillna(0)
    # Normalizar delta_inertia (más alto = más codo aquí)
    di_min, di_max = m["delta_inertia"].min(), m["delta_inertia"].max()
    m["elbow_norm"] = (m["delta_inertia"] - di_min) / (di_max - di_min + 1e-9)

    # Score combinado
    m["score"] = 0.5 * m["sil_norm"] + 0.3 * m["db_norm"] + 0.2 * m["elbow_norm"]

    optimal_k = int(m.loc[m["score"].idxmax(), "k"])
    return optimal_k


# ----------------------------------------------------------------------------
#  Naming heurístico de clusters
# ----------------------------------------------------------------------------
def name_clusters(df: pd.DataFrame, cluster_col: str = "cluster_id") -> dict[int, str]:
    """
    Asigna un nombre a cada cluster basado en el perfil de sus clientes.

    Reglas (orden de prioridad):
      1. Top CLTV predicho + alive alta  → "Champions"
      2. Frequency alta + recurrente     → "Recurrentes leales"
      3. Alive alta + bajo CLTV          → "Nuevos prometedores"
      4. Alive baja                      → "En riesgo de churn"
      5. Resto                            → "Ocasionales"
    """
    # Centroides en escala original
    profiles = (
        df.groupby(cluster_col)
        .agg(
            n=("customer_key", "count"),
            cltv_pred=("cltv_predicted_12m", "mean"),
            num_orders=("num_orders", "mean"),
            alive=("alive_probability", "mean"),
            margin=("margin_total", "mean"),
        )
        .sort_values("cltv_pred", ascending=False)
    )

    n_clusters = len(profiles)
    names: dict[int, str] = {}
    used = set()

    # 1. Champions: cluster con MAYOR CLTV predicho
    top = profiles.iloc[0]
    names[top.name] = "Champions"
    used.add(top.name)

    # Resto
    remaining = profiles.drop(index=list(used))

    # 2. En riesgo: cluster con MENOR alive_probability entre los que quedan
    if len(remaining) > 0:
        risk = remaining["alive"].idxmin()
        names[risk] = "En riesgo de churn"
        used.add(risk)
        remaining = remaining.drop(index=risk)

    # 3. Recurrentes leales: cluster con mayor num_orders del resto
    if len(remaining) > 0:
        loyal = remaining["num_orders"].idxmax()
        names[loyal] = "Recurrentes leales"
        used.add(loyal)
        remaining = remaining.drop(index=loyal)

    # 4. Nuevos prometedores: cluster con mayor alive del resto (si k≥4)
    if len(remaining) > 0:
        promising = remaining["alive"].idxmax()
        names[promising] = "Nuevos prometedores"
        used.add(promising)
        remaining = remaining.drop(index=promising)

    # 5. Resto: ocasionales
    for cid in remaining.index:
        names[cid] = "Ocasionales"

    return names


# ----------------------------------------------------------------------------
#  Main
# ----------------------------------------------------------------------------
def main() -> int:
    print("=" * 70)
    print("Cluster · K-Means + triple validación + UMAP")
    print("=" * 70)

    # 1. DDL
    print("[1/7] Creando marts.customer_segments...")
    with config.connect_dwh() as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS marts")
        cur.execute(SQL_DDL)
        conn.commit()

    # 2. Cargar datos
    print("[2/7] Cargando datos desde marts.customer_lifetime_value...")
    with config.connect_dwh() as conn:
        df = pd.read_sql(SQL_LOAD_BASE, conn)
    print(f"      · {len(df):,} clientes con compras")

    if len(df) < 20:
        print("ERROR: muy pocos clientes para clusterizar.", file=sys.stderr)
        return 1

    # 3. Preparar features
    X_raw = df[FEATURES].fillna(0).values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_raw)

    # 4. PCA preservando 95% varianza
    print("[3/7] PCA (95% varianza)...")
    pca = PCA(n_components=0.95, random_state=RANDOM_STATE)
    X_pca = pca.fit_transform(X_scaled)
    print(f"      · {pca.n_components_} componentes "
          f"(varianza explicada: {pca.explained_variance_ratio_.sum():.1%})")

    # 5. Evaluar K = 2..10
    print(f"[4/7] Evaluando K = {K_RANGE[0]}..{K_RANGE[-1]}...")
    metrics = evaluate_k(X_pca, K_RANGE)
    for _, row in metrics.iterrows():
        print(f"      K={int(row['k']):>2}: "
              f"inercia={row['inertia']:>10,.0f}  "
              f"silhouette={row['silhouette']:.3f}  "
              f"davies-bouldin={row['davies_bouldin']:.3f}")

    optimal_k = select_optimal_k(metrics)
    print(f"      → K óptimo = {optimal_k}")

    # Exportar métricas para el documento
    config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = config.EXPORTS_DIR / "cluster_metrics.csv"
    metrics["optimal"] = metrics["k"] == optimal_k
    metrics.to_csv(metrics_path, index=False)
    print(f"      · métricas guardadas en {metrics_path.relative_to(config.PROJECT_ROOT)}")

    # 6. Entrenar K-Means definitivo
    print(f"[5/7] Entrenando K-Means con K={optimal_k}...")
    km = KMeans(n_clusters=optimal_k, n_init=20, random_state=RANDOM_STATE)
    df["cluster_id"] = km.fit_predict(X_pca)

    # 7. PCA 2D para scatter (usar las 2 primeras componentes)
    df["pca_x"] = X_pca[:, 0]
    df["pca_y"] = X_pca[:, 1] if X_pca.shape[1] > 1 else 0

    # 8. UMAP 2D (mejor visualización para clusters)
    print("[6/7] Calculando UMAP 2D...")
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=min(15, len(df) - 1),
        min_dist=0.1,
        random_state=RANDOM_STATE,
    )
    X_umap = reducer.fit_transform(X_scaled)
    df["umap_x"] = X_umap[:, 0]
    df["umap_y"] = X_umap[:, 1]

    # 9. Naming
    cluster_names = name_clusters(df)
    df["cluster_name"] = df["cluster_id"].map(cluster_names)

    # 10. Insert
    print("[7/7] Insertando en marts.customer_segments...")
    cols = ["customer_key", "cluster_id", "cluster_name",
            "pca_x", "pca_y", "umap_x", "umap_y", "snapshot_date"]
    rows = [tuple(r) for r in df[cols].itertuples(index=False, name=None)]

    with config.connect_dwh() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE marts.customer_segments")
        cur.executemany(
            f"INSERT INTO marts.customer_segments ({', '.join(cols)}) "
            f"VALUES ({', '.join(['%s'] * len(cols))})",
            rows,
        )
        conn.commit()
    print(f"      · {len(rows):,} clientes asignados")

    # Resumen por cluster
    print()
    print(f"  Resumen ({optimal_k} clusters):")
    summary = (
        df.groupby(["cluster_id", "cluster_name"])
        .agg(
            n=("customer_key", "count"),
            cltv_avg=("cltv_predicted_12m", "mean"),
            margin_avg=("margin_total", "mean"),
            alive_avg=("alive_probability", "mean"),
        )
        .reset_index()
        .sort_values("cltv_avg", ascending=False)
    )
    for _, r in summary.iterrows():
        print(f"    [{int(r['cluster_id'])}] {r['cluster_name']:<24} "
              f"n={int(r['n']):>5,}  "
              f"CLTV12m={r['cltv_avg']:>8,.0f}€  "
              f"alive={r['alive_avg']:.2f}")

    print()
    print("=" * 70)
    print("OK · clustering aplicado.")
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
