-- =============================================================================
-- V2.1__categoria_gasto_seed.sql
-- Datos iniciales del catálogo: grupos, categorías y reglas de deducibilidad
-- para el régimen más común (estimación directa simplificada).
--
-- Los porcentajes siguen la doctrina general de la AEAT para autónomos:
--   - Vehículos: 50% IVA y 50% IRPF (afectación mixta por defecto)
--   - Hogar (trabajo desde casa): 30% IVA y 30% IRPF (regla 30% superficie)
--   - Dietas en España: 100% IVA deducible si hay justificante; IRPF no aplica directamente
--   - Software/suscripciones 100%: afectación total a la actividad
--
-- Fuente: Art. 95 LIVA, Art. 30 LIRPF, consultas vinculantes AEAT.
-- Estos valores son el punto de partida — el usuario puede sobreescribirlos
-- en PreferenciaDeducibilidadUsuario según su situación particular.
-- =============================================================================

-- ── Grupos ────────────────────────────────────────────────────────────────────

INSERT INTO grupos_categoria_gasto (id, codigo, nombre_display, orden_dashboard) VALUES
    ('00000000-0000-0000-0000-000000000001', 'operaciones',    'Operaciones y servicios', 1),
    ('00000000-0000-0000-0000-000000000002', 'infraestructura','Infraestructura y oficina', 2),
    ('00000000-0000-0000-0000-000000000003', 'desplazamientos','Desplazamientos y dietas',  3),
    ('00000000-0000-0000-0000-000000000004', 'personal',       'Gastos personales y RETA',  4),
    ('00000000-0000-0000-0000-000000000005', 'otros_gastos',   'Otros gastos',              5);

-- ── Categorías ────────────────────────────────────────────────────────────────
-- El código debe coincidir con el enum CategoriaGasto del servicio Python

INSERT INTO categorias_gasto (id, codigo, nombre_display, grupo_id) VALUES
    -- Grupo: Operaciones y servicios
    ('10000000-0000-0000-0000-000000000001', 'software_suscripciones',  'Software y suscripciones',   '00000000-0000-0000-0000-000000000001'),
    ('10000000-0000-0000-0000-000000000002', 'servicios_profesionales', 'Servicios profesionales',    '00000000-0000-0000-0000-000000000001'),
    ('10000000-0000-0000-0000-000000000003', 'publicidad_marketing',    'Publicidad y marketing',     '00000000-0000-0000-0000-000000000001'),
    ('10000000-0000-0000-0000-000000000004', 'formacion',               'Formación',                  '00000000-0000-0000-0000-000000000001'),
    ('10000000-0000-0000-0000-000000000005', 'seguros',                 'Seguros',                    '00000000-0000-0000-0000-000000000001'),
    -- Grupo: Infraestructura y oficina
    ('10000000-0000-0000-0000-000000000006', 'material_oficina',        'Material de oficina',        '00000000-0000-0000-0000-000000000002'),
    ('10000000-0000-0000-0000-000000000007', 'suministros_oficina',     'Suministros de oficina',     '00000000-0000-0000-0000-000000000002'),
    ('10000000-0000-0000-0000-000000000008', 'suministros_hogar',       'Suministros del hogar',      '00000000-0000-0000-0000-000000000002'),
    ('10000000-0000-0000-0000-000000000009', 'alquiler',                'Alquiler',                   '00000000-0000-0000-0000-000000000002'),
    ('10000000-0000-0000-0000-000000000010', 'vehiculos',               'Vehículos',                  '00000000-0000-0000-0000-000000000002'),
    -- Grupo: Desplazamientos y dietas
    ('10000000-0000-0000-0000-000000000011', 'viajes_transporte',       'Viajes y transporte',        '00000000-0000-0000-0000-000000000003'),
    ('10000000-0000-0000-0000-000000000012', 'dietas_restauracion',     'Dietas y restauración',      '00000000-0000-0000-0000-000000000003'),
    -- Grupo: Gastos personales y RETA
    ('10000000-0000-0000-0000-000000000013', 'cuota_autonomo_reta',     'Cuota autónomo (RETA)',      '00000000-0000-0000-0000-000000000004'),
    -- Grupo: Otros gastos
    ('10000000-0000-0000-0000-000000000014', 'otros',                   'Otros gastos',               '00000000-0000-0000-0000-000000000005');

-- ── Reglas de deducibilidad — Estimación Directa Simplificada ────────────────
-- Régimen más común. Porcentajes por defecto según criterio AEAT.

