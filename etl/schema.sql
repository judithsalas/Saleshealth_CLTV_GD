-- ============================================================================
--  Saleshealth CLTV — Modelo dimensional
--  Proyecto Final · Gestión de Datos · UAX 2025/26
-- ----------------------------------------------------------------------------
--  Arquitectura por capas (Kimball + medallion):
--    stg    →  staging, copia 1:1 del origen tras extract
--    dwh    →  data warehouse, modelo en estrella con SK
--    marts  →  capa analítica, agregados pre-calculados (CLTV, segmentos)
--
--  Modelo en estrella:
--    4 dimensiones:  dim_customer, dim_product, dim_location, dim_date
--    2 hechos:       fact_sales, fact_returns
-- ============================================================================


-- ----------------------------------------------------------------------------
--  Schemas
-- ----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS dwh;
CREATE SCHEMA IF NOT EXISTS marts;

COMMENT ON SCHEMA stg   IS 'Staging — copia bruta del origen tras extracción';
COMMENT ON SCHEMA dwh   IS 'Data Warehouse — modelo en estrella con surrogate keys';
COMMENT ON SCHEMA marts IS 'Marts analíticos — agregados pre-calculados para el dashboard';


-- ============================================================================
--  DIMENSIONES
-- ============================================================================

-- ----------------------------------------------------------------------------
--  dim_date — dimensión temporal sintética
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS dwh.dim_date CASCADE;
CREATE TABLE dwh.dim_date (
    date_key            INTEGER       PRIMARY KEY,        -- formato YYYYMMDD
    full_date           DATE          NOT NULL UNIQUE,
    year                SMALLINT      NOT NULL,
    quarter             SMALLINT      NOT NULL,
    month               SMALLINT      NOT NULL,
    month_name          VARCHAR(12)   NOT NULL,
    week_of_year        SMALLINT      NOT NULL,
    day_of_month        SMALLINT      NOT NULL,
    day_of_week         SMALLINT      NOT NULL,            -- 1=Mon, 7=Sun
    day_name            VARCHAR(12)   NOT NULL,
    is_weekend          BOOLEAN       NOT NULL,
    year_month          CHAR(7)       NOT NULL             -- 'YYYY-MM'
);

CREATE INDEX idx_dim_date_year_month ON dwh.dim_date (year_month);
CREATE INDEX idx_dim_date_year       ON dwh.dim_date (year);

COMMENT ON TABLE dwh.dim_date IS 'Dimensión temporal sintética — calendario completo';


