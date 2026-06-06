"""Sección 1 — Cruces estudiados: antecedente, selección y justificación."""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces.tipologia import clasificar_catalogo

st.set_page_config(page_title='Cruces estudiados', page_icon='📍', layout='wide')
st.title('1 · Cruces estudiados')
st.caption('Antecedente del corredor, criterio de selección de los cruces a '
           'evaluar y su fundamento técnico.')

con = datos.conectar(); cur = con.cursor()
clasif = clasificar_catalogo(con, ids_corredor={2,4,6,7,8,10,11,12,14})

st.markdown("""
La Línea 2 del Biotrén recorre el eje **Ruta 160** entre San Pedro de la
Paz y Coronel, e intersecta la vialidad mediante 22 cruces a nivel. El
antecedente del corredor reúne, para cada cruce, su ubicación, geometría,
presencia de semáforo, la vía principal sobre la que se emplaza y el
movimiento vial que interactúa con el paso del tren. Sobre esta base se
define el conjunto de cruces que el estudio evalúa.
""")

st.subheader('Antecedente del corredor')
filas = []
for r in cur.execute("""SELECT a.cruce_id, c.nombre, a.comuna, a.pistas_totales,
        a.pistas_mov_estudio, a.tiene_semaforo, a.via_principal, a.calle_lateral,
        a.evaluacion FROM infra.antecedentes_cruce a
        JOIN infra.cruces c ON c.cruce_id=a.cruce_id ORDER BY a.cruce_id""").fetchall():
    filas.append({
        'Cruce': r['nombre'], 'Comuna': r['comuna'],
        'Vía principal': r['via_principal'], 'Calle lateral': r['calle_lateral'],
        'Pistas': r['pistas_totales'], 'Mov. estudio': r['pistas_mov_estudio'],
        'Semáforo': 'Sí' if r['tiene_semaforo'] else 'No',
        'Evaluado': 'Sí' if r['evaluacion'] else '—',
    })
st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

st.subheader('Cruces seleccionados para evaluación')
evaluados = [c for c in clasif.values() if c.admite_reconfiguracion]
st.markdown(f"""
Se evalúan **{len(evaluados)} cruces**, todos emplazados sobre el eje
interurbano Ruta 160 y dotados de semáforo coordinable con el paso del
tren. Ocho se ubican en San Pedro de la Paz y uno en Coronel
(Escuadrón 2). En estos cruces existe un **movimiento lateral
identificable y caracterizado** que cruza la vía férrea, cuya interacción
con la barrera y el ciclo semafórico es la que el proyecto aborda.
""")
ev_df = pd.DataFrame([{
    'Cruce': c.nombre,
    'Comuna': cur.execute("SELECT comuna FROM infra.antecedentes_cruce WHERE cruce_id=?",
                          (c.cruce_id,)).fetchone()[0],
    'Tratamiento': 'Simulación directa' if c.simulable_directo else 'Estimación por tipología',
} for c in evaluados])
st.dataframe(ev_df, use_container_width=True, hide_index=True)

st.subheader('Cruces no incluidos y su fundamento')

st.markdown('**a) Cruces sin semáforo — fuera del alcance del proyecto**')
sin_sem = [c for c in clasif.values() if c.tipologia == 'B']
st.markdown(f"""
{len(sin_sem)} cruces no cuentan con semáforo de tráfico: Las Garzas,
Grau, Escuadrón 1, Escuadrón 3 y Cruz Mora. El proyecto consiste en
integrar la información del tren a la **gestión semafórica**; donde no
existe un controlador sobre el cual operar, la intervención no tiene
objeto. Estos cruces quedan fuera del alcance, sin que ello implique un
juicio sobre su operación, que se rige únicamente por la barrera.
""")

st.markdown('**b) Intersecciones urbanas — requieren información y un enfoque específico**')
urbanos = [c for c in clasif.values() if c.tipologia == 'C']
st.markdown(f"""
{len(urbanos)} cruces semaforizados no se incorporan a esta evaluación.
Siete se ubican en la trama urbana de Coronel (San Francisco, El Plomo,
Volcán Villarrica, Los Molineros, Héroes de la Concepción, Yobilo y Lo
Rojas), sobre vías locales como Av. Manuel Montt y Av. Carlos Prats, no
sobre el eje interurbano. Estas intersecciones operan con **varios
movimientos de la trama vial adyacente**, y sus tiempos de verde responden
a la coordinación de la red urbana local. Para evaluarlos de forma
representativa se requiere la **caracterización de los flujos de los
movimientos que interactúan con el cruce ferroviario** y el detalle de los
**tiempos de verde asignados**, información que no está disponible en esta
etapa.

El caso de **Daniel Belmar** responde a una razón distinta y definitiva.
El Puente Industrial se encuentra **operativo desde fines de 2025**, y la
redistribución de flujos asociada a su apertura **ya está reflejada en los
aforos vigentes**. En su **etapa final**, este cruce se cerrará al paso
vehicular. No procede, por tanto, evaluar un beneficio sostenido en el
tiempo sobre una operación que cesará. Su flujo residual —aún elevado— se
redistribuirá hacia los cruces vecinos al momento del cierre.
""")

c1, c2, c3, c4 = st.columns(4)
c1.metric('Cruces del corredor', len(clasif))
c2.metric('Evaluados', len(evaluados))
c3.metric('Sin semáforo', len(sin_sem))
c4.metric('Intersecciones urbanas', len(urbanos))

st.subheader('Ubicación de los cruces')
pts = []
for cid in sorted(clasif):
    r = cur.execute("SELECT latitud, longitud FROM infra.cruces WHERE cruce_id=?",
                    (cid,)).fetchone()
    if r and r['latitud'] and r['longitud']:
        pts.append({'lat': r['latitud'], 'lon': r['longitud']})
if pts:
    st.map(pd.DataFrame(pts))

con.close()
