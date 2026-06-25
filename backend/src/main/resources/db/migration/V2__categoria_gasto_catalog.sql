-- =============================================================================
-- V2__categoria_gasto_catalog.sql
-- Catálogo de categorías de gasto con reglas de deducibilidad por régimen fiscal
-- y tabla de sobreescrituras por usuario.
--
-- Decisiones de diseño:
--   - Dos niveles: GrupoCategoriaGasto (agrupación para dashboard) + CategoriaGasto (reglas fiscales)
--   - ReglasDeducibilidad separada: permite porcentajes distintos por régimen fiscal sin tocar código
--   - PreferenciaDeducibilidadUsuario: el usuario sobreescribe el % del catálogo para su cuenta
--   - Sin flag requiere_aviso_hacienda: las alertas las gestiona la capa de servicio
--   - codigo en snake_case, sincronizado con CategoriaGasto enum del servicio Python
-- =============================================================================

-- ── Tipos ENUM ────────────────────────────────────────────────────────────────

CREATE TYPE regimen_fiscal AS ENUM (
    'estimacion_directa_simplificada',
    'estimacion_directa_normal',
    'estimacion_objetiva_modulos'
);

-- ── Tabla de grupos (nivel 1 — para el dashboard) ────────────────────────────

CREATE TABLE grupos_categoria_gasto (
    id               UUID        NOT NULL DEFAULT gen_random_uuid(),
    codigo           VARCHAR(60) NOT NULL,
    nombre_display   VARCHAR(120) NOT NULL,
    orden_dashboard  SMALLINT    NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_grupos_categoria_gasto PRIMARY KEY (id),
    CONSTRAINT uq_grupos_categoria_gasto_codigo UNIQUE (codigo)
);

COMMENT ON TABLE  grupos_categoria_gasto              IS 'Agrupación visual de categorías para el dashboard (ej: "Gastos de vehículo").';
COMMENT ON COLUMN grupos_categoria_gasto.codigo       IS 'Identificador snake_case legible por código (ej: vehiculos).';
COMMENT ON COLUMN grupos_categoria_gasto.orden_dashboard IS 'Orden de aparición en el dashboard. Menor número = primero.';

-- ── Tabla de categorías (nivel 2 — reglas fiscales) ──────────────────────────

CREATE TABLE categorias_gasto (
    id             UUID        NOT NULL DEFAULT gen_random_uuid(),
    codigo         VARCHAR(60) NOT NULL,
    nombre_display VARCHAR(120) NOT NULL,
    grupo_id       UUID        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_categorias_gasto           PRIMARY KEY (id),
    CONSTRAINT uq_categorias_gasto_codigo    UNIQUE (codigo),
    CONSTRAINT fk_categorias_gasto_grupo     FOREIGN KEY (grupo_id)
        REFERENCES grupos_categoria_gasto (id) ON DELETE RESTRICT
);

COMMENT ON TABLE  categorias_gasto              IS 'Catálogo de categorías de gasto. El código debe coincidir con el enum CategoriaGasto del servicio Python.';
COMMENT ON COLUMN categorias_gasto.codigo       IS 'snake_case sincronizado con el enum categoria_sugerida del extraction schema (ej: software_suscripciones).';
COMMENT ON COLUMN categorias_gasto.grupo_id     IS 'Grupo al que pertenece la categoría para la agrupación visual del dashboard.';

-- ── Tabla de reglas de deducibilidad por régimen fiscal ──────────────────────

CREATE TABLE reglas_deducibilidad (
    id                    UUID           NOT NULL DEFAULT gen_random_uuid(),
    categoria_id          UUID           NOT NULL,
    regimen_fiscal        regimen_fiscal NOT NULL,
    pct_deducible_iva     NUMERIC(5, 2)  NOT NULL CHECK (pct_deducible_iva  BETWEEN 0 AND 100),
    pct_deducible_irpf    NUMERIC(5, 2)  NOT NULL CHECK (pct_deducible_irpf BETWEEN 0 AND 100),
    created_at            TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ    NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_reglas_deducibilidad PRIMARY KEY (id),
    CONSTRAINT uq_reglas_deducibilidad_categoria_regimen
        UNIQUE (categoria_id, regimen_fiscal),
    CONSTRAINT fk_reglas_deducibilidad_categoria
        FOREIGN KEY (categoria_id) REFERENCES categorias_gasto (id) ON DELETE CASCADE
);

COMMENT ON TABLE  reglas_deducibilidad                  IS 'Porcentajes de deducibilidad de IVA e IRPF por categoría y régimen fiscal. Una fila por combinación (categoría, régimen).';
COMMENT ON COLUMN reglas_deducibilidad.pct_deducible_iva  IS '% de IVA deducible. Ejemplo: 50 para vehículos en estimación directa.';
COMMENT ON COLUMN reglas_deducibilidad.pct_deducible_irpf IS '% de IRPF deducible. Ejemplo: 50 para vehículos en estimación directa.';

-- ── Tabla de sobreescrituras por usuario ─────────────────────────────────────

CREATE TABLE preferencias_deducibilidad_usuario (
    id                        UUID          NOT NULL DEFAULT gen_random_uuid(),
    usuario_id                UUID          NOT NULL,
    categoria_id              UUID          NOT NULL,
    pct_deducible_iva_override  NUMERIC(5, 2) NOT NULL CHECK (pct_deducible_iva_override  BETWEEN 0 AND 100),
    pct_deducible_irpf_override NUMERIC(5, 2) NOT NULL CHECK (pct_deducible_irpf_override BETWEEN 0 AND 100),
    created_at                TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_preferencias_deducibilidad_usuario PRIMARY KEY (id),
    CONSTRAINT uq_preferencias_deducibilidad_usuario_categoria
        UNIQUE (usuario_id, categoria_id),
    CONSTRAINT fk_preferencias_deducibilidad_categoria
        FOREIGN KEY (categoria_id) REFERENCES categorias_gasto (id) ON DELETE CASCADE
    -- fk a usuarios se añade en la migración de la tabla usuarios (V3)
);

COMMENT ON TABLE  preferencias_deducibilidad_usuario IS 'Porcentajes que el usuario ha personalizado para su cuenta, sobreescribiendo las reglas del catálogo.';
COMMENT ON COLUMN preferencias_deducibilidad_usuario.usuario_id IS 'FK a la tabla usuarios (restricción formal añadida en V3 tras crear dicha tabla).';

-- ── Índices ───────────────────────────────────────────────────────────────────

CREATE INDEX idx_categorias_gasto_grupo_id
    ON categorias_gasto (grupo_id);

CREATE INDEX idx_reglas_deducibilidad_categoria_id
    ON reglas_deducibilidad (categoria_id);

CREATE INDEX idx_preferencias_deducibilidad_usuario_id
    ON preferencias_deducibilidad_usuario (usuario_id);

-- ── Trigger updated_at automático ────────────────────────────────────────────

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_grupos_categoria_gasto_updated_at
    BEFORE UPDATE ON grupos_categoria_gasto
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_categorias_gasto_updated_at
    BEFORE UPDATE ON categorias_gasto
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_reglas_deducibilidad_updated_at
    BEFORE UPDATE ON reglas_deducibilidad
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_preferencias_deducibilidad_usuario_updated_at
    BEFORE UPDATE ON preferencias_deducibilidad_usuario
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
