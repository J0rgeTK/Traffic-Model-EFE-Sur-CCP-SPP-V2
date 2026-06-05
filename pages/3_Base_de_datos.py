"""Sección 3 — Base de datos: estructura y contenido."""
import pandas as pd
import streamlit as st

import datos

st.set_page_config(page_title='Base de datos', page_icon='🗄️', layout='wide')
st.title('3 · Base de datos')
st.caption('Estructura y contenido de la información que alimenta el modelo.')

st.markdown("""
El programa organiza la información del corredor en bases de datos
relacionales separadas por dominio. Este diseño permite un procesamiento
eficiente y trazable: cada dato tiene una fuente y una ubicación
definidas, y las consultas combinan los dominios según se necesite.
""")

con = datos.conectar()
cur = con.cursor()

st.subheader('Dominios de datos')
st.dataframe(pd.DataFrame([
    {'Dominio': 'Infraestructura', 'Contenido': 'Cruces, semáforos, '
     'programaciones semafóricas, modelo operacional, geometría.'},
    {'Dominio': 'Demanda', 'Contenido': 'Flujos vehiculares por cruce, '
     'banda horaria y tipo de día; campañas de medición.'},
    {'Dominio': 'Operación ferroviaria', 'Contenido': 'Itinerario del '
     'servicio, pasadas por cruce, tiempos de cierre de barrera (HCALL).'},
], columns=['Dominio', 'Contenido']),
    use_container_width=True, hide_index=True)

# Flujos vehiculares
st.subheader('Flujos vehiculares')
camps = datos.listar_campanias(con)
camp_sel = st.selectbox('Campaña de medición',
                        [(r['campania_id'], r['nombre']) for r in camps],
                        format_func=lambda x: x[1])
cid_camp = camp_sel[0]
rows = cur.execute(
    "SELECT cruce_id, COUNT(*) n, MIN(flujo_veh_h) mn, MAX(flujo_veh_h) mx, "
    "AVG(flujo_veh_h) av FROM dem.llegadas_vehiculares WHERE campania_id=? "
    "GROUP BY cruce_id ORDER BY cruce_id", (cid_camp,)).fetchall()
if rows:
    nombres = {r['cruce_id']: r['nombre'] for r in
               cur.execute("SELECT cruce_id, nombre FROM infra.cruces").fetchall()}
    df = pd.DataFrame([{
        'Cruce': nombres.get(r['cruce_id'], f"#{r['cruce_id']}"),
        'Bandas horarias': r['n'],
        'Flujo mín (v/h)': round(r['mn']),
        'Flujo máx (v/h)': round(r['mx']),
        'Flujo medio (v/h)': round(r['av']),
    } for r in rows])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f'{len(rows)} cruces con flujo medido en esta campaña, '
               'desagregado por banda horaria de una hora.')
else:
    st.info('Sin flujos cargados para esta campaña.')

# Programaciones semafóricas
st.subheader('Programaciones semafóricas')
prog = cur.execute(
    "SELECT cruce_id, COUNT(*) n FROM infra.planes_horarios_cruce "
    "GROUP BY cruce_id ORDER BY cruce_id").fetchall()
if prog:
    nombres = {r['cruce_id']: r['nombre'] for r in
               cur.execute("SELECT cruce_id, nombre FROM infra.cruces").fetchall()}
    dfp = pd.DataFrame([{
        'Cruce': nombres.get(r['cruce_id'], f"#{r['cruce_id']}"),
        'Planes horarios registrados': r['n'],
    } for r in prog])
    st.dataframe(dfp, use_container_width=True, hide_index=True)
    st.caption(f'{len(prog)} cruces con programación semafórica registrada '
               '(ciclo, fases y repartos por tipo de día).')
else:
    st.info('Sin programaciones registradas.')

# Itinerario ferroviario
st.subheader('Operación ferroviaria')
try:
    n_serv = cur.execute("SELECT COUNT(*) FROM dem.itinerario").fetchone()[0]
    st.metric('Servicios en el itinerario de referencia', n_serv)
except Exception:
    st.caption('El itinerario ferroviario de referencia (marzo) define las '
               'pasadas del tren por cada cruce y el tiempo de cierre de '
               'barrera asociado a cada pasada.')

con.close()
