"""
Validadores
===========
Reglas de integridad que deben cumplirse antes de confiar en las bases.
Cada validador devuelve una lista de `Hallazgo`. `validar_todo` agrega
todos y permite separar errores (bloquean) de advertencias.
"""
from __future__ import annotations
import sqlite3
from dataclasses import dataclass

from .catalogo import construir_catalogo

ERROR, ADVERTENCIA = 'error', 'advertencia'
FLUJO_MAX_PLAUSIBLE = 6000.0   # veh/h por banda; sobre esto, sospechar k_dem aplicado


@dataclass
class Hallazgo:
    nivel: str          # ERROR | ADVERTENCIA
    regla: str
    detalle: str

    def __str__(self) -> str:
        marca = '✗' if self.nivel == ERROR else '⚠'
        return f'{marca} [{self.regla}] {self.detalle}'


def val_fases(con: sqlite3.Connection) -> list[Hallazgo]:
    """cum_inicio_s < cum_fin_s <= ciclo_s ; ciclo y duracion positivos."""
    h = []
    for r in con.execute(
            'SELECT version_prog_id v, cruce_id c, plan_id p, fase_id f, '
            'duracion_s d, cum_inicio_s ci, cum_fin_s cf, ciclo_s cy '
            'FROM infra.programacion_fases'):
        ref = f'v{r[0]} cruce {r[1]} plan {r[2]} fase {r[3]}'
        if not (r[5] < r[6] <= r[7]):
            h.append(Hallazgo(ERROR, 'fases.rango',
                              f'{ref}: cum_inicio<{r[5]}> cum_fin<{r[6]}> '
                              f'ciclo<{r[7]}> no cumple ci<cf<=ciclo'))
        if r[4] <= 0 or r[7] <= 0:
            h.append(Hallazgo(ERROR, 'fases.positivo',
                              f'{ref}: duracion<{r[4]}> o ciclo<{r[7]}> no positivo'))
    return h


def val_planes_sin_solape(con: sqlite3.Connection) -> list[Hallazgo]:
    """Los planes horarios por (version, cruce, tipo_dia) sin superposicion."""
    h = []
    grupos = con.execute(
        'SELECT DISTINCT version_prog_id, cruce_id, tipo_dia '
        'FROM infra.planes_horarios_cruce').fetchall()
    for vid, cid, td in grupos:
        rows = con.execute(
            'SELECT hora_inicio_s, hora_fin_s, plan_id '
            'FROM infra.planes_horarios_cruce '
            'WHERE version_prog_id=? AND cruce_id=? AND tipo_dia=? '
            'ORDER BY hora_inicio_s', (vid, cid, td)).fetchall()
        for a, b in zip(rows, rows[1:]):
            if b[0] < a[1]:
                h.append(Hallazgo(ERROR, 'planes.solape',
                                  f'v{vid} cruce {cid} {td}: plan {a[2]} '
                                  f'(fin {a[1]}s) se solapa con plan {b[2]}'
                                  f' (inicio {b[0]}s)'))
    return h


def val_plan_tiene_fases(con: sqlite3.Connection) -> list[Hallazgo]:
    """Cada plan referido en planes_horarios_cruce debe tener fases definidas."""
    h = []
    for vid, cid, plan in con.execute(
            'SELECT DISTINCT version_prog_id, cruce_id, plan_id '
            'FROM infra.planes_horarios_cruce'):
        n = con.execute('SELECT count(*) FROM infra.programacion_fases '
                        'WHERE version_prog_id=? AND cruce_id=? AND plan_id=?',
                        (vid, cid, plan)).fetchone()[0]
        if n == 0:
            h.append(Hallazgo(ERROR, 'plan.sin_fases',
                              f'v{vid} cruce {cid} plan {plan}: sin fases'))
    return h


def val_hcall(con: sqlite3.Connection) -> list[Hallazgo]:
    """hcall_in <= hcall_out en todos los eventos de barrera."""
    n = con.execute('SELECT count(*) FROM dem.eventos_barrera '
                    'WHERE hcall_in_s > hcall_out_s').fetchone()[0]
    return [] if n == 0 else [Hallazgo(
        ERROR, 'hcall.orden', f'{n} eventos con hcall_in > hcall_out')]


