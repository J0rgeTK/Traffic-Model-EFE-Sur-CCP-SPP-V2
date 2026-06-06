"""
Tipologia de cruces y ruteo del modelo de evaluacion
====================================================
El error de fondo de tratar todos los cruces con un unico modelo (paso a
nivel semaforizado sobre arteria) es que NO todos los cruces son ese
arquetipo. Aplicar el modelo de reconfiguracion semaforica a un cruce sin
semaforo, o a una interseccion clasica, produce numeros sin sentido
fisico.

Este modulo clasifica cada cruce en una tipologia y rutea al modelo
apropiado. La cartera del proyecto debe construirse respetando esto: un
cruce solo aporta beneficio del proyecto de reconfiguracion si su
tipologia admite reconfiguracion.

TIPOLOGIAS
----------
A  Paso a nivel SEMAFORIZADO sobre arteria (arquetipo del proyecto)
   - Tiene semaforo coordinable con el HCALL.
   - Existe un movimiento lateral identificable que cruza la via.
   - Modelo: motor cola segundo-a-segundo + Akcelik por banda + balance
     con el movimiento principal. Pre-vaciado y reconfiguracion APLICAN.
   - Si no hay programacion: extrapolar SOLO desde anclas tipo A.

B  Paso a nivel SIN semaforo de trafico (control solo por barrera)
   - No hay controlador SCATS que reprogramar.
   - La reconfiguracion semaforica NO APLICA: beneficio del proyecto = 0.
   - El pre-vaciado tampoco aplica (no hay fase semaforica que anticipar).
   - Modelo: espera por barrera pura (diagnostico), pero el beneficio del
     proyecto de reconfiguracion es nulo. Intervenir aqui seria un
     proyecto distinto (instalar semaforo), con otra evaluacion.

C  Interseccion semaforizada CLASICA (multi-movimiento)
   - Interseccion urbana de varias ramas integrada con el cruce.
   - No existe un movimiento lateral unico que el pre-vaciado beneficie.
   - Modelo: HCM interseccion completa (cap. 19, varios grupos de
     movimiento) o microsimulacion. El modelo de fase lateral no aplica.
   - Se EXCLUYE de la cartera de reconfiguracion (caso San Francisco a
     Lo Rojas).

D  Cruce semaforizado en CORREDOR coordinado (varios en serie)
   - Conceptualmente tipo A, pero la coordinacion entre cruces vecinos
     hace que el modelo aislado sobreestime/subestime. Requiere modelo de
     red (TRANSYT) para ser exacto.
   - Se modela como A con ADVERTENCIA de efecto corredor.
"""
from __future__ import annotations
from dataclasses import dataclass


TIPOLOGIAS = {
    'A': 'Paso a nivel semaforizado sobre arteria',
    'B': 'Paso a nivel sin semaforo (control por barrera)',
    'C': 'Interseccion semaforizada clasica (multi-movimiento)',
    'D': 'Cruce semaforizado en corredor coordinado',
}

MODELO_POR_TIPOLOGIA = {
    'A': 'motor_cola + Akcelik + balance_principal',
    'B': 'espera_barrera (sin reconfiguracion: beneficio proyecto = 0)',
    'C': 'HCM interseccion / microsimulacion (excluido de cartera)',
    'D': 'motor_cola + Akcelik + balance_principal (con efecto corredor)',
}

# El proyecto de reconfiguracion solo entrega beneficio en tipologias A y D.
TIPOLOGIAS_CON_BENEFICIO_PROYECTO = {'A', 'D'}


@dataclass
class ClasificacionCruce:
    cruce_id: int
    nombre: str
    tipologia: str
    modelo_recomendado: str
    admite_reconfiguracion: bool
    simulable_directo: bool       # tiene programacion -> simular
    extrapolable: bool            # tipo A sin prog -> extrapolar
    motivo: str

    def __str__(self) -> str:
        return (f'{self.nombre} [{self.tipologia}] -> '
                f'{self.modelo_recomendado}')


