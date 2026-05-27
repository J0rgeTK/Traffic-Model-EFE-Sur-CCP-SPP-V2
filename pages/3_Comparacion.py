"""Página de comparación: contrasta cruces y evidencia el error del Excel."""
import pandas as pd
import streamlit as st

import datos
from motor_sim import Simulador

st.set_page_config(page_title='Comparación', page_icon='📊', layout='wide')
st.title('Comparación de cruces')

con = datos.conectar()
cruces = datos.cruces_simulables(con)
versiones = {r['nombre']: r['version_prog_id'] for r in datos.listar_versiones(con)}
campanias = {r['nombre']: r['campania_id'] for r in datos.listar_campanias(con)}

with st.sidebar:
    st.header('Configuración')
    sel = st.multiselect('Cruces a comparar', cruces, default=cruces)
    version = st.selectbox('Programación semafórica', list(versiones))
    campania = st.selectbox('Campaña de aforos', list(campanias))
    k_dem = st.slider('Factor de demanda k_dem', 0.5, 1.5, 1.1, 0.05)
    correr = st.button('Comparar', type='primary', use_container_width=True)

if not correr or not sel:
    st.info('Seleccione cruces y pulse «Comparar».')
    con.close()
    st.stop()


@st.cache_data(show_spinner=False)
def correr(cruce, vp, cm, kd, modo):
    inp = datos.construir_inputs(con, cruce, version_prog_id=vp,
                                 campania_id=cm, k_dem=kd)
    r = Simulador(inp).run(mode=modo)
    return dict(espera_base=r.espera_vh, espera_pre=r.espera_pre_vh,
                reduccion_vh=r.reduccion_vh, reduccion_pct=r.reduccion_pct,
                demora_base=r.demora_prom, cola_final=r.cola_final)


filas = []
for cruce in sel:
    cor = correr(cruce, versiones[version], campanias[campania], k_dem,
                 'corrected')
    fai = correr(cruce, versiones[version], campanias[campania], k_dem,
                 'faithful')
    filas.append({
        'Cruce': cruce,
        'Espera base (veh·h)': round(cor['espera_base'], 1),
        'Espera pre (veh·h)': round(cor['espera_pre'], 1),
        'Reducción corregida (%)': round(cor['reduccion_pct'] * 100, 1),
        'Reducción Excel (%)': round(fai['reduccion_pct'] * 100, 1),
        'Cola final (veh)': round(cor['cola_final'], 1),
    })
df = pd.DataFrame(filas)

st.subheader('Resultados por cruce (modo corregido)')
st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader('Espera: base vs pre-vaciado')
st.bar_chart(df.set_index('Cruce')[['Espera base (veh·h)',
                                    'Espera pre (veh·h)']])

st.subheader('El error de ventana del Excel')
st.caption('La columna «Excel» suma la espera pre-vaciado solo sobre las '
           'primeras 3 h y la base sobre 15 h, inflando la reducción. '
           'La columna «corregida» usa la misma ventana para ambos.')
st.bar_chart(df.set_index('Cruce')[['Reducción corregida (%)',
                                    'Reducción Excel (%)']])

st.download_button(
    'Descargar comparación (CSV)', df.to_csv(index=False).encode('utf-8'),
    file_name='comparacion_cruces.csv', mime='text/csv')

con.close()
