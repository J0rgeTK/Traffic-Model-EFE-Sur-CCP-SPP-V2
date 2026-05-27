"""
Capa de acceso a datos
======================
Conecta las tres bases SQLite y construye objetos `Inputs` para el motor
de simulacion. Es el unico modulo que conoce el esquema de la base; el
motor (`motor_sim.py`) solo recibe objetos `Inputs` ya armados.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

from motor_sim import Inputs, Resultados

DIR_DATA = Path(__file__).resolve().parent / 'data'
DB_INFRA = DIR_DATA / 'infraestructura.db'
DB_DEM   = DIR_DATA / 'demanda.db'
DB_ESC   = DIR_DATA / 'escenarios.db'


def _hhmmss(seg: int) -> str:
    """Segundos del dia -> 'HH:MM:SS' (formato que espera el motor)."""
    seg = int(seg) % 86400
    return f'{seg // 3600:02d}:{(seg % 3600) // 60:02d}:{seg % 60:02d}'


def conectar() -> sqlite3.Connection:
    """Abre escenarios.db y adjunta infraestructura y demanda."""
    con = sqlite3.connect(DB_ESC, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute('ATTACH DATABASE ? AS infra', (str(DB_INFRA),))
    con.execute('ATTACH DATABASE ? AS dem',   (str(DB_DEM),))
    con.execute('PRAGMA foreign_keys = ON')
    return con


# --------------------------------------------------------------------- #
#  consultas de catalogo (para selectores y mapa)
# --------------------------------------------------------------------- #
def listar_cruces(con) -> list[sqlite3.Row]:
    """Todos los cruces con georreferencia."""
    return con.execute(
        'SELECT * FROM infra.cruces ORDER BY cruce_id').fetchall()


def cruces_simulables(con) -> list[str]:
    """Cruces que tienen aforos Y eventos de barrera (los que el motor puede correr)."""
    return [r['nombre'] for r in con.execute("""
        SELECT DISTINCT c.nombre
        FROM   infra.cruces c
        JOIN   dem.llegadas_vehiculares l ON l.cruce_id = c.cruce_id
        JOIN   dem.eventos_barrera      e ON e.cruce_id = c.cruce_id
        ORDER  BY c.nombre""")]


def listar_escenarios(con) -> list[sqlite3.Row]:
    return con.execute('SELECT * FROM escenarios ORDER BY escenario_id').fetchall()


def listar_versiones(con) -> list[sqlite3.Row]:
    return con.execute(
        'SELECT * FROM infra.versiones_programacion').fetchall()


def listar_campanias(con) -> list[sqlite3.Row]:
    return con.execute('SELECT * FROM dem.campanias_medicion').fetchall()


# --------------------------------------------------------------------- #
#  construccion de Inputs para el motor
# --------------------------------------------------------------------- #
def construir_inputs(con, cruce: str, version_prog_id: int = 1,
                     campania_id: int = 1, itinerario_id: int = 1,
                     hora_inicio_s: int = 21600, hora_fin_s: int = 75600,
                     h: float = 2.0, n_carriles: float = 2.0,
                     buffer: int = 0, k_dem: float = 1.1) -> Inputs:
    """Arma un objeto Inputs leyendo los insumos desde las bases.

    El flujo en la base es CRUDO; aqui lambda = flujo_veh_h / 3600 y el
    motor aplica k_dem. Para reproducir el Excel original usar k_dem=1.1.
    """
    cid = con.execute('SELECT cruce_id FROM infra.cruces WHERE nombre = ?',
                       (cruce,)).fetchone()
    if cid is None:
        raise ValueError(f'Cruce no encontrado: {cruce}')
    cid = cid['cruce_id']

    prog_fases = [{
        'cross': cruce, 'plan': r['plan_id'], 'phase': r['fase_id'],
        'dur': r['duracion_s'], 'entreverde': r['entreverde_s'],
        'cumend': r['cum_fin_s'], 'cumstart': r['cum_inicio_s'],
        'green_movx': r['es_verde_lateral'], 'ciclo': r['ciclo_s'],
    } for r in con.execute(
        'SELECT * FROM infra.programacion_fases '
        'WHERE version_prog_id = ? AND cruce_id = ?', (version_prog_id, cid))]

    plan = [{
        'ini': _hhmmss(r['hora_inicio_s']),
        'fin': _hhmmss(r['hora_fin_s']),
        'plan': r['plan_id'],
    } for r in con.execute(
        'SELECT * FROM infra.planes_horarios WHERE version_prog_id = ?',
        (version_prog_id,))]

    llegadas = [{
        'cruce': cruce, 't_ini': r['t_inicio_s'], 't_fin': r['t_fin_s'],
        'lambda': r['flujo_veh_h'] / 3600.0,        # CRUDO; k_dem lo aplica el motor
    } for r in con.execute(
        'SELECT * FROM dem.llegadas_vehiculares '
        'WHERE campania_id = ? AND cruce_id = ?', (campania_id, cid))]

    eventos = con.execute(
        'SELECT hcall_in_s, hcall_out_s FROM dem.eventos_barrera '
        'WHERE itinerario_id = ? AND cruce_id = ? ORDER BY hcall_in_s',
        (itinerario_id, cid)).fetchall()
    hcall_in  = sorted(r['hcall_in_s']  for r in eventos)
    hcall_out = sorted(r['hcall_out_s'] for r in eventos)

    return Inputs(
        crossing=cruce, start_s=hora_inicio_s, end_s=hora_fin_s,
        h=h, n_carriles=n_carriles, buffer=buffer, k_dem=k_dem,
        prog_fases=prog_fases, plan=plan, llegadas=llegadas,
        hcall_in=hcall_in, hcall_out=hcall_out,
    )


def inputs_de_escenario(con, escenario_id: int) -> tuple[Inputs, sqlite3.Row]:
    """Construye Inputs a partir de un escenario guardado."""
    e = con.execute('SELECT * FROM escenarios WHERE escenario_id = ?',
                     (escenario_id,)).fetchone()
    if e is None:
        raise ValueError(f'Escenario inexistente: {escenario_id}')
    cruce = con.execute('SELECT nombre FROM infra.cruces WHERE cruce_id = ?',
                        (e['cruce_id'],)).fetchone()['nombre']
    inp = construir_inputs(
        con, cruce, version_prog_id=e['version_prog_id'],
        campania_id=e['campania_id'], itinerario_id=e['itinerario_id'],
        hora_inicio_s=e['hora_inicio_s'], hora_fin_s=e['hora_fin_s'],
        h=e['headway_s'], n_carriles=e['num_carriles'],
        buffer=e['buffer_pre_s'], k_dem=e['k_dem'])
    return inp, e


# --------------------------------------------------------------------- #
#  persistencia de resultados
# --------------------------------------------------------------------- #
def guardar_resultado(con, escenario_id: int, res: Resultados) -> None:
    """Inserta o actualiza los KPIs de un escenario.

    Nota: en Streamlit Community Cloud el sistema de archivos es efimero;
    estas escrituras no persisten entre reinicios. Para persistencia real
    multiusuario, migrar escenarios.db a un servicio externo (p.ej. Turso).
    """
    alpha = con.execute('SELECT alpha FROM escenarios WHERE escenario_id = ?',
                         (escenario_id,)).fetchone()['alpha']
    con.execute('DELETE FROM resultados WHERE escenario_id = ?', (escenario_id,))
    con.execute("""
        INSERT INTO resultados (
            escenario_id, demanda_veh,
            espera_base_vs, espera_base_vh, demora_base_s,
            cola_max_base, cola_final_base,
            espera_pre_vs, espera_pre_vh, demora_pre_s,
            cola_max_pre, cola_final_pre,
            reduccion_vh, reduccion_pct, reduccion_demora_s,
            reduccion_ajustada_vh)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        escenario_id, res.demanda,
        res.espera_vs, res.espera_vh, res.demora_prom,
        res.cola_max, res.cola_final,
        res.espera_pre_vs, res.espera_pre_vh, res.demora_pre,
        res.cola_max_pre, res.cola_final_pre,
        res.reduccion_vh, res.reduccion_pct, res.reduccion_demora,
        res.reduccion_vh * alpha))
    con.commit()
