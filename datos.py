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
from modelo_cruces import catalogo as _catalogo
from modelo_cruces.modelos import Variante, CatalogoCruce

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
#  catalogo de variantes por cruce  (que modelo corresponde a cada uno)
# --------------------------------------------------------------------- #
def catalogo(con) -> list[CatalogoCruce]:
    """Catalogo completo: cada cruce con sus variantes aplicables."""
    return _catalogo.construir_catalogo(con)


def catalogo_simulable(con) -> list[CatalogoCruce]:
    """Solo cruces simulables (con aforo y eventos de barrera)."""
    return _catalogo.catalogo_simulable(con)


def inputs_de_variante(con, var: Variante, **overrides) -> Inputs:
    """Construye Inputs para una variante del catalogo.

    La variante determina la version de programacion y el comportamiento
    post-HCALL (False = base, True = reconfiguracion = salto a verde lateral).
    """
    params = dict(version_prog_id=var.version_prog_id,
                  post_hcall_lateral=var.post_hcall_lateral)
    params.update(overrides)
    return construir_inputs(con, var.cruce, **params)


def simular_proyecto(con, cruce: str, **opts) -> dict:
    """Simula la operacion actual vs el proyecto completo para un cruce.

    Devuelve un dict con las cuatro situaciones del modelo:
      actual            -> base sin pre-vaciado     (variante base, espera_vh)
      solo_prevaciado   -> base con pre-vaciado     (variante base, espera_pre_vh)
      solo_reconfig     -> reconfig sin pre-vaciado (variante reconfig, espera_vh)
      proyecto          -> reconfig con pre-vaciado (variante reconfig, espera_pre_vh)
    Si el cruce NO esta declarado, solo_reconfig y proyecto coinciden con
    solo_prevaciado (no hay reconfiguracion que aplicar).

    Tambien entrega el ahorro descompuesto:
      ahorro_total      = actual - proyecto
      aporte_prevaciado = actual - solo_prevaciado
      aporte_reconfig   = solo_prevaciado - proyecto
    """
    from modelo_cruces import Simulador
    from modelo_cruces.catalogo import buscar, construir_catalogo
    from modelo_cruces.saturacion import analizar as analizar_sat

    c = buscar(construir_catalogo(con), cruce)
    if c is None or not c.simulable:
        raise ValueError(f'Cruce no simulable: {cruce}')
    v_base = c.variante('base')
    v_rec  = c.variante('reconfiguracion') or v_base    # fallback

    rb = Simulador(inputs_de_variante(con, v_base, **opts)).run(mode='corrected',
                                                                keep_series=True)
    if v_rec is v_base:
        rr = rb
    else:
        rr = Simulador(inputs_de_variante(con, v_rec, **opts)).run(
            mode='corrected', keep_series=True)

    actual          = rb.espera_vh
    solo_prevaciado = rb.espera_pre_vh
    solo_reconfig   = rr.espera_vh
    proyecto        = rr.espera_pre_vh
    ahorro_total      = actual - proyecto
    aporte_prevaciado = actual - solo_prevaciado
    aporte_reconfig   = solo_prevaciado - proyecto

    # Analisis Akcelik (saturacion por banda horaria)
    try:
        sat_actual   = analizar_sat(rb, n_carriles=2.0, usar_pre=False)
        sat_proyecto = analizar_sat(rr, n_carriles=2.0, usar_pre=True)
    except Exception:
        sat_actual = sat_proyecto = None

    return {
        'cruce': cruce, 'tiene_reconfig': v_rec is not v_base,
        'actual': actual, 'solo_prevaciado': solo_prevaciado,
        'solo_reconfig': solo_reconfig, 'proyecto': proyecto,
        'ahorro_total': ahorro_total,
        'reduccion_pct': ahorro_total / actual if actual > 0 else 0,
        'aporte_prevaciado': aporte_prevaciado,
        'aporte_reconfig': aporte_reconfig,
        'demanda': rb.demanda, 'cola_final_actual': rb.cola_final,
        'serie_actual': rb.series, 'serie_proyecto': rr.series,
        'saturacion_actual': sat_actual, 'saturacion_proyecto': sat_proyecto,
    }


