"""Evaluacion SNI: saturacion + principal + externalidades + horizonte."""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import (
    calcular_beneficio, analizar_saturacion, analizar_principal,
    balance_lateral_principal, calcular_externalidades, evaluar_horizonte,
    correr_jitter_hcall, Simulador,
    VST_URBANO_VIAJE_2026, OCUPACION_VEH_DEFAULT,
    TASA_SOCIAL_DESCUENTO_2026, HORIZONTE_SNI_DEFAULT,
    TASA_CRECIMIENTO_DEMANDA_DEFAULT,
)

st.set_page_config(page_title='Evaluación SNI', page_icon='💰', layout='wide')
st.title('Evaluación SNI integral — un solo cruce')
st.caption('Combina motor + Akcelik + movimiento principal + externalidades '
           '+ horizonte 15 años. Para postulación al Sistema Nacional de '
           'Inversiones.')

con = datos.conectar()
cat = {c.cruce: c for c in datos.catalogo_simulable(con)}
campanias = {r['nombre']: r['campania_id'] for r in datos.listar_campanias(con)}

with st.sidebar:
    st.header('Configuración')
    cruce = st.selectbox('Cruce', list(cat))
    cc = cat[cruce]
    st.caption(f'**{cc.etiqueta_modelo}**')

    campania = st.selectbox('Campaña aforos', list(campanias))
    k_dem = st.slider('k_dem', 0.5, 1.5, 1.1, 0.05)

    st.divider()
    st.caption('**Movimiento principal (Ruta 160)**')
    flujo_principal = st.number_input(
        'Flujo principal estimado (veh/h)', 500, 4000, 1800, 100,
        help='Sin aforos reales del principal — valor referencial.')
    carriles_principal = st.slider('Carriles principal', 1, 4, 2, 1)

    st.divider()
    st.caption('**Evaluación social**')
    ocup = st.slider('Ocupación (pax/veh)', 1.0, 3.0, OCUPACION_VEH_DEFAULT, 0.1)
    capex = st.number_input('CAPEX (CLP M)', 0, 5000, 200, 50,
                            help='Inversión inicial del proyecto en este cruce.')
    opex_anual = st.number_input('OPEX anual (CLP M)', 0, 500, 15, 5)
    crec_dem = st.slider('Crecimiento demanda anual %', 0.0, 5.0, 2.0, 0.5) / 100
    horizonte = st.slider('Horizonte (años)', 5, 25, HORIZONTE_SNI_DEFAULT, 1)

    st.divider()
    st.caption('**Variabilidad operacional**')
    sigma_hcall = st.slider('Jitter HCALL σ (s)', 0, 240, 90, 30,
                            help='Variabilidad real del itinerario ferroviario.')
    n_rep = st.slider('Réplicas Monte Carlo', 10, 100, 30, 10)

    correr = st.button('Ejecutar evaluación SNI', type='primary',
                       use_container_width=True)

if not correr:
    st.info('Configure los parámetros del proyecto y pulse «Ejecutar».')
    con.close(); st.stop()

# -------------------- corridas determinísticas -----------------------
p = datos.simular_proyecto(
    con, cruce, campania_id=campanias[campania], k_dem=k_dem,
    hora_inicio_s=6*3600, hora_fin_s=24*3600)
sat_a, sat_p = p['saturacion_actual'], p['saturacion_proyecto']

# Movimiento principal sobre ambas series
v_base = cc.variante('base')
v_rec = cc.variante('reconfiguracion') or v_base
ib = datos.inputs_de_variante(con, v_base, campania_id=campanias[campania],
                              k_dem=k_dem, hora_inicio_s=6*3600,
                              hora_fin_s=24*3600)
ir = datos.inputs_de_variante(con, v_rec, campania_id=campanias[campania],
                              k_dem=k_dem, hora_inicio_s=6*3600,
                              hora_fin_s=24*3600)
rb = Simulador(ib).run(mode='corrected', keep_series=True)
rr = Simulador(ir).run(mode='corrected', keep_series=True)
pri_a = analizar_principal(rb, flujo_principal_h=flujo_principal,
                           carriles_principal=carriles_principal, usar_pre=False)
pri_p = analizar_principal(rr, flujo_principal_h=flujo_principal,
                           carriles_principal=carriles_principal, usar_pre=True)
