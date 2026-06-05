"""
Configuracion de importacion
=============================
Centraliza el mapeo con el fuente de referencia para que ninguna fila, hoja o
posicion quede hardcodeada en la logica. La deteccion de bloques HCALL
se hace por ETIQUETA (texto en la columna A), no por numero de fila.
"""
from __future__ import annotations
from dataclasses import dataclass

# Nombres de hoja del fuente de referencia (unico punto de acoplamiento).
HOJAS = {
    'bbdd':       'BBDD',
    'itinerario': 'Itinerario (INPUT)',
    'plan':       'Plan',
    'prog_fases': 'PROG_FASES',
    'llegadas':   'Llegadas',
    'hcall':      'HCALL',
}

# Etiquetas que delimitan los bloques dentro de la hoja HCALL.
HCALL_MARCA_IN = 'HCALL-IN'
HCALL_MARCA_OUT = 'HCALL-OUT'
HCALL_FILA_CRUCE_ID = 'Cruce ID'     # fila de cabecera de servicios
HCALL_MARCA_FIN = ('Matriz', 'Promedio', 'Observ')  # cortes de bloque

# Columnas (1-indexadas) de cada hoja tabular. Si el fuente de referencia cambia de
# layout, se ajusta aqui y no en el codigo.
COLS_BBDD = {
    'id': 1, 'nombre': 2, 'comuna': 3, 'latitud': 4, 'longitud': 5,
    'pistas': 6, 'semaforo': 7, 'estado_camaras': 8, 'dist_estacion': 9,
    'dist_total': 10, 'estacion_cercana': 11,
    'tramo_cw_desde': 13, 'tramo_cw_hasta': 14,
    'tramo_cc_desde': 15, 'tramo_cc_hasta': 16,
    'afecta_lateral': 20, 'sentido_afectacion': 21,
    'barrera_cw': 22, 'barrera_cc': 23,
}
COLS_PLAN = {'ini': 2, 'fin': 3, 'plan': 4}
COLS_PROG_FASES = {
    'cruce': 1, 'plan': 2, 'fase': 3, 'duracion': 4, 'entreverde': 5,
    'cumend': 6, 'cumstart': 7, 'verde_lateral': 8, 'ciclo': 9,
}
COLS_LLEGADAS = {'cruce': 1, 't_ini': 2, 't_fin': 3, 'veh_h': 4}

# Fila/columna de la alarma sonora en BBDD (dato suelto del original).
BBDD_ALARMA = (25, 7)

# Factor de demanda incrustado en el fuente de referencia (panel B9 sin efecto).
# Se documenta aqui para trazabilidad; en la base el flujo va CRUDO.
K_DEM_REF = 1.1


@dataclass(frozen=True)
class FuenteReferencia:
    """Identifica un libro de origen de origen y su rol."""
    ruta: str
    version: str          # nombre de la version de programacion
    campania: str         # nombre de la campania de aforos
    es_base: bool         # True para el escenario base/vigente