INSERT INTO reglas_deducibilidad (categoria_id, regimen_fiscal, pct_deducible_iva, pct_deducible_irpf) VALUES
    -- software_suscripciones: 100% si es para la actividad
    ('10000000-0000-0000-0000-000000000001', 'estimacion_directa_simplificada', 100.00, 100.00),
    -- servicios_profesionales: 100%
    ('10000000-0000-0000-0000-000000000002', 'estimacion_directa_simplificada', 100.00, 100.00),
    -- publicidad_marketing: 100%
    ('10000000-0000-0000-0000-000000000003', 'estimacion_directa_simplificada', 100.00, 100.00),
    -- formacion: 100%
    ('10000000-0000-0000-0000-000000000004', 'estimacion_directa_simplificada', 100.00, 100.00),
    -- seguros: 100% si son de la actividad
    ('10000000-0000-0000-0000-000000000005', 'estimacion_directa_simplificada', 100.00, 100.00),
    -- material_oficina: 100%
    ('10000000-0000-0000-0000-000000000006', 'estimacion_directa_simplificada', 100.00, 100.00),
    -- suministros_oficina: 100%
    ('10000000-0000-0000-0000-000000000007', 'estimacion_directa_simplificada', 100.00, 100.00),
    -- suministros_hogar: 30% (regla del 30% del espacio dedicado a la actividad)
    ('10000000-0000-0000-0000-000000000008', 'estimacion_directa_simplificada',  30.00,  30.00),
    -- alquiler: 100% si es de local de negocio; 30% si es de vivienda habitual
    --   → valor conservador por defecto: 30%. El usuario puede subir al 100% si tiene local
    ('10000000-0000-0000-0000-000000000009', 'estimacion_directa_simplificada',  30.00,  30.00),
    -- vehiculos: 50% IVA (Art. 95.3 LIVA), 50% IRPF (uso mixto por defecto)
    ('10000000-0000-0000-0000-000000000010', 'estimacion_directa_simplificada',  50.00,  50.00),
    -- viajes_transporte (taxi, tren, avión): 100%
    ('10000000-0000-0000-0000-000000000011', 'estimacion_directa_simplificada', 100.00, 100.00),
    -- dietas_restauracion: IVA 100% deducible con justificante; IRPF: no deducible como gasto
    --   (las dietas tienen tratamiento especial en el 130 — se deducen por baremos, no por factura)
    ('10000000-0000-0000-0000-000000000012', 'estimacion_directa_simplificada', 100.00,   0.00),
    -- cuota_autonomo_reta: sin IVA; 100% deducible en IRPF
    ('10000000-0000-0000-0000-000000000013', 'estimacion_directa_simplificada',   0.00, 100.00),
    -- otros: valor conservador, el usuario debe revisar
    ('10000000-0000-0000-0000-000000000014', 'estimacion_directa_simplificada', 100.00, 100.00);

-- ── Reglas de deducibilidad — Estimación Directa Normal ──────────────────────
-- Mismo punto de partida que simplificada — las diferencias se aplican en el cálculo
-- del rendimiento neto (más opciones de amortización), no en los porcentajes de IVA/IRPF.

INSERT INTO reglas_deducibilidad (categoria_id, regimen_fiscal, pct_deducible_iva, pct_deducible_irpf) VALUES
    ('10000000-0000-0000-0000-000000000001', 'estimacion_directa_normal', 100.00, 100.00),
    ('10000000-0000-0000-0000-000000000002', 'estimacion_directa_normal', 100.00, 100.00),
    ('10000000-0000-0000-0000-000000000003', 'estimacion_directa_normal', 100.00, 100.00),
    ('10000000-0000-0000-0000-000000000004', 'estimacion_directa_normal', 100.00, 100.00),
    ('10000000-0000-0000-0000-000000000005', 'estimacion_directa_normal', 100.00, 100.00),
    ('10000000-0000-0000-0000-000000000006', 'estimacion_directa_normal', 100.00, 100.00),
    ('10000000-0000-0000-0000-000000000007', 'estimacion_directa_normal', 100.00, 100.00),
    ('10000000-0000-0000-0000-000000000008', 'estimacion_directa_normal',  30.00,  30.00),
    ('10000000-0000-0000-0000-000000000009', 'estimacion_directa_normal',  30.00,  30.00),
    ('10000000-0000-0000-0000-000000000010', 'estimacion_directa_normal',  50.00,  50.00),
    ('10000000-0000-0000-0000-000000000011', 'estimacion_directa_normal', 100.00, 100.00),
    ('10000000-0000-0000-0000-000000000012', 'estimacion_directa_normal', 100.00,   0.00),
    ('10000000-0000-0000-0000-000000000013', 'estimacion_directa_normal',   0.00, 100.00),
    ('10000000-0000-0000-0000-000000000014', 'estimacion_directa_normal', 100.00, 100.00);