bal = balance_lateral_principal(sat_a, pri_a, sat_p, pri_p)

# -------------------- panel 1: saturación ----------------------------
st.subheader('1. Saturación del movimiento lateral')
c = st.columns(4)
c[0].metric('Espera actual (motor)', f'{p["actual"]:,.0f} vh')
c[1].metric('Espera actual (Akcelik)', f'{sat_a.espera_akcelik_total_vh:,.0f} vh',
            f'{sat_a.ajuste_pct:+.0f} % vs motor')
c[2].metric('x_max actual', f'{sat_a.x_max:.2f}', sat_a.metodo_recomendado)
c[3].metric('x_max proyecto', f'{sat_p.x_max:.2f}', sat_p.metodo_recomendado)
if not sat_a.valida_global:
    st.error(f'⚠ {sat_a.observacion}')

with st.expander('Detalle por banda horaria'):
    bandas_df = pd.DataFrame([{
        'Hora': f'{b.hora_inicio:>4.0f}–{b.hora_fin:.0f}h',
        'V (v/h)': round(b.flujo_h),
        'c (v/h)': round(b.capacidad_h),
        'x': round(b.x, 2),
        'Motor (vh)': round(b.espera_motor_vh, 1),
        'd1+d2 (vh)': round(b.espera_d1_vh + b.espera_d2_vh, 1),
        'Cola final': round(b.cola_final, 1),
        'Régimen': b.metodo.split(' (')[0],
    } for b in sat_a.bandas])
    st.dataframe(bandas_df, use_container_width=True, hide_index=True)

# -------------------- panel 2: balance lateral vs principal ----------
st.subheader('2. Balance lateral vs principal (Ruta 160)')
c = st.columns(4)
c[0].metric('Ahorro lateral', f'{bal["delta_lateral_vh"]:,.0f} vh/día',
            'Akcelik agregado')
c[1].metric('Costo principal', f'{bal["delta_principal_vh"]:,.0f} vh/día',
            f'flujo asumido {flujo_principal} v/h')
c[2].metric('Balance neto', f'{bal["balance_neto_vh"]:,.0f} vh/día',
            'positivo = proyecto beneficioso')
razon = bal['razon_lateral_principal']
c[3].metric('Razón L/P',
            f'{razon:.1f}×' if razon != float('inf') else '∞',
            'ahorro lateral por cada veh·h costo principal')
if not bal['es_neto_positivo']:
    st.error('⚠ El balance NETO del proyecto es negativo. El costo en '
             'Ruta 160 supera el ahorro lateral.')

# -------------------- panel 3: beneficio social anual ----------------
st.subheader('3. Beneficio social anual (VST + externalidades)')
ben_vst = calcular_beneficio(bal['balance_neto_vh'], ocupacion=ocup)
ext = calcular_externalidades(
    veh_h_ahorrado_anual=ben_vst.ahorro_anual_veh_h,
    beneficio_vst_clp=ben_vst.beneficio_anual_clp)
total_anual = ben_vst.beneficio_anual_clp + ext.beneficio_externalidades_clp

c = st.columns(4)
c[0].metric('Ahorro veh·h anual',
            f'{ben_vst.ahorro_anual_veh_h:,.0f}',
            f'250 días × {bal["balance_neto_vh"]:.0f} vh/día')
c[1].metric('Beneficio VST',
            f'CLP {ben_vst.beneficio_anual_clp:,.0f}',
            f'{VST_URBANO_VIAJE_2026:,} CLP/h-pax')
c[2].metric('Externalidades',
            f'CLP {ext.beneficio_externalidades_clp:,.0f}',
            f'+{ext.factor_sobre_vst:.0f} % sobre VST')
c[3].metric('TOTAL anual', f'CLP {total_anual:,.0f}',
            f'≈ {total_anual/39727.96:,.0f} UF/año')

with st.expander('Desglose de externalidades'):
    st.code(ext.desglose())

# -------------------- panel 4: horizonte 15 años ---------------------
st.subheader('4. Evaluación a horizonte SNI')
ev = evaluar_horizonte(
    beneficio_anual_inicial=total_anual,
    capex_clp=capex * 1e6, opex_anual_clp=opex_anual * 1e6,
    horizonte_anios=horizonte, tasa_descuento=TASA_SOCIAL_DESCUENTO_2026,
    tasa_crecimiento_demanda=crec_dem)
