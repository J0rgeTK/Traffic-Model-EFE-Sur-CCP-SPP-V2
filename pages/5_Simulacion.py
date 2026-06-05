"""Sección 5 — Simulación de la operación de un cruce."""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import (
    Simulador, analizar_saturacion, calcular_beneficio, evaluar_incremental,
)
from modelo_cruces.catalogo import buscar, construir_catalogo

st.set_page_config(page_title='Simulación', page_icon='🚦', layout='wide')
st.title('5 · Simulación de la operación de un cruce')
st.caption('Reproduce segundo a segundo la operación semáforo–barrera y '
           'cuantifica la espera en las vías laterales.')

con = datos.conectar()
cat = {c.cruce: c for c in datos.catalogo_simulable(con)}
camps = {r['nombre']: r['campania_id'] for r in datos.listar_campanias(con)}

with st.sidebar:
    cruce = st.selectbox('Cruce', list(cat))
    campania = st.selectbox('Campaña de flujos', list(camps))
    st.caption('La simulación usa la programación semafórica y el itinerario '
               'ferroviario registrados para el cruce.')

cc = cat[cruce]
vb = cc.variante('base'); vr = cc.variante('reconfiguracion') or vb
ib = datos.inputs_de_variante(con, vb, campania_id=camps[campania], k_dem=1.0,
                              hora_inicio_s=6*3600, hora_fin_s=24*3600)
ir = datos.inputs_de_variante(con, vr, campania_id=camps[campania], k_dem=1.0,
                              hora_inicio_s=6*3600, hora_fin_s=24*3600)
rb = Simulador(ib).run(mode='corrected', keep_series=True)
rr = Simulador(ir).run(mode='corrected', keep_series=True)

# Marco incremental: situación previa, base optimizada (reconfig), con proyecto (GPS)
ev = evaluar_incremental(rb.espera_vh, rr.espera_vh, rr.espera_pre_vh, cruce)

st.subheader(f'Resultados — {cruce}')
c = st.columns(3)
c[0].metric('Situación base optimizada', f'{ev.espera_sbo:,.0f} v·h/día',
            'reconfiguración semafórica')
c[1].metric('Con proyecto (GPS–SCATS)', f'{ev.espera_proyecto:,.0f} v·h/día',
            'reconfiguración + pre-vaciado')
c[2].metric('Ahorro incremental del proyecto',
            f'{ev.ahorro_gps_incremental:,.0f} v·h/día',
            f'{ev.fraccion_gps*100:.0f}% del total de optimización')

# Saturación por banda
sat = analizar_saturacion(rb, n_carriles=2.0, usar_pre=False)
st.subheader('Régimen de saturación por banda horaria')
if sat.banda_critica:
    st.caption(f'Banda más cargada: {sat.banda_critica.hora_inicio:02.0f}:00–'
               f'{sat.banda_critica.hora_fin:02.0f}:00 con grado de '
               f'saturación x = {sat.x_max:.2f} ({sat.metodo_recomendado}).')
banda_df = pd.DataFrame([{
    'Hora': f'{b.hora_inicio:02.0f}–{b.hora_fin:02.0f}h',
    'Flujo (v/h)': round(b.flujo_h),
    'Capacidad (v/h)': round(b.capacidad_h),
    'Saturación x': round(b.x, 2),
    'Régimen': b.metodo.split(' (')[0],
} for b in sat.bandas])
st.dataframe(banda_df, use_container_width=True, hide_index=True)

# Beneficio incremental valorizado
ben = calcular_beneficio(ev.ahorro_gps_incremental, factor_espera=2.0)
st.subheader('Beneficio incremental del proyecto en este cruce')
c = st.columns(2)
c[0].metric('Ahorro anual', f'{ben.ahorro_anual_veh_h:,.0f} v·h/año')
c[1].metric('Beneficio social anual', f'CLP {ben.beneficio_anual_clp:,.0f}',
            'valor social del tiempo de espera')

# Evolución de la cola (visual)
st.subheader('Cola en la vía lateral a lo largo del día')
s = rr.series
if s and 'C' in s:
    import numpy as np
    C = np.asarray(s['C']) / 3600
    chart_df = pd.DataFrame({
        'hora': C,
        'base optimizada': np.asarray(s['Q']),
        'con proyecto': np.asarray(s['Qpre']),
    }).set_index('hora')
    st.line_chart(chart_df)

con.close()
