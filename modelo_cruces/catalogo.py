"""
Catalogo de variantes por cruce
================================
Cada cruce declara su modelo de evaluacion. La fuente de verdad ahora es
la tabla `modelo_operacional_cruce` (RECONFIG / NOREPROG) que viene del
archivo de programacion v2.

Variantes generadas:
  - Cruce NOREPROG con fases: [base]                  (1 variante)
  - Cruce RECONFIG con fases: [base, reconfiguracion] (2 variantes)
  - Cruce declarado RECONFIG SIN fases: []            (en catalogo informativo)

La variante base usa post_hcall_lateral=False (salto a fase 1 al
terminar HCALL); la variante reconfiguracion usa post_hcall_lateral=True
(salto al cum_inicio del verde lateral). En ambos casos el motor entrega
la comparacion sin/con pre-vaciado en una unica corrida.
"""
from __future__ import annotations
import sqlite3

from .modelos import (
    CatalogoCruce, Variante, ProyectoReconfig, ROL_BASE, ROL_RECONFIG,
)


def _con_aforo(con) -> set[int]:
    return {r[0] for r in con.execute(
        'SELECT DISTINCT cruce_id FROM dem.llegadas_vehiculares')}


def _con_hcall(con) -> set[int]:
    return {r[0] for r in con.execute(
        'SELECT DISTINCT cruce_id FROM dem.eventos_barrera')}


def _modelo_operacional(con) -> dict:
    """{cruce_id: (tipo_modelo, version_prog_id)} desde modelo_operacional_cruce."""
    try:
        rows = con.execute(
            'SELECT cruce_id, tipo_modelo, version_prog_id '
            'FROM infra.modelo_operacional_cruce').fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r[0]: (r[1], r[2]) for r in rows}


def _proyectos(con) -> dict[int, ProyectoReconfig]:
    try:
        rows = con.execute(
            'SELECT cruce_id, via_principal, codigo_proyecto, '
            'comuna_referencia, fuente FROM infra.cruces_reconfiguracion'
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {r[0]: ProyectoReconfig(via_principal=r[1], codigo_proyecto=r[2],
                                   comuna_referencia=r[3], fuente=r[4])
            for r in rows}


def _con_fases(con, vid_por_cruce: dict) -> set[int]:
    """Cruces que tienen fases cargadas en SU version asignada."""
    out = set()
    for cid, (_, vid) in vid_por_cruce.items():
        n = con.execute('SELECT count(*) FROM infra.programacion_fases '
                        'WHERE cruce_id=? AND version_prog_id=?',
                        (cid, vid)).fetchone()[0]
        if n > 0:
            out.add(cid)
    return out


def construir_catalogo(con: sqlite3.Connection) -> list[CatalogoCruce]:
    """Catalogo derivado de modelo_operacional_cruce + datos disponibles."""
    versiones = {r[0]: r[1] for r in con.execute(
        'SELECT version_prog_id, nombre FROM infra.versiones_programacion')}
    if not versiones:
        return []

    mop = _modelo_operacional(con)
    con_aforo, con_hcall = _con_aforo(con), _con_hcall(con)
    con_fases = _con_fases(con, mop)
    proyectos = _proyectos(con)

    if not mop:
        return []

    catalogo: list[CatalogoCruce] = []
    rows = list(con.execute(
        'SELECT cruce_id, nombre, comuna FROM infra.cruces '
        'WHERE cruce_id IN (%s) ORDER BY cruce_id' %
        ','.join('?' * len(mop)), tuple(mop)))
    for cruce_id, nombre, comuna in rows:
        tipo, vid = mop[cruce_id]
        vnom = versiones.get(vid, '')
        tiene_fases = cruce_id in con_fases
        tiene_pre   = cruce_id in con_hcall
        variantes: list[Variante] = []

        if tiene_fases:
            # Variante base: post-HCALL -> fase 1.
            variantes.append(Variante(
                cruce=nombre, cruce_id=cruce_id, version_prog_id=vid,
                version_nombre=vnom, rol=ROL_BASE,
                tiene_prevaciado=tiene_pre, post_hcall_lateral=False))
            # Variante reconfiguracion: solo si el cruce es RECONFIG.
            if tipo == 'RECONFIG':
                variantes.append(Variante(
                    cruce=nombre, cruce_id=cruce_id, version_prog_id=vid,
                    version_nombre=vnom, rol=ROL_RECONFIG,
                    tiene_prevaciado=tiene_pre, post_hcall_lateral=True))

        simulable = tiene_fases and cruce_id in con_aforo and cruce_id in con_hcall
        catalogo.append(CatalogoCruce(
            cruce=nombre, cruce_id=cruce_id, comuna=comuna,
            simulable=simulable, variantes=variantes,
            proyecto=proyectos.get(cruce_id)))
    return catalogo


def catalogo_simulable(con: sqlite3.Connection) -> list[CatalogoCruce]:
    return [c for c in construir_catalogo(con) if c.simulable]


def buscar(catalogo: list[CatalogoCruce], cruce: str) -> CatalogoCruce | None:
    for c in catalogo:
        if c.cruce == cruce:
            return c
    return None