c = st.columns(4)
c[0].metric('VAN', f'CLP {ev.van_clp:,.0f}',
            '✅ positivo' if ev.van_clp > 0 else '❌ negativo')
c[1].metric('TIR', f'{ev.tir*100:.1f} %' if ev.tir else '—',
            'vs tasa social 5,5 %')
c[2].metric('B/C descontado', f'{ev.relacion_b_c:.2f}',
            '≥ 1 = rentable')
c[3].metric('Payback', f'{ev.payback_anios:.1f} años'
            if ev.payback_anios else '> horizonte',
            'recuperación de la inversión')

with st.expander('Flujos anuales descontados'):
    flujos_df = pd.DataFrame(ev.detalle_flujos)
    st.dataframe(flujos_df, use_container_width=True, hide_index=True)

# -------------------- panel 5: sensibilidad jitter HCALL -------------
st.subheader('5. Sensibilidad operacional — jitter del HCALL')
sim_pre = Simulador(ir)
jh = correr_jitter_hcall(sim_pre, ir, n_rep=n_rep, sigma_s=sigma_hcall,
                          usar_pre=True)
c = st.columns(4)
c[0].metric('Espera media (n={})'.format(n_rep),
            f'{jh.espera_media_vh:.1f} vh',
            f'σ={sigma_hcall}s')
c[1].metric('Espera P10', f'{jh.espera_p10_vh:.1f} vh', 'mejor 10 %')
c[2].metric('Espera P90', f'{jh.espera_p90_vh:.1f} vh', 'peor 10 %')
c[3].metric('Pérdida vs ideal', f'{jh.perdida_pct_vs_ideal:+.1f} %',
            'cuánto se degrada el beneficio')

st.caption('Esta sensibilidad muestra cuánto del beneficio reportado se '
           'mantiene si el itinerario ferroviario tiene variabilidad real. '
           'Para postulación SNI, reportar el P10–P90.')

# -------------------- veredicto --------------------------------------
st.divider()
st.subheader('Veredicto técnico')
defendible = (ev.van_clp > 0 and ev.relacion_b_c >= 1
              and bal['es_neto_positivo']
              and sat_p.valida_global)
if defendible:
    st.success(f'**{cruce}: postulable.** Modelo coherente, balance neto '
               'positivo, VAN/TIR aceptables. Documentar supuestos y '
               'validar con mediciones de campo.')
else:
    razones = []
    if not bal['es_neto_positivo']:
        razones.append('balance neto NEGATIVO (Ruta 160 pierde más que el lateral)')
    if not sat_p.valida_global:
        razones.append('régimen de saturación fuera del rango analítico')
    if ev.van_clp <= 0:
        razones.append('VAN no rentable a la tasa social')
    if ev.relacion_b_c < 1:
        razones.append(f'B/C={ev.relacion_b_c:.2f} < 1')
    st.error(f'**{cruce}: NO postulable así.** Motivos: {", ".join(razones)}.')

# Exportable
resumen = {
    'cruce': cruce, 'x_max_actual': sat_a.x_max, 'x_max_proyecto': sat_p.x_max,
    'ahorro_lateral_vh': bal['delta_lateral_vh'],
    'costo_principal_vh': bal['delta_principal_vh'],
    'balance_neto_vh': bal['balance_neto_vh'],
    'beneficio_vst_anual_clp': ben_vst.beneficio_anual_clp,
    'beneficio_externalidades_clp': ext.beneficio_externalidades_clp,
    'beneficio_total_anual_clp': total_anual,
    'capex_clp': capex * 1e6, 'opex_anual_clp': opex_anual * 1e6,
    'van_clp': ev.van_clp, 'tir': ev.tir, 'b_c': ev.relacion_b_c,
    'payback_anios': ev.payback_anios,
    'jitter_espera_media_vh': jh.espera_media_vh,
    'jitter_perdida_pct': jh.perdida_pct_vs_ideal,
    'postulable': defendible,
}
st.download_button('Descargar resumen SNI (CSV)',
                   pd.DataFrame([resumen]).to_csv(index=False).encode(),
                   file_name=f'evaluacion_sni_{cruce.replace(" ", "_")}.csv')
con.close()
