"""Página de simulación: corre el motor para un cruce y muestra resultados."""
import numpy as np
import pandas as pd
import streamlit as st

import datos
from motor_sim import Simulador

st.set_page_config(page_title='Simulación', page_icon='🚦', layout='wide')
st.title('Simulación de un cruce')

con = datos.conectar()
cruces = datos.cruces_simulables(con)
versiones = {r['nombre']: r['version_prog_id'] for r in datos.listar_versiones(con)}
campanias = {r['nombre']: r['campania_id'] for r in datos.listar_campanias(con)}

# ------------------------------------------------------------------ #
#  panel de control (barra lateral) -- reemplaza el panel del Excel
# ------------------------------------------------------------------ #
with st.sidebar:
    st.header('Configuración')
    cruce = st.selectbox('Cruce', cruces)
    version = st.selectbox('Programación semafórica', list(versiones))
    campania = st.selectbox('Campaña de aforos', list(campanias))
    modo = st.radio(
        'Modo de cálculo', ['corrected', 'faithful', 'stochastic'],
        help='corrected: base y pre en la misma ventana. '
             'faithful: réplica del Excel (con sus errores). '
             'stochastic: llegadas Poisson (Monte Carlo).')
    st.divider()
    k_dem = st.slider('Factor de demanda k_dem', 0.5, 1.5, 1.1, 0.05,
                      help='1.1 reproduce el modelo Excel original.')
    buffer = st.slider('Buffer pre-vaciado (s)', 0, 60, 0, 5)
    h = st.slider('Headway de saturación h (s)', 1.0, 3.0, 2.0, 0.5)
    n_carriles = st.slider('Carriles del movimiento lateral', 1, 4, 2, 1)
    h_ini, h_fin = st.select_slider(
        'Ventana horaria', options=list(range(0, 25)), value=(6, 21),
        format_func=lambda x: f'{x:02d}:00')
    correr = st.button('Ejecutar simulación', type='primary',
                       use_container_width=True)

if not correr:
    st.info('Ajuste la configuración en la barra lateral y pulse '
            '«Ejecutar simulación».')
    con.close()
    st.stop()

# ------------------------------------------------------------------ #
#  ejecucion del motor
# ------------------------------------------------------------------ #
inp = datos.construir_inputs(
    con, cruce, version_prog_id=versiones[version],
    campania_id=campanias[campania], hora_inicio_s=h_ini * 3600,
    hora_fin_s=h_fin * 3600, h=h, n_carriles=n_carriles,
    buffer=buffer, k_dem=k_dem)
sim = Simulador(inp)

if modo == 'stochastic':
    st_res = sim.run_stochastic(n_rep=30)
    res = sim.run(mode='corrected', keep_series=True)
else:
    res = sim.run(mode=modo, keep_series=True)
    st_res = None

# ------------------------------------------------------------------ #
#  indicadores
# ------------------------------------------------------------------ #
st.subheader(f'Resultados — {cruce}')
c = st.columns(4)
c[0].metric('Demanda evaluada', f'{res.demanda:,.0f} veh')
c[1].metric('Espera base', f'{res.espera_vh:,.1f} veh·h',
            f'{res.demora_prom:.0f} s/veh')
c[2].metric('Espera pre-vaciado', f'{res.espera_pre_vh:,.1f} veh·h',
            f'{res.demora_pre:.0f} s/veh')
c[3].metric('Reducción de espera', f'{res.reduccion_pct * 100:.1f} %',
            f'{res.reduccion_vh:,.1f} veh·h')

if res.cola_final > 1.0:
    st.warning(f'La cola base termina la ventana con '
               f'{res.cola_final:.0f} vehículos: el cruce opera cerca '
               f'de la saturación y el modelo determinístico de cola puntual '
               f'pierde validez (sin spillback la cola diverge).')

if modo == 'faithful':
    st.error('Modo «faithful»: reproduce el Excel **incluyendo su error de '
             'ventana** (la espera pre-vaciado se suma solo sobre las '
             'primeras 3 h). La reducción mostrada está sobreestimada. '
             'Use «corrected» para una comparación válida.')

if st_res is not None:
    st.subheader('Sensibilidad estocástica (30 réplicas Poisson)')
    cc = st.columns(3)
    cc[0].metric('Espera base determinista', f'{st_res["det_base_vh"]:.1f} veh·h')
    cc[1].metric('Espera base estocástica',
                 f'{st_res["est_base_vh"]:.1f} veh·h',
                 f'± {st_res["est_base_sd"]:.1f}')
    cc[2].metric('Sesgo del modelo determinista',
                 f'{st_res["sesgo_pct"]:+.1f} %')

# ------------------------------------------------------------------ #
#  graficos
# ------------------------------------------------------------------ #
s = res.series
paso = 15                                   # submuestreo para graficar
C = s['C'][::paso]
horas = C / 3600.0
cumA = np.cumsum(s['V'])[::paso]            # llegadas acumuladas
cumD_base = cumA - s['Q'][::paso]            # salidas acumuladas base
cumD_pre = cumA - s['Qpre'][::paso]          # salidas acumuladas pre

st.subheader('Curvas acumuladas (diagrama de Newell)')
st.caption('El área entre llegadas y salidas es la espera total. '
           'Cuanto más pegada va la curva de salidas a la de llegadas, '
           'menor es la espera.')
df_newell = pd.DataFrame(
    {'Llegadas': cumA, 'Salidas base': cumD_base,
     'Salidas pre-vaciado': cumD_pre}, index=horas)
df_newell.index.name = 'Hora'
st.line_chart(df_newell)

st.subheader('Cola a lo largo del día')
df_cola = pd.DataFrame(
    {'Cola base': s['Q'][::paso], 'Cola pre-vaciado': s['Qpre'][::paso]},
    index=horas)
df_cola.index.name = 'Hora'
st.area_chart(df_cola)

# ------------------------------------------------------------------ #
#  descarga
# ------------------------------------------------------------------ #
st.subheader('Exportar')
resumen = pd.DataFrame([{
    'cruce': cruce, 'modo': modo, 'k_dem': k_dem,
    'demanda_veh': res.demanda,
    'espera_base_veh_h': res.espera_vh,
    'espera_pre_veh_h': res.espera_pre_vh,
    'demora_base_s': res.demora_prom,
    'demora_pre_s': res.demora_pre,
    'reduccion_veh_h': res.reduccion_vh,
    'reduccion_pct': res.reduccion_pct,
    'cola_max_base': res.cola_max,
    'cola_final_base': res.cola_final,
}])
st.download_button(
    'Descargar resumen (CSV)', resumen.to_csv(index=False).encode('utf-8'),
    file_name=f'resultado_{cruce.replace(" ", "_")}.csv', mime='text/csv')

con.close()