def clasificar(cruce_id: int, nombre: str, tiene_semaforo: bool,
               tiene_programacion: bool, num_pistas: int = 2,
               es_interseccion_clasica: bool = False,
               en_corredor_coordinado: bool = False) -> ClasificacionCruce:
    """Clasifica un cruce en su tipologia y rutea al modelo apropiado.

    `es_interseccion_clasica`: marca del equipo tecnico (caso San
        Francisco a Lo Rojas). Tiene prioridad sobre el resto.
    `en_corredor_coordinado`: cruces en serie que comparten coordinacion
        (p.ej. los de Ruta 160 en San Pedro).
    """
    # Prioridad 1: interseccion clasica -> tipo C (excluida)
    if es_interseccion_clasica:
        return ClasificacionCruce(
            cruce_id, nombre, 'C', MODELO_POR_TIPOLOGIA['C'],
            admite_reconfiguracion=False, simulable_directo=False,
            extrapolable=False,
            motivo='Interseccion clasica multi-movimiento: no existe fase '
                   'lateral unica que el pre-vaciado beneficie. Requiere '
                   'modelo de interseccion completa o microsimulacion.')

    # Prioridad 2: sin semaforo -> tipo B (reconfiguracion no aplica)
    if not tiene_semaforo:
        return ClasificacionCruce(
            cruce_id, nombre, 'B', MODELO_POR_TIPOLOGIA['B'],
            admite_reconfiguracion=False, simulable_directo=False,
            extrapolable=False,
            motivo='Sin semaforo de trafico: no hay controlador SCATS que '
                   'reconfigurar. El proyecto de reconfiguracion no aplica; '
                   'su beneficio en este cruce es nulo.')

    # Tipo A o D segun corredor
    tip = 'D' if en_corredor_coordinado else 'A'
    return ClasificacionCruce(
        cruce_id, nombre, tip, MODELO_POR_TIPOLOGIA[tip],
        admite_reconfiguracion=True,
        simulable_directo=tiene_programacion,
        extrapolable=not tiene_programacion,
        motivo=('Paso a nivel semaforizado: reconfiguracion aplica. '
                + ('Simular directamente (tiene programacion).'
                   if tiene_programacion
                   else 'Sin programacion: extrapolar desde anclas tipo A/D.')
                + (' En corredor coordinado: el modelo aislado puede '
                   'sobre/subestimar; validar con modelo de red.'
                   if tip == 'D' else '')))