-- ----------------------------------------------------------------------------
--  dim_customer — clientes (SCD Type 1)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS dwh.dim_customer CASCADE;
CREATE TABLE dwh.dim_customer (
    customer_key        SERIAL        PRIMARY KEY,         -- surrogate key
    customer_id         INTEGER       NOT NULL UNIQUE,     -- natural key (origen)
    full_name           VARCHAR(310)  NOT NULL,
    email               VARCHAR(150),
    phone               VARCHAR(20),
    signup_date         DATE          NOT NULL,
    signup_year         SMALLINT      NOT NULL,
    signup_month        CHAR(7)       NOT NULL,            -- 'YYYY-MM' cohorte
    loaded_at           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_dim_customer_id     ON dwh.dim_customer (customer_id);
CREATE INDEX idx_dim_customer_cohort ON dwh.dim_customer (signup_year, signup_month);

COMMENT ON TABLE  dwh.dim_customer             IS 'Dimensión cliente — SCD Type 1';
COMMENT ON COLUMN dwh.dim_customer.customer_key IS 'Surrogate key autogenerada';
COMMENT ON COLUMN dwh.dim_customer.customer_id  IS 'Natural key del sistema origen';


-- ----------------------------------------------------------------------------
--  dim_product — productos enriquecidos con marca y categoría
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS dwh.dim_product CASCADE;
CREATE TABLE dwh.dim_product (
    product_key         SERIAL         PRIMARY KEY,
    product_id          INTEGER        NOT NULL UNIQUE,
    product_name        VARCHAR(200)   NOT NULL,
    sku                 VARCHAR(50),
    barcode             VARCHAR(50),
    category_name       VARCHAR(100),
    brand_name          VARCHAR(150),
    manufacturer        VARCHAR(150),
    unit_price          NUMERIC(10, 2) NOT NULL,
    unit_cost           NUMERIC(10, 2),
    margin_pct          NUMERIC(5, 2),                     -- (price - cost) / price * 100
    cost_was_imputed    BOOLEAN        NOT NULL DEFAULT FALSE,
    loaded_at           TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_dim_product_id        ON dwh.dim_product (product_id);
CREATE INDEX idx_dim_product_category  ON dwh.dim_product (category_name);
CREATE INDEX idx_dim_product_brand     ON dwh.dim_product (brand_name);

COMMENT ON TABLE  dwh.dim_product               IS 'Dimensión producto enriquecida con jerarquía categoría → marca';
COMMENT ON COLUMN dwh.dim_product.cost_was_imputed IS 'TRUE cuando unit_cost se estimó por falta de dato en origen';


-- ----------------------------------------------------------------------------
--  dim_location — punto de venta (tienda + zona geográfica)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS dwh.dim_location CASCADE;
CREATE TABLE dwh.dim_location (
    location_key        SERIAL         PRIMARY KEY,
    store_id            INTEGER        NOT NULL UNIQUE,
    store_name          VARCHAR(100)   NOT NULL,
    address             VARCHAR(200),
    postal_code         VARCHAR(10),
    district            VARCHAR(100),
    city                VARCHAR(100)   NOT NULL DEFAULT 'Madrid',
    area_type           VARCHAR(20),                        -- Céntrica · Periférica
    zone_orientation    VARCHAR(20),                        -- Norte · Sur · etc.
    latitude            NUMERIC(9, 6),
    longitude           NUMERIC(9, 6),
    opened_date         DATE,
    loaded_at           TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_dim_location_id       ON dwh.dim_location (store_id);
CREATE INDEX idx_dim_location_district ON dwh.dim_location (district);

COMMENT ON TABLE dwh.dim_location IS 'Dimensión punto de venta · combina tienda + atributos geográficos';


-- ============================================================================
--  HECHOS
-- ============================================================================

-- ----------------------------------------------------------------------------
--  fact_sales — grano: 1 línea de venta (sale_item)
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS dwh.fact_sales CASCADE;
CREATE TABLE dwh.fact_sales (
    sale_item_key       BIGSERIAL      PRIMARY KEY,
    sale_id             INTEGER        NOT NULL,
    sale_item_id        INTEGER        NOT NULL UNIQUE,

    -- Foreign keys hacia dimensiones
    customer_key        INTEGER        NOT NULL REFERENCES dwh.dim_customer  (customer_key),
    product_key         INTEGER        NOT NULL REFERENCES dwh.dim_product   (product_key),
    location_key        INTEGER        NOT NULL REFERENCES dwh.dim_location  (location_key),
    date_key            INTEGER        NOT NULL REFERENCES dwh.dim_date      (date_key),

    -- Atributos del hecho
    sale_timestamp      TIMESTAMP      NOT NULL,
    quantity            INTEGER        NOT NULL CHECK (quantity > 0),
    unit_price          NUMERIC(10, 2) NOT NULL,
    unit_cost           NUMERIC(10, 2),

    -- Medidas (pre-calculadas en el ETL)
    gross_amount        NUMERIC(12, 2) NOT NULL,            -- quantity * unit_price
    discount_amount     NUMERIC(12, 2) NOT NULL DEFAULT 0,
    net_amount          NUMERIC(12, 2) NOT NULL,            -- gross - discount
    cost_amount         NUMERIC(12, 2),                     -- quantity * unit_cost
    margin_amount       NUMERIC(12, 2),                     -- net - cost

    -- Flags
    has_discount        BOOLEAN        NOT NULL DEFAULT FALSE,
    is_returned         BOOLEAN        NOT NULL DEFAULT FALSE,

    loaded_at           TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fact_sales_customer  ON dwh.fact_sales (customer_key);
CREATE INDEX idx_fact_sales_product   ON dwh.fact_sales (product_key);
CREATE INDEX idx_fact_sales_location  ON dwh.fact_sales (location_key);
CREATE INDEX idx_fact_sales_date      ON dwh.fact_sales (date_key);
CREATE INDEX idx_fact_sales_sale      ON dwh.fact_sales (sale_id);

COMMENT ON TABLE dwh.fact_sales IS 'Hecho transaccional · grano: 1 línea de venta';


-- ----------------------------------------------------------------------------
--  fact_returns — grano: 1 línea de devolución
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS dwh.fact_returns CASCADE;
CREATE TABLE dwh.fact_returns (
    return_key          BIGSERIAL      PRIMARY KEY,
    return_id           INTEGER        NOT NULL UNIQUE,
    sale_item_id        INTEGER        NOT NULL,
    sale_item_key       BIGINT         NOT NULL REFERENCES dwh.fact_sales    (sale_item_key),

    -- FKs heredadas (denormalizadas para facilitar análisis sin joins)
    customer_key        INTEGER        NOT NULL REFERENCES dwh.dim_customer  (customer_key),
    product_key         INTEGER        NOT NULL REFERENCES dwh.dim_product   (product_key),
    location_key        INTEGER        NOT NULL REFERENCES dwh.dim_location  (location_key),
    date_key            INTEGER        NOT NULL REFERENCES dwh.dim_date      (date_key),

    -- Atributos
    return_timestamp    TIMESTAMP      NOT NULL,
    sale_timestamp      TIMESTAMP      NOT NULL,
    days_to_return      INTEGER        NOT NULL,
    return_reason       VARCHAR(100),
    quantity_returned   INTEGER        NOT NULL CHECK (quantity_returned > 0),

    -- Medidas
    refund_amount       NUMERIC(12, 2) NOT NULL,
    cost_recovered      NUMERIC(12, 2),
    margin_lost         NUMERIC(12, 2),

    loaded_at           TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fact_returns_customer ON dwh.fact_returns (customer_key);
CREATE INDEX idx_fact_returns_product  ON dwh.fact_returns (product_key);
CREATE INDEX idx_fact_returns_date     ON dwh.fact_returns (date_key);

COMMENT ON TABLE dwh.fact_returns IS 'Hecho de devoluciones · referencia a fact_sales por sale_item_key';


-- ============================================================================
--  MARTS · se poblarán en días posteriores (CLTV, segmentos, agregados)
-- ============================================================================

-- Placeholder vacío en este día. Los marts se crean en los días 4 y 5
-- cuando ya tengamos las métricas calculadas.

-- Fin del DDL.
