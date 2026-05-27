-- demanda.db  --  insumos de estudio: aforos vehiculares e itinerario ferroviario
PRAGMA foreign_keys = ON;

CREATE TABLE campanias_medicion (
    campania_id INTEGER PRIMARY KEY,
    nombre      TEXT NOT NULL UNIQUE,
    fecha       TEXT,
    fuente      TEXT,
    descripcion TEXT
);

-- flujo_veh_h se guarda CRUDO (sin el factor k_dem).
-- El motor calcula  lambda = flujo_veh_h / 3600 * k_dem  en ejecucion.
CREATE TABLE llegadas_vehiculares (
    id          INTEGER PRIMARY KEY,
    campania_id INTEGER NOT NULL REFERENCES campanias_medicion(campania_id),
    cruce_id    INTEGER NOT NULL,
    t_inicio_s  INTEGER NOT NULL CHECK (t_inicio_s BETWEEN 0 AND 86399),
    t_fin_s     INTEGER NOT NULL CHECK (t_fin_s   BETWEEN 0 AND 86400),
    flujo_veh_h REAL    NOT NULL CHECK (flujo_veh_h >= 0),
    UNIQUE (campania_id, cruce_id, t_inicio_s)
);

CREATE TABLE itinerario_versiones (
    itinerario_id INTEGER PRIMARY KEY,
    nombre        TEXT NOT NULL UNIQUE,
    fecha         TEXT,
    descripcion   TEXT
);

CREATE TABLE servicios_ferroviarios (
    servicio_id    INTEGER PRIMARY KEY,
    itinerario_id  INTEGER NOT NULL REFERENCES itinerario_versiones(itinerario_id),
    codigo         TEXT,
    numero_tren    INTEGER,
    tipo           TEXT,
    sentido        TEXT CHECK (sentido IN ('CC','CW') OR sentido IS NULL),
    dias_operacion TEXT
);

CREATE TABLE itinerario_paradas (
    id             INTEGER PRIMARY KEY,
    servicio_id    INTEGER NOT NULL REFERENCES servicios_ferroviarios(servicio_id),
    estacion_id    INTEGER NOT NULL,
    orden          INTEGER NOT NULL,
    hora_llegada_s INTEGER,
    hora_salida_s  INTEGER,
    UNIQUE (servicio_id, estacion_id)
);

-- Eventos de barrera derivados del itinerario (ex hojas PasadasCruce + HCALL).
-- Son la entrada de Hurry Call que consume el motor de simulacion.
CREATE TABLE eventos_barrera (
    id              INTEGER PRIMARY KEY,
    itinerario_id   INTEGER NOT NULL REFERENCES itinerario_versiones(itinerario_id),
    cruce_id        INTEGER NOT NULL,
    sentido         TEXT CHECK (sentido IN ('CC','CW') OR sentido IS NULL),
    instante_paso_s INTEGER,
    hcall_in_s      INTEGER NOT NULL,
    hcall_out_s     INTEGER NOT NULL,
    CHECK (hcall_in_s <= hcall_out_s)
);

CREATE INDEX ix_llegadas_cruce ON llegadas_vehiculares (campania_id, cruce_id, t_inicio_s);
CREATE INDEX ix_paradas_servicio ON itinerario_paradas (servicio_id, orden);
CREATE INDEX ix_hcall_itin ON eventos_barrera (itinerario_id, cruce_id, hcall_in_s);
