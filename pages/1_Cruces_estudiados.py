"""Sección 1 — Cruces estudiados: catálogo, tipología y ubicación."""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces.tipologia import clasificar_catalogo, TIPOLOGIAS

st.set_page_config(page_title='Cruces estudiados', page_icon='📍', layout='wide')
st.title('1 · Cruces estudiados')
st.caption('Universo de cruces del corredor, su tipología operacional y la '
           'definición del alcance de evaluación.')

con = datos.conectar()
clasif = clasificar_catalogo(con, ids_corredor={2,4,6,7,8,10,11,12})

st.markdown("""
El corredor de la Línea 2 del Biotrén concentra los cruces a nivel
semaforizados de mayor fricción entre el modo ferroviario y el vial. Cada
cruce se clasifica según su **tipología operacional**, que determina el
modelo de evaluación aplicable. No todos los cruces admiten el mismo
tratamiento: un paso a nivel semaforizado sobre una arteria, un cruce
controlado solo por barrera y una intersección urbana clásica responden a
lógicas distintas.
""")

st.subheader('Tipologías operacionales')
tip_df = pd.DataFrame([
    {'Tipo': 'A', 'Descripción': TIPOLOGIAS['A'],
     'Admite el proyecto': 'Sí', 'Modelo': 'Simulación segundo a segundo + saturación'},
    {'Tipo': 'B', 'Descripción': TIPOLOGIAS['B'],
     'Admite el proyecto': 'No', 'Modelo': 'Fuera de alcance (sin semáforo)'},
    {'Tipo': 'C', 'Descripción': TIPOLOGIAS['C'],
     'Admite el proyecto': 'No', 'Modelo': 'Intersección completa (evaluación separada)'},
    {'Tipo': 'D', 'Descripción': TIPOLOGIAS['D'],
     'Admite el proyecto': 'Sí', 'Modelo': 'Simulación + saturación (corredor coordinado)'},
])
st.dataframe(tip_df, use_container_width=True, hide_index=True)

st.subheader('Catálogo de cruces y clasificación')
cur = con.cursor()
con_prog = set(r[0] for r in cur.execute(
    "SELECT DISTINCT cruce_id FROM infra.planes_horarios_cruce").fetchall())
filas = []
for cid in sorted(clasif):
    c = clasif[cid]
    r = cur.execute("SELECT comuna, tiene_semaforo, num_pistas_total "
                    "FROM infra.cruces WHERE cruce_id=?", (cid,)).fetchone()
    comuna = r['comuna'] or '—'
    ruta = ('Simulación directa' if c.simulable_directo else
            'Estimación por tipología' if c.extrapolable else
            'Fuera de alcance' if c.tipologia == 'B' else
            'Evaluación separada')
    filas.append({
        'ID': cid, 'Cruce': c.nombre, 'Comuna': comuna,
        'Tipología': c.tipologia, 'Semáforo': 'Sí' if r['tiene_semaforo'] else 'No',
        'Pistas': r['num_pistas_total'], 'Tratamiento': ruta,
    })
df = pd.DataFrame(filas)
st.dataframe(df, use_container_width=True, hide_index=True)

c1, c2, c3, c4 = st.columns(4)
from collections import Counter
cnt = Counter(c.tipologia for c in clasif.values())
c1.metric('Tipo A/D (evaluables)', cnt.get('A', 0) + cnt.get('D', 0))
c2.metric('Tipo B (sin semáforo)', cnt.get('B', 0))
c3.metric('Tipo C (intersección)', cnt.get('C', 0))
c4.metric('Total corredor', len(clasif))

st.subheader('Ubicación de los cruces')
try:
    pts = []
    for cid in sorted(clasif):
        r = cur.execute("SELECT lat, lon, nombre FROM infra.cruces WHERE cruce_id=?",
                        (cid,)).fetchone()
        if r and r['lat'] and r['lon']:
            pts.append({'lat': r['lat'], 'lon': r['lon']})
    if pts:
        st.map(pd.DataFrame(pts))
    else:
        st.info('Coordenadas no disponibles en la base de datos para el mapa.')
except Exception:
    st.info('Coordenadas no disponibles en la base de datos para el mapa.')

con.close()
