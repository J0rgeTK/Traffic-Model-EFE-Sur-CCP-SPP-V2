"""Sección 5 — Simulación de la operación de un cruce."""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import calcular_beneficio

st.set_page_config(page_title='Simulación', page_icon='🚦', layout='wide')
st.title('5 · Simulación de la operación de un cruce')
st.caption('Reproduce la operación semáforo–barrera y cuantifica la espera en '
           'la vía lateral en tres situaciones, con corrección de saturación.')

con = datos.conectar()
cruces = [c.cruce for c in datos.catalogo_simulable(con)]
camp = datos.listar_campanias(con)[0]
CAMP_ID, CAMP_NOM = camp['campania_id'], camp['nombre']
con.close()


@st.cache_data(show_spinner='Simulando el cruce…')
def evaluar(cruce: str, campania_id: int) -> dict:
    """Evalúa un cruce una sola vez y cachea el resultado (serializable)."""
    con = datos.conectar()
    try:
        return datos.evaluar_cruce_corregido(con, cruce, campania_id=campania_id)
    finally:
        con.close()


with st.sidebar:
    cruce = st.selectbox('Cruce', cruces)
    ocupacion = st.slider('Ocupación vehículo liviano (pax/veh)', 1.0, 2.5, 1.5, 0.1)
    st.caption(f'Flujos: {CAMP_NOM}.')
    st.caption('Usa la programación semafórica, el número de pistas del '
               'movimiento de estudio y el itinerario ferroviario del cruce.')

ec = evaluar(cruce, CAMP_ID)

st.subheader(f'Resultados — {cruce}')
c = st.columns(3)
c[0].metric('Situación actual', f'{ec["espera_actual_vh"]:,.0f} v·h/día',
            'sin modificación')
c[1].metric('Base optimizada', f'{ec["espera_sbo_vh"]:,.0f} v·h/día',
            'reconfiguración semafórica')
c[2].metric('Con proyecto (GPS–SCATS)', f'{ec["espera_proyecto_vh"]:,.0f} v·h/día',
            'reconfiguración + pre-vaciado')

st.markdown(f"""
La **situación actual** es la operación vigente del cruce. La **base
optimizada** incorpora la reconfiguración semafórica (situación sin
proyecto). La situación **con proyecto** suma la integración GPS–SCATS. Las
esperas están corregidas por la formulación de saturación del HCM, con el
número de pistas del movimiento de estudio ({ec['n_carriles']:.0f}). El
beneficio atribuible al proyecto es el incremental del GPS sobre la base:
**{ec['ahorro_gps_incremental_vh']:,.1f} v·h/día**; el de la
reconfiguración es **{ec['ahorro_reconfiguracion_vh']:,.1f} v·h/día**.
""")

# Régimen de saturación (reutiliza las bandas ya calculadas)
st.subheader('Régimen de saturación por banda horaria')
if ec['banda_critica']:
    st.caption(f'Banda más cargada: {ec["banda_critica"][0]:02.0f}:00–'
               f'{ec["banda_critica"][1]:02.0f}:00, grado de saturación '
               f'x = {ec["x_max"]:.2f} · método: {ec["metodo"]}')
if ec['bandas']:
    banda_df = pd.DataFrame([{
        'Hora': f'{b["hora_inicio"]:02.0f}–{b["hora_fin"]:02.0f}h',
        'Flujo (v/h)': round(b['flujo_h']), 'Capacidad (v/h)': round(b['capacidad_h']),
        'Saturación x': round(b['x'], 2), 'Régimen': b['metodo'].split(' (')[0],
    } for b in ec['bandas']])
    st.dataframe(banda_df, use_container_width=True, hide_index=True)

# Beneficio incremental valorizado
ben = calcular_beneficio(ec['ahorro_gps_incremental_vh'], ocupacion=ocupacion,
                         factor_espera=1.0)
st.subheader('Beneficio incremental del proyecto en este cruce')
c = st.columns(2)
c[0].metric('Ahorro anual', f'{ben.ahorro_anual_veh_h:,.0f} v·h/año')
c[1].metric('Beneficio social anual', f'CLP {ben.beneficio_anual_clp:,.0f}',
            'valor social del tiempo')

# Evolución de la cola (reutiliza las series ya calculadas)
if ec['serie_hora']:
    st.subheader('Cola en la vía lateral a lo largo del día')
    chart_df = pd.DataFrame({'hora': ec['serie_hora'],
        'situación actual': ec['serie_q_actual'],
        'base optimizada': ec['serie_q_sbo'],
        'con proyecto': ec['serie_q_proyecto']}).set_index('hora')
    st.line_chart(chart_df)
    st.caption('Las esperas mostradas arriba están corregidas por saturación; '
               'la curva ilustra la dinámica de la cola simulada.')
