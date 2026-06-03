"""Incertidumbre: Monte Carlo + Sobol + break-even + valor de la información."""
import numpy as np
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import (
    ParamIncierto, monte_carlo_van, sobol_van, break_even,
    valor_informacion_perfecta, construir_eval_van,
)

st.set_page_config(page_title='Incertidumbre', page_icon='🎲', layout='wide')
st.title('Tratamiento riguroso de la incertidumbre')
st.caption('Monte Carlo multivariable, índices de Sobol (sensibilidad '
           'global), break-even y valor de la información. Eleva el VAN de '
           'un punto estimado a una distribución con intervalos de confianza.')

con = datos.conectar()
cat = {c.cruce: c for c in datos.catalogo_simulable(con)}

with st.sidebar:
    cruce = st.selectbox('Cruce', list(cat))
    st.divider()
    st.caption('**Distribuciones de los parámetros inciertos**')
    fp_min = st.number_input('Flujo principal mín (v/h)', 200, 3000, 800, 100)
    fp_mod = st.number_input('Flujo principal moda (v/h)', 200, 3000, 1800, 100)
    fp_max = st.number_input('Flujo principal máx (v/h)', 200, 4000, 2600, 100)
    kd_min = st.number_input('k_dem mín', 0.5, 1.5, 0.95, 0.05)
    kd_mod = st.number_input('k_dem moda', 0.5, 1.5, 1.10, 0.05)
    kd_max = st.number_input('k_dem máx', 0.5, 1.5, 1.25, 0.05)
    capex_base = st.number_input('CAPEX base (CLP M)', 50, 2000, 300, 50)
    n_mc = st.slider('Muestras Monte Carlo', 100, 1000, 400, 100)
    correr = st.button('Ejecutar análisis', type='primary',
                       use_container_width=True)

if not correr:
    st.info('Configure las distribuciones y pulse «Ejecutar análisis». '
            'El cálculo toma ≈20-40 s según el número de muestras.')
    con.close(); st.stop()

eval_fn = construir_eval_van(con, cruce)
params = [
    ParamIncierto('k_dem', 'triangular', kd_min, kd_mod, kd_max),
    ParamIncierto('flujo_principal_h', 'triangular', fp_min, fp_mod, fp_max),
    ParamIncierto('h_saturacion', 'normal', 2.0, 0.15),
    ParamIncierto('capex_clp', 'triangular',
                  capex_base*0.85e6, capex_base*1e6, capex_base*1.5e6),
    ParamIncierto('ocupacion_veh', 'triangular', 1.3, 1.5, 1.8),
]
base = {'k_dem': kd_mod, 'flujo_principal_h': fp_mod, 'h_saturacion': 2.0,
        'n_carriles_lateral': 2, 'n_carriles_principal': 2,
        'capex_clp': capex_base*1e6, 'opex_anual_clp': 15e6,
        'tasa_descuento': 0.055, 'crecimiento_demanda': 0.02,
        'ocupacion_veh': 1.5, 'consumo_ralenti_l_h': 1.10}

# --- 1. Monte Carlo ---
st.subheader('1. Monte Carlo multivariable — distribución del VAN')
with st.spinner('Propagando incertidumbre...'):
    mc = monte_carlo_van(eval_fn, params, n_muestras=n_mc, semilla=7)
c = st.columns(4)
c[0].metric('VAN esperado', f'CLP {mc.van_media/1e6:,.0f} M')
c[1].metric('VAN mediana', f'CLP {mc.van_mediana/1e6:,.0f} M')
c[2].metric('IC 90 %',
            f'[{mc.van_p05/1e6:,.0f} .. {mc.van_p95/1e6:,.0f}] M')
c[3].metric('P(VAN > 0)', f'{mc.prob_van_positivo*100:.1f} %',
            '✅ rentable' if mc.prob_van_positivo > 0.9 else '⚠ riesgoso')
# Histograma
hist_df = pd.DataFrame({'VAN (CLP M)': mc.muestras_van / 1e6})
st.bar_chart(np.histogram(mc.muestras_van/1e6, bins=30)[0])
st.caption(f'Distribución de {n_mc} simulaciones del VAN. '
           f'Desviación estándar: CLP {mc.van_std/1e6:,.0f} M.')

# --- 2. Sobol ---
st.subheader('2. Índices de Sobol — sensibilidad global con interacciones')
with st.spinner('Calculando índices de Sobol...'):
    sob = sobol_van(eval_fn, params, n_base=64)
df_sob = pd.DataFrame([{
    'Parámetro': n,
    'S1 (directo)': round(sob.S1[n], 3),
    'ST (total)': round(sob.ST[n], 3),
    'Interacción': round(sob.ST[n] - sob.S1[n], 3),
} for n in sorted(sob.nombres, key=lambda n: -sob.ST[n])])
st.dataframe(df_sob, use_container_width=True, hide_index=True)
st.caption('S1 = efecto directo. ST = efecto total (directo + interacciones). '
           'Cuando ST >> S1, el parámetro actúa principalmente por '
           'interacción con otros — algo que el tornado univariado no detecta.')

# --- 3. Break-even ---
st.subheader('3. Break-even — umbrales de viabilidad')
rangos_be = {'flujo_principal_h': (400, 4000), 'k_dem': (0.6, 1.4),
             'capex_clp': (100e6, 3000e6)}
filas_be = []
for par, rng in rangos_be.items():
    be = break_even(eval_fn, base, par, rng)
    filas_be.append({
        'Parámetro': par,
        'Valor base': f'{be.valor_base:,.1f}',
        'Break-even (VAN=0)': f'{be.valor_break_even:,.1f}' if be.valor_break_even else 'no cruza',
        'Margen': f'{be.margen_pct:+.0f} %' if be.margen_pct is not None else '—',
        'Viabilidad': f'{be.direccion} con el parámetro',
    })
st.dataframe(pd.DataFrame(filas_be), use_container_width=True, hide_index=True)

# --- 4. Valor de la información ---
st.subheader('4. Valor de la información sobre el flujo principal')
voi = valor_informacion_perfecta(
    eval_fn, base, 'flujo_principal_h',
    ParamIncierto('flujo_principal_h', 'triangular', fp_min, fp_mod, fp_max),
    n_estados=150)
c = st.columns(3)
c[0].metric('VAN esperado sin medir', f'CLP {voi.van_esperado_sin_info/1e6:,.0f} M')
c[1].metric('VAN esperado con info', f'CLP {voi.van_esperado_con_info/1e6:,.0f} M')
c[2].metric('EVPI', f'CLP {voi.evpi/1e6:,.0f} M',
            'valor de medir antes de decidir')
st.info(voi.evpi_interpretacion)

con.close()
