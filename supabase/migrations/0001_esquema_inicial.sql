-- Esquema de Expresangil en Postgres, espejo del de SQLite.
--
-- Las fechas se guardan como TEXT en formato 'AAAA-MM-DD', igual que en
-- SQLite: toda la aplicacion las compara y filtra como texto ISO (que
-- ordena bien), y cambiarlas a DATE aqui obligaria a revisar cada consulta
-- y cada informe. Se puede migrar despues, con calma.
--
-- Los importes son BIGINT: son pesos colombianos sin decimales.

CREATE TABLE IF NOT EXISTS guias (
    guia          TEXT PRIMARY KEY,
    planilla      TEXT,
    servicio      TEXT,
    unid          TEXT,
    tipo_de_servicio TEXT,
    destinatario  TEXT,
    direccion     TEXT,
    municipio     TEXT,
    valor         TEXT,
    operador      TEXT,
    estado        TEXT,
    causal        TEXT,
    fecha         TEXT,   -- F_INGRESO: dia en que entro por planilla
    ingreso       TEXT,   -- F_ENTREGA: dia en que se gestiono
    orden_salida  BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS guias_archivo (
    guia          TEXT PRIMARY KEY,
    planilla      TEXT,
    servicio      TEXT,
    unid          TEXT,
    tipo_de_servicio TEXT,
    destinatario  TEXT,
    direccion     TEXT,
    municipio     TEXT,
    valor         TEXT,
    operador      TEXT,
    estado        TEXT,
    causal        TEXT,
    fecha         TEXT,
    ingreso       TEXT,
    orden_salida  BIGINT NOT NULL DEFAULT 0,
    archivado_en  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS operadores (
    usuario       TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    nombre        TEXT NOT NULL,
    rol           TEXT NOT NULL DEFAULT 'operador',
    licencia_vencimiento      TEXT NOT NULL DEFAULT '',
    soat_vencimiento          TEXT NOT NULL DEFAULT '',
    tecnomecanica_vencimiento TEXT NOT NULL DEFAULT '',
    salario_base       BIGINT NOT NULL DEFAULT 0,
    auxilio_transporte BIGINT NOT NULL DEFAULT 0,
    cedula        TEXT NOT NULL DEFAULT '',
    cargo         TEXT NOT NULL DEFAULT '',
    apellidos     TEXT NOT NULL DEFAULT '',
    fecha_ingreso TEXT NOT NULL DEFAULT '',
    fecha_retiro  TEXT NOT NULL DEFAULT '',
    tipo_contrato TEXT NOT NULL DEFAULT 'NOMINA',
    valor_encomienda BIGINT NOT NULL DEFAULT 0,
    celular       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS cierres_operador (
    fecha       TEXT NOT NULL,
    operador    TEXT NOT NULL,
    gestionadas BIGINT NOT NULL,
    ro          BIGINT NOT NULL,
    n           BIGINT NOT NULL,
    d           BIGINT NOT NULL,
    e           BIGINT NOT NULL,
    recaudado   BIGINT NOT NULL,
    bancos      BIGINT NOT NULL,
    nequi       BIGINT NOT NULL,
    envia       BIGINT NOT NULL,
    efectivo    BIGINT NOT NULL,
    gastos            BIGINT NOT NULL DEFAULT 0,
    adelanto_salario  BIGINT NOT NULL DEFAULT 0,
    denominaciones    TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (fecha, operador)
);

CREATE TABLE IF NOT EXISTS cierres_generales (
    fecha            TEXT PRIMARY KEY,
    denominaciones   TEXT NOT NULL DEFAULT '{}',
    efectivo_contado BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prestamos (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empleado      TEXT NOT NULL,
    tipo          TEXT NOT NULL,
    monto         BIGINT NOT NULL,
    fecha         TEXT NOT NULL,
    forma_pago    TEXT NOT NULL DEFAULT '',
    cuotas        BIGINT NOT NULL DEFAULT 1,
    observaciones TEXT NOT NULL DEFAULT '',
    estado        TEXT NOT NULL DEFAULT 'ACTIVO'
);

CREATE TABLE IF NOT EXISTS prestamo_abonos (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prestamo_id BIGINT NOT NULL REFERENCES prestamos(id) ON DELETE CASCADE,
    fecha       TEXT NOT NULL,
    monto       BIGINT NOT NULL,
    concepto    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS nomina (
    periodo       TEXT NOT NULL,
    empleado      TEXT NOT NULL,
    salario_base       BIGINT NOT NULL DEFAULT 0,
    dias_trabajados    BIGINT NOT NULL DEFAULT 30,
    auxilio_transporte BIGINT NOT NULL DEFAULT 0,
    bonificaciones     BIGINT NOT NULL DEFAULT 0,
    salud              BIGINT NOT NULL DEFAULT 0,
    pension            BIGINT NOT NULL DEFAULT 0,
    descuento_prestamos BIGINT NOT NULL DEFAULT 0,
    otros_descuentos   BIGINT NOT NULL DEFAULT 0,
    total_pagar        BIGINT NOT NULL DEFAULT 0,
    observaciones TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (periodo, empleado)
);

CREATE TABLE IF NOT EXISTS liquidaciones_semanales (
    semana_inicio TEXT NOT NULL,
    empleado      TEXT NOT NULL,
    entregas          BIGINT NOT NULL DEFAULT 0,
    valor_encomienda  BIGINT NOT NULL DEFAULT 0,
    subtotal          BIGINT NOT NULL DEFAULT 0,
    descuento_prestamos BIGINT NOT NULL DEFAULT 0,
    otros_descuentos  BIGINT NOT NULL DEFAULT 0,
    total_pagar       BIGINT NOT NULL DEFAULT 0,
    forma_pago    TEXT NOT NULL DEFAULT '',
    observaciones TEXT NOT NULL DEFAULT '',
    registrada_en TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (semana_inicio, empleado)
);

CREATE TABLE IF NOT EXISTS liquidaciones_laborales (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empleado      TEXT NOT NULL,
    tipo_liquidacion TEXT NOT NULL DEFAULT 'RETIRO_VOLUNTARIO',
    fecha_ingreso TEXT NOT NULL,
    fecha_retiro  TEXT NOT NULL,
    dias_trabajados    BIGINT NOT NULL DEFAULT 0,
    salario_base       BIGINT NOT NULL DEFAULT 0,
    auxilio_transporte BIGINT NOT NULL DEFAULT 0,
    cesantias             BIGINT NOT NULL DEFAULT 0,
    cesantias_pagadas     BIGINT NOT NULL DEFAULT 0,
    cesantias_consignadas BIGINT NOT NULL DEFAULT 0,
    intereses_cesantias   BIGINT NOT NULL DEFAULT 0,
    prima         BIGINT NOT NULL DEFAULT 0,
    vacaciones    BIGINT NOT NULL DEFAULT 0,
    indemnizacion BIGINT NOT NULL DEFAULT 0,
    otros_descuentos BIGINT NOT NULL DEFAULT 0,
    total_pagar   BIGINT NOT NULL DEFAULT 0,
    observaciones TEXT NOT NULL DEFAULT '',
    registrada_en TEXT NOT NULL DEFAULT ''
);

-- Sesiones del panel. Se guarda el hash del token, no el token: los
-- respaldos salen del servidor y una copia no debe entregar sesiones vivas.
CREATE TABLE IF NOT EXISTS sesiones (
    token_hash TEXT PRIMARY KEY,
    usuario    TEXT NOT NULL,
    nombre     TEXT NOT NULL,
    rol        TEXT NOT NULL,
    creada_en  TEXT NOT NULL,
    expira_en  TEXT NOT NULL
);

-- Libro de caja de la oficina: ingresos y egresos digitados a mano. La
-- nomina y los gastos NO se copian aqui; se leen de su propia tabla al
-- armar el informe, para que no haya dos verdades.
CREATE TABLE IF NOT EXISTS movimientos (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha       TEXT NOT NULL,
    tipo        TEXT NOT NULL,
    categoria   TEXT NOT NULL DEFAULT '',
    descripcion TEXT NOT NULL DEFAULT '',
    valor       BIGINT NOT NULL DEFAULT 0,
    forma_pago  TEXT NOT NULL DEFAULT '',
    registrado_por TEXT NOT NULL DEFAULT '',
    registrado_en  TEXT NOT NULL DEFAULT ''
);

-- Indices para las consultas que mas se repiten en la operacion diaria.
CREATE INDEX IF NOT EXISTS idx_guias_operador_estado ON guias (operador, estado);
CREATE INDEX IF NOT EXISTS idx_guias_ingreso ON guias (ingreso);
CREATE INDEX IF NOT EXISTS idx_guias_fecha ON guias (fecha);
CREATE INDEX IF NOT EXISTS idx_archivo_ingreso ON guias_archivo (ingreso);
CREATE INDEX IF NOT EXISTS idx_archivo_operador ON guias_archivo (operador);
CREATE INDEX IF NOT EXISTS idx_prestamos_empleado ON prestamos (empleado);
CREATE INDEX IF NOT EXISTS idx_abonos_prestamo ON prestamo_abonos (prestamo_id);
CREATE INDEX IF NOT EXISTS idx_sesiones_usuario ON sesiones (usuario);
CREATE INDEX IF NOT EXISTS idx_movimientos_fecha ON movimientos (fecha);

-- Seguridad: aqui hay salarios, cedulas y prestamos de personas reales.
-- Supabase publica estas tablas por PostgREST con la clave anonima, que es
-- publica por diseño. Con RLS activo y SIN politicas, esa via queda cerrada
-- del todo; el aplicativo entra por conexion directa de Postgres, que no
-- pasa por RLS. Si algun dia se quiere una app movil, se agregan politicas
-- explicitas aqui.
ALTER TABLE guias                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE guias_archivo           ENABLE ROW LEVEL SECURITY;
ALTER TABLE operadores              ENABLE ROW LEVEL SECURITY;
ALTER TABLE cierres_operador        ENABLE ROW LEVEL SECURITY;
ALTER TABLE cierres_generales       ENABLE ROW LEVEL SECURITY;
ALTER TABLE prestamos               ENABLE ROW LEVEL SECURITY;
ALTER TABLE prestamo_abonos         ENABLE ROW LEVEL SECURITY;
ALTER TABLE nomina                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE liquidaciones_semanales ENABLE ROW LEVEL SECURITY;
ALTER TABLE liquidaciones_laborales ENABLE ROW LEVEL SECURITY;
ALTER TABLE sesiones                ENABLE ROW LEVEL SECURITY;
ALTER TABLE movimientos             ENABLE ROW LEVEL SECURITY;