def val_flujos_crudos(con: sqlite3.Connection) -> list[Hallazgo]:
    """Los flujos deben estar CRUDOS (sin k_dem) y en rango plausible."""
    h = []
    neg = con.execute('SELECT count(*) FROM dem.llegadas_vehiculares '
                      'WHERE flujo_veh_h < 0').fetchone()[0]
    if neg:
        h.append(Hallazgo(ERROR, 'flujo.negativo', f'{neg} flujos negativos'))
    alto = con.execute('SELECT count(*) FROM dem.llegadas_vehiculares '
                       'WHERE flujo_veh_h > ?', (FLUJO_MAX_PLAUSIBLE,)).fetchone()[0]
    if alto:
        h.append(Hallazgo(ADVERTENCIA, 'flujo.crudo',
                          f'{alto} flujos > {FLUJO_MAX_PLAUSIBLE:.0f} veh/h: '
                          'revisar que no traigan k_dem ya aplicado'))
    return h


def val_simulables(con: sqlite3.Connection) -> list[Hallazgo]:
    """Todo cruce simulable debe tener programacion, flujo y eventos HCALL."""
    h = []
    for c in construir_catalogo(con):
        falta = []
        if not c.variantes:
            falta.append('programacion')
        if not con.execute('SELECT 1 FROM dem.llegadas_vehiculares '
                           'WHERE cruce_id=? LIMIT 1', (c.cruce_id,)).fetchone():
            falta.append('flujo')
        if not con.execute('SELECT 1 FROM dem.eventos_barrera '
                           'WHERE cruce_id=? LIMIT 1', (c.cruce_id,)).fetchone():
            falta.append('eventos HCALL')
        if c.simulable and falta:
            h.append(Hallazgo(ERROR, 'cruce.incompleto',
                              f'{c.cruce}: marcado simulable pero falta '
                              + ', '.join(falta)))
    return h


def val_escenarios(con: sqlite3.Connection) -> list[Hallazgo]:
    """Cada escenario debe apuntar a un cruce existente con datos."""
    h = []
    cruces = {r[0] for r in con.execute('SELECT cruce_id FROM infra.cruces')}
    for eid, cid, nom in con.execute(
            'SELECT escenario_id, cruce_id, nombre FROM escenarios'):
        if cid not in cruces:
            h.append(Hallazgo(ERROR, 'escenario.cruce',
                              f'escenario {eid} ({nom}): cruce_id {cid} inexistente'))
    return h


def val_proyecto_no_simulable(con: sqlite3.Connection) -> list[Hallazgo]:
    """Reporta cruces declarados en el proyecto pero que no se pueden simular."""
    h = []
    for c in construir_catalogo(con):
        if c.en_proyecto and not c.simulable:
            cod = c.proyecto.codigo_proyecto or '—'
            falta = []
            if not c.variantes:
                falta.append('programación base')
            if not con.execute('SELECT 1 FROM dem.llegadas_vehiculares '
                               'WHERE cruce_id=? LIMIT 1', (c.cruce_id,)).fetchone():
                falta.append('aforos')
            if not con.execute('SELECT 1 FROM dem.eventos_barrera '
                               'WHERE cruce_id=? LIMIT 1', (c.cruce_id,)).fetchone():
                falta.append('eventos HCALL')
            h.append(Hallazgo(ADVERTENCIA, 'proyecto.no_simulable',
                              f'{c.cruce} (código {cod}): declarado en el '
                              'proyecto pero falta ' + ', '.join(falta)))
    return h


VALIDADORES = [
    val_fases, val_planes_sin_solape, val_plan_tiene_fases,
    val_hcall, val_flujos_crudos, val_simulables, val_escenarios,
    val_proyecto_no_simulable,
]


def validar_todo(con: sqlite3.Connection) -> list[Hallazgo]:
    """Ejecuta todos los validadores y concatena los hallazgos."""
    out: list[Hallazgo] = []
    for v in VALIDADORES:
        out.extend(v(con))
    return out


def resumen(hallazgos: list[Hallazgo]) -> dict:
    return {
        'errores': sum(1 for x in hallazgos if x.nivel == ERROR),
        'advertencias': sum(1 for x in hallazgos if x.nivel == ADVERTENCIA),
        'ok': all(x.nivel != ERROR for x in hallazgos),
    }
