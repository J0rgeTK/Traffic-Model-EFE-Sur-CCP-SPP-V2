-- infraestructura.db  --  datos maestros: estaciones, cruces, barreras y semaforos
PRAGMA foreign_keys = ON;

CREATE TABLE estaciones (
    estacion_id INTEGER PRIMARY KEY,
    nombre      TEXT    NOT NULL UNIQUE,
    orden_linea INTEGER NOT NULL UNIQUE,
    comuna      TEXT,
    latitud     REAL,
    longitud    REAL
);

CREATE TABLE cruces (
    cruce_id             INTEGER PRIMARY KEY,
    nombre               TEXT    NOT NULL UNIQUE,
    comuna               TEXT,
    latitud              REAL,
    longitud             REAL,
    num_pistas_total     INTEGER,
    num_carriles_lateral INTEGER NOT NULL DEFAULT 2,
    tiene_semaforo       INTEGER NOT NULL DEFAULT 1 CHECK (tiene_semaforo IN (0,1)),
    afecta_lateral       INTEGER NOT NULL DEFAULT 1 CHECK (afecta_lateral IN (0,1)),
    sentido_afectacion   TEXT CHECK (sentido_afectacion IN ('CC','CW') OR sentido_afectacion IS NULL),
    estacion_cercana_id  INTEGER REFERENCES estaciones(estacion_id),
    dist_estacion_m      REAL,
    estado_camaras       TEXT,
    observaciones        TEXT
);

CREATE TABLE cruce_tramo (
    cruce_id          INTEGER NOT NULL REFERENCES cruces(cruce_id),
    sentido           TEXT    NOT NULL CHECK (sentido IN ('CC','CW')),
    estacion_desde_id INTEGER REFERENCES estaciones(estacion_id),
    estacion_hasta_id INTEGER REFERENCES estaciones(estacion_id),
    dist_desde_m      REAL,
    dist_total_m      REAL,
    PRIMARY KEY (cruce_id, sentido)
);

CREATE TABLE parametros_barrera (
    cruce_id         INTEGER NOT NULL REFERENCES cruces(cruce_id),
    sentido          TEXT    NOT NULL CHECK (sentido IN ('CC','CW')),
    tiempo_barrera_s INTEGER NOT NULL,
    margen_pre_s     INTEGER NOT NULL DEFAULT 10,
    margen_post_s    INTEGER NOT NULL DEFAULT 10,
    tiempo_alarma_s  INTEGER,
    fuente           TEXT,
    fecha_medicion   TEXT,
    PRIMARY KEY (cruce_id, sentido)
);

CREATE TABLE versiones_programacion (
    version_prog_id INTEGER PRIMARY KEY,
    nombre          TEXT NOT NULL UNIQUE,
    fecha           TEXT,
    tipo_version    TEXT,
    fuente          TEXT,
    descripcion     TEXT
);

-- Planes horarios POR CRUCE y POR TIPO DE DIA (Laboral, Sabado, Domingo/Festivo).
CREATE TABLE planes_horarios_cruce (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    version_prog_id INTEGER NOT NULL REFERENCES versiones_programacion(version_prog_id),
    cruce_id        INTEGER NOT NULL REFERENCES cruces(cruce_id),
    tipo_dia        TEXT    NOT NULL DEFAULT 'Laboral'
                    CHECK (tipo_dia IN ('Laboral','Sabado','Domingo/Festivo')),
    hora_inicio_s   INTEGER NOT NULL CHECK (hora_inicio_s BETWEEN 0 AND 86400),
    hora_fin_s      INTEGER NOT NULL CHECK (hora_fin_s   BETWEEN 0 AND 86400),
    plan_id         INTEGER NOT NULL,
    fuente          TEXT,
    UNIQUE (version_prog_id, cruce_id, tipo_dia, hora_inicio_s)
);

CREATE TABLE programacion_fases (
    fase_pk          INTEGER PRIMARY KEY,
    version_prog_id  INTEGER NOT NULL REFERENCES versiones_programacion(version_prog_id),
    cruce_id         INTEGER NOT NULL REFERENCES cruces(cruce_id),
    plan_id          INTEGER NOT NULL,
    fase_id          INTEGER NOT NULL,
    duracion_s       INTEGER NOT NULL,
    entreverde_s     INTEGER NOT NULL DEFAULT 0,
    cum_inicio_s     INTEGER NOT NULL,
    cum_fin_s        INTEGER NOT NULL,
    es_verde_lateral INTEGER NOT NULL DEFAULT 0 CHECK (es_verde_lateral IN (0,1)),
    ciclo_s          INTEGER NOT NULL,
    fase_origen      TEXT,
    fuente           TEXT,
    confianza        TEXT,
    estado_carga     TEXT,
    UNIQUE (version_prog_id, cruce_id, plan_id, fase_id)
);

-- Modelo operacional por cruce: regla operativa que aplica al cruce.
CREATE TABLE modelo_operacional_cruce (
    cruce_id             INTEGER PRIMARY KEY REFERENCES cruces(cruce_id),
    tipo_modelo          TEXT    NOT NULL
                         CHECK (tipo_modelo IN ('RECONFIG','NOREPROG')),
    usa_reconfiguracion  INTEGER NOT NULL DEFAULT 0 CHECK (usa_reconfiguracion IN (0,1)),
    version_prog_id      INTEGER NOT NULL REFERENCES versiones_programacion(version_prog_id),
    descripcion          TEXT,
    fuente               TEXT
);

-- Declaracion del proyecto: cruces en el alcance con su ID SCATS, via, etc.
CREATE TABLE cruces_reconfiguracion (
    cruce_id           INTEGER PRIMARY KEY REFERENCES cruces(cruce_id),
    via_principal      TEXT,
    codigo_proyecto    TEXT,
    comuna_referencia  TEXT,
    estado_carga       TEXT,
    confianza          TEXT,
    fuente             TEXT,
    fecha_declaracion  TEXT DEFAULT (date('now'))
);

CREATE INDEX ix_fases_cruce_plan ON programacion_fases (version_prog_id, cruce_id, plan_id);
CREATE INDEX ix_planes_cruce ON planes_horarios_cruce (version_prog_id, cruce_id, tipo_dia);
