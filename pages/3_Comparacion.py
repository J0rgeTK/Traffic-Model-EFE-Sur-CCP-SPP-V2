"""Comparación entre cruces: beneficio actual vs proyecto completo."""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import (
    calcular_beneficio,
    VST_URBANO_VIAJE_2026, DIAS_LABORALES_AÑO, OCUPACION_VEH_DEFAULT,
)

st.set_page_config(page_title='Comparación', page_icon='📊', layout='wide')
st.title('Comparación de cruces — beneficio del proyecto')

con = datos.conectar()
cat = datos.catalogo_simulable(con)
campanias = {r['nombre']: r['campania_id'] for r in datos.listar_campanias(con)}

with st.sidebar:
    st.header('Configuración')
    sel = st.multiselect('Cruces', [c.cruce for c in cat],
                         default=[c.cruce for c in cat])
    campania = st.selectbox('Campaña de aforos', list(campanias))
    tipo_dia = st.radio('Tipo de día', ['Laboral', 'Sabado', 'Domingo/Festivo'])
    k_dem = st.slider('Factor de demanda k_dem', 0.5, 1.5, 1.1, 0.05)
    h_ini, h_fin = st.select_slider(
        'Ventana horaria', options=list(range(0, 25)), value=(6, 24),
        format_func=lambda x: f'{x:02d}:00')
    ocup = st.slider('Ocupación (pax/veh)', 1.0, 3.0,
                     OCUPACION_VEH_DEFAULT, 0.1)
    correr = st.button('Comparar', type='primary', use_container_width=True)

if not correr or not sel:
    st.info('Seleccione cruces y pulse «Comparar». Cada cruce se evalúa '
            'comparando la operación actual contra el proyecto completo '
            '(pre-vaciado + reconfiguración donde aplique).')
    con.close(); st.stop()

filas = []
for cruce in sel:
    p = datos.simular_proyecto(
        con, cruce, campania_id=campanias[campania], k_dem=k_dem,
        hora_inicio_s=h_ini * 3600, hora_fin_s=h_fin * 3600,
        tipo_dia=tipo_dia)
    ben = calcular_beneficio(p['ahorro_total'], ocupacion=ocup)
    filas.append({
        'Cruce': cruce,
        'Reconfig.': 'Sí' if p['tiene_reconfig'] else 'No',
        'Actual (veh·h)': round(p['actual'], 1),
        'Proyecto (veh·h)': round(p['proyecto'], 1),
        'Ahorro diario (veh·h)': round(p['ahorro_total'], 1),
        'Aporte pre-vaciado (veh·h)': round(p['aporte_prevaciado'], 1),
        'Aporte reconfig (veh·h)': round(p['aporte_reconfig'], 1),
        'Reducción (%)': round(p['reduccion_pct'] * 100, 1),
        'Ahorro anual (veh·h)': round(ben.ahorro_anual_veh_h, 0),
        'Beneficio anual (CLP)': round(ben.beneficio_anual_clp, 0),
    })
df = pd.DataFrame(filas)

st.subheader('Tabla de resultados')
st.dataframe(df, use_container_width=True, hide_index=True)

st.subheader('Beneficio social anual por cruce')
st.caption(f'VST urbano viaje MDS 2026 = {VST_URBANO_VIAJE_2026:,} CLP/h-pax · '
           f'{DIAS_LABORALES_AÑO} días · {ocup:g} pax/veh.')
st.bar_chart(df.set_index('Cruce')[['Beneficio anual (CLP)']])

st.subheader('Descomposición del ahorro diario')
st.caption('Cuánto del ahorro viene del pre-vaciado solo y cuánto suma la '
           'reconfiguración. Para cruces sin reconfig, el aporte reconfig es 0.')
st.bar_chart(df.set_index('Cruce')[['Aporte pre-vaciado (veh·h)',
                                    'Aporte reconfig (veh·h)']])

st.subheader('Espera vehicular: actual vs proyecto')
st.bar_chart(df.set_index('Cruce')[['Actual (veh·h)', 'Proyecto (veh·h)']])

total = df['Beneficio anual (CLP)'].sum()
st.metric('Beneficio social TOTAL del conjunto', f'CLP {total:,.0f}',
          f'≈ {total/39727.96:,.0f} UF/año')

st.download_button('Descargar comparación (CSV)',
                   df.to_csv(index=False).encode('utf-8'),
                   file_name='comparacion_proyecto.csv', mime='text/csv')
con.close()