def clasificar_catalogo(con, ids_interseccion_clasica: set | None = None,
                        ids_corredor: set | None = None
                        ) -> dict[int, ClasificacionCruce]:
    """Clasifica los cruces a partir del antecedente oficial del corredor.

    La seleccion de cruces a evaluar proviene del antecedente (tabla
    `infra.antecedentes_cruce`, columna `evaluacion`). La tipologia y el
    motivo tecnico se derivan de los atributos del antecedente: presencia
    de semaforo y via principal sobre la que se emplaza el cruce.

    Criterios:
      - Evaluado (evaluacion=1): cruce semaforizado sobre el eje
        interurbano (Ruta 160), con un movimiento lateral caracterizado
        que interactua con el paso del tren. Tipologia A/D.
      - Sin semaforo: fuera del alcance del proyecto. Tipologia B.
      - Semaforizado fuera del eje interurbano (trama urbana de Coronel) o
        sin caracterizacion de flujos del movimiento de estudio:
        interseccion urbana que requiere un levantamiento de informacion y
        un modelo especifico. Tipologia C.
    """
    ids_corredor = ids_corredor or set()
    cur = con.cursor()
    con_prog = set(r[0] for r in cur.execute(
        "SELECT DISTINCT cruce_id FROM infra.planes_horarios_cruce").fetchall())
    # Antecedente oficial
    ant = {r['cruce_id']: r for r in cur.execute(
        "SELECT * FROM infra.antecedentes_cruce").fetchall()}

    out: dict[int, ClasificacionCruce] = {}
    for r in cur.execute("SELECT cruce_id,nombre,tiene_semaforo,num_pistas_total "
                         "FROM infra.cruces ORDER BY cruce_id").fetchall():
        cid = r['cruce_id']
        a = ant.get(cid)
        tiene_sem = bool(a['tiene_semaforo']) if a else bool(r['tiene_semaforo'])
        evaluado = bool(a['evaluacion']) if a else False
        principal = (a['via_principal'] if a else '') or ''
        en_eje_interurbano = 'ruta 160' in principal.lower()

        if not tiene_sem:
            out[cid] = ClasificacionCruce(
                cid, r['nombre'], 'B', MODELO_POR_TIPOLOGIA['B'],
                admite_reconfiguracion=False, simulable_directo=False,
                extrapolable=False,
                motivo='No cuenta con semaforo de trafico: la integracion '
                       'GPS-SCATS no tiene un controlador sobre el cual '
                       'operar. El cruce se encuentra fuera del alcance del '
                       'proyecto.')
        elif evaluado:
            tip = 'D' if cid in ids_corredor else 'A'
            out[cid] = ClasificacionCruce(
                cid, r['nombre'], tip, MODELO_POR_TIPOLOGIA[tip],
                admite_reconfiguracion=True,
                simulable_directo=cid in con_prog,
                extrapolable=cid not in con_prog,
                motivo='Cruce semaforizado sobre el eje interurbano '
                       '(Ruta 160), con un movimiento lateral caracterizado '
                       'que interactua directamente con el paso del tren. '
                       'Reune las condiciones para la evaluacion.')
        else:
            # Semaforizado pero no evaluado: interseccion urbana o sin
            # caracterizacion de flujos del movimiento de estudio.
            if cid == 5:  # Daniel Belmar
                motivo = ('El Puente Industrial se encuentra operativo desde '
                          'fines de 2025 y la redistribucion de flujos '
                          'asociada a su apertura ya esta reflejada en los '
                          'aforos vigentes. En su etapa final este cruce se '
                          'cerrara al paso vehicular, por lo que no procede '
                          'evaluar un beneficio sostenido en el tiempo sobre '
                          'una operacion que cesara. El flujo residual del '
                          'cruce se redistribuira hacia los cruces vecinos al '
                          'momento del cierre.')
            elif en_eje_interurbano:
                motivo = ('Interseccion sobre el eje interurbano cuya '
                          'operacion responde a multiples movimientos de la '
                          'trama vial adyacente. No se dispone de la '
                          'caracterizacion de flujos del movimiento que '
                          'interactua con el cruce ferroviario ni del '
                          'detalle de los tiempos de verde asignados, por lo '
                          'que su evaluacion requiere un levantamiento de '
                          'informacion especifico.')
            else:
                motivo = ('Cruce emplazado sobre la trama vial urbana de '
                          'Coronel (no sobre el eje interurbano). Opera como '
                          'interseccion urbana con varios movimientos, donde '
                          'los tiempos de verde responden a la coordinacion '
                          'de la red local. No se dispone de la '
                          'caracterizacion de flujos de los movimientos que '
                          'interactuan con el cruce ferroviario, condicion '
                          'necesaria para una evaluacion representativa.')
            out[cid] = ClasificacionCruce(
                cid, r['nombre'], 'C', MODELO_POR_TIPOLOGIA['C'],
                admite_reconfiguracion=False, simulable_directo=False,
                extrapolable=False, motivo=motivo)
    return out


def resumen_tipologico(clasificaciones: dict[int, ClasificacionCruce]) -> str:
    """Tabla resumen de la clasificacion tipologica."""
    L = ['Clasificacion tipologica de la cartera', '']
    L.append(f'  {"id":>3s} {"cruce":22s} {"tipo":5s} {"reconfig?":10s} {"ruta del modelo":45s}')
    for cid in sorted(clasificaciones):
        c = clasificaciones[cid]
        rec = 'si' if c.admite_reconfiguracion else 'NO'
        ruta = ('simular' if c.simulable_directo else
                'extrapolar' if c.extrapolable else
                'excluir/otro modelo')
        L.append(f'  {cid:>3d} {c.nombre[:22]:22s} {c.tipologia:5s} '
                 f'{rec:10s} {c.modelo_recomendado[:45]:45s}')
    # Conteo por tipologia
    from collections import Counter
    cnt = Counter(c.tipologia for c in clasificaciones.values())
    L.append('')
    L.append('  Conteo: ' + ', '.join(f'{TIPOLOGIAS[t]}: {n}'
                                        for t, n in sorted(cnt.items())))
    return '\n'.join(L)