# --------------------------------------------------------------------- #
#  construccion de Inputs para el motor
# --------------------------------------------------------------------- #
def construir_inputs(con, cruce: str, version_prog_id: int | None = None,
                     campania_id: int = 1, itinerario_id: int = 1,
                     hora_inicio_s: int = 21600, hora_fin_s: int = 75600,
                     h: float = 2.0, n_carriles: float = 2.0,
                     buffer: int = 0, k_dem: float = 1.1,
                     post_hcall_lateral: bool = False,
                     tipo_dia: str = 'Laboral') -> Inputs:
    """Arma un objeto Inputs leyendo los insumos desde las bases.

    Si `version_prog_id` es None, se resuelve desde `modelo_operacional_cruce`
    (cada cruce esta asignado a la version que le corresponde: v1 NOREPROG
    o v2 RECONFIG). `tipo_dia` selecciona la malla horaria (Laboral por
    defecto, Sabado o Domingo/Festivo).

    El flujo en la base es CRUDO; el motor aplica k_dem. Para reproducir
    replicar el caso de referencia historico usar k_dem=1.1. `post_hcall_lateral=True` activa la
    reconfiguracion (salto al verde lateral al terminar HCALL).
    """
    cid = con.execute('SELECT cruce_id FROM infra.cruces WHERE nombre = ?',
                       (cruce,)).fetchone()
    if cid is None:
        raise ValueError(f'Cruce no encontrado: {cruce}')
    cid = cid['cruce_id']

    if version_prog_id is None:
        row = con.execute('SELECT version_prog_id FROM '
                          'infra.modelo_operacional_cruce WHERE cruce_id=?',
                          (cid,)).fetchone()
        version_prog_id = row['version_prog_id'] if row else 1

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
        'SELECT * FROM infra.planes_horarios_cruce '
        'WHERE version_prog_id=? AND cruce_id=? AND tipo_dia=? '
        'ORDER BY hora_inicio_s', (version_prog_id, cid, tipo_dia))]

    llegadas = [{
        'cruce': cruce, 't_ini': r['t_inicio_s'], 't_fin': r['t_fin_s'],
        'lambda': r['flujo_veh_h'] / 3600.0,
    } for r in con.execute(
        'SELECT * FROM dem.llegadas_vehiculares '
        'WHERE campania_id=? AND cruce_id=? AND tipo_dia=?',
        (campania_id, cid, tipo_dia))]

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
        post_hcall_lateral=post_hcall_lateral,
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


# ----------------------------------------------------------------------
#  Evaluacion coherente de un cruce (correccion de saturacion unificada)
# ----------------------------------------------------------------------
def evaluar_cruce_corregido(con, nombre: str, campania_id: int = 3,
                            n_carriles: float | None = None,
                            hora_inicio_s: int = 6 * 3600,
                            hora_fin_s: int = 24 * 3600) -> dict:
    """Evalua un cruce aplicando la correccion de saturacion de forma
    coherente entre las tres situaciones (actual, base optimizada, proyecto).

    Criterio metodologico:
      - El beneficio de la RECONFIGURACION se calcula como la diferencia de
        esperas corregidas por la formulacion del HCM (Webster + Akcelik):
        e_akcelik(actual) - e_akcelik(base). La correccion acota la
        sobreestimacion del modelo de colas en regimen de sobre-saturacion
        y distingue ambas situaciones por la capacidad efectiva resultante
        de la recuperacion tras el cierre de barrera.
      - El beneficio del GPS (pre-vaciado) es un efecto transitorio que la
        formulacion estacionaria del HCM no representa; se obtiene de la
        simulacion segundo a segundo (base con y sin pre-vaciado) y se
        acota por el factor de saturacion del cruce, de modo que no se
        sobreestime en cruces sobre-saturados.
      - El numero de pistas del movimiento de estudio (n_carriles) se toma
        del antecedente del cruce, no de un valor uniforme.
    """
    from modelo_cruces import Simulador, analizar_saturacion
    from modelo_cruces.catalogo import buscar, construir_catalogo

    cat = construir_catalogo(con)
    c = buscar(cat, nombre)
    if n_carriles is None:
        row = con.execute(
            "SELECT num_carriles_lateral FROM infra.cruces WHERE nombre = ?",
            (nombre,)).fetchone()
        n_carriles = (row['num_carriles_lateral'] if row else 2.0) or 2.0

    vb = c.variante('base')
    vr = c.variante('reconfiguracion') or vb
    rb = Simulador(inputs_de_variante(con, vb, campania_id=campania_id, k_dem=1.0,
        hora_inicio_s=hora_inicio_s, hora_fin_s=hora_fin_s)).run(
        mode='corrected', keep_series=True)
    rr = Simulador(inputs_de_variante(con, vr, campania_id=campania_id, k_dem=1.0,
        hora_inicio_s=hora_inicio_s, hora_fin_s=hora_fin_s)).run(
        mode='corrected', keep_series=True)

    sa_act = analizar_saturacion(rb, n_carriles=n_carriles, usar_pre=False)
    sa_sbo = analizar_saturacion(rr, n_carriles=n_carriles, usar_pre=False)

    e_actual = sa_act.espera_akcelik_total_vh
    e_sbo = sa_sbo.espera_akcelik_total_vh
    ahorro_reconfig = max(0.0, e_actual - e_sbo)

    factor = (min(1.0, sa_sbo.espera_akcelik_total_vh / sa_sbo.espera_motor_total_vh)
              if sa_sbo.espera_motor_total_vh else 1.0)
    ahorro_gps = max(0.0, rr.espera_vh - rr.espera_pre_vh) * factor
    e_proyecto = max(0.0, e_sbo - ahorro_gps)

    return {
        'cruce': nombre, 'n_carriles': n_carriles, 'x_max': sa_act.x_max,
        'metodo': sa_act.metodo_recomendado,
        'espera_actual_vh': e_actual, 'espera_sbo_vh': e_sbo,
        'espera_proyecto_vh': e_proyecto,
        'ahorro_reconfiguracion_vh': ahorro_reconfig,
        'ahorro_gps_incremental_vh': ahorro_gps,
        'factor_saturacion': factor,
        'espera_motor_actual_vh': sa_act.espera_motor_total_vh,
    }
