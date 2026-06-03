"""Análisis avanzado: microsim + tornado + alternativas + desglose + riesgos."""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import (
    Simulador, analizar_saturacion, analizar_principal,
    balance_lateral_principal, calcular_beneficio, calcular_externalidades,
    evaluar_horizonte, microsim_desde_resultados, sensibilidad_van_cruce,
    alternativas_estandar, desglosar_beneficio, matriz_riesgos_estandar,
    COMPOSICION_TIPICA_CONCEPCION,
)

st.set_page_config(page_title='Análisis avanzado', page_icon='📐', layout='wide')
st.title('Análisis avanzado — microsim, sensibilidad, alternativas, riesgos')

con = datos.conectar()
cat = {c.cruce: c for c in datos.catalogo_simulable(con)}
campanias = {r['nombre']: r['campania_id'] for r in datos.listar_campanias(con)}

with st.sidebar:
    cruce = st.selectbox('Cruce', list(cat))
    cc = cat[cruce]
    campania = st.selectbox('Campaña', list(campanias))
    k_dem = st.slider('k_dem', 0.5, 1.5, 1.1, 0.05)
    flujo_pri = st.number_input('Flujo principal (v/h)', 500, 4000, 1800, 100)
    capex = st.number_input('CAPEX proyecto (CLP M)', 0, 5000, 300, 50)

tabs = st.tabs(['🔬 Microsim banda crítica', '🌀 Tornado VAN',
                '⚖️ Alternativas', '🚌 Desglose modal', '⚠️ Riesgos'])

# Corridas comunes para todas las pestañas
v_base = cc.variante('base')
v_rec = cc.variante('reconfiguracion') or v_base
ib = datos.inputs_de_variante(con, v_base, campania_id=campanias[campania],
                              k_dem=k_dem, hora_inicio_s=6*3600, hora_fin_s=24*3600)
ir = datos.inputs_de_variante(con, v_rec, campania_id=campanias[campania],
                              k_dem=k_dem, hora_inicio_s=6*3600, hora_fin_s=24*3600)
rb = Simulador(ib).run(mode='corrected', keep_series=True)
rr = Simulador(ir).run(mode='corrected', keep_series=True)
sat_a = analizar_saturacion(rb, n_carriles=2.0, usar_pre=False)
sat_p = analizar_saturacion(rr, n_carriles=2.0, usar_pre=True)
pri_a = analizar_principal(rb, flujo_principal_h=flujo_pri, usar_pre=False)
pri_p = analizar_principal(rr, flujo_principal_h=flujo_pri, usar_pre=True)
bal = balance_lateral_principal(sat_a, pri_a, sat_p, pri_p)
ben = calcular_beneficio(bal['balance_neto_vh'])
ext = calcular_externalidades(ben.ahorro_anual_veh_h, ben.beneficio_anual_clp)
total_anual = ben.beneficio_anual_clp + ext.beneficio_externalidades_clp

# ---------- Tab 1: Microsim ----------
with tabs[0]:
    st.subheader('Microsimulación de eventos discretos')
    bandas_saturadas = [b for b in sat_a.bandas if b.x > 1.0]
    if not bandas_saturadas:
        st.info('No hay bandas sobre-saturadas (x > 1,0) en este cruce. '
                'Microsim aplica solo cuando Akcelik está fuera de rango.')
    else:
        st.caption(f'Bandas saturadas detectadas: '
                   f'{", ".join(f"{int(b.hora_inicio)}-{int(b.hora_fin)}h (x={b.x:.2f})" for b in bandas_saturadas)}')
        banda_sel = st.selectbox(
            'Banda a microsimular',
            [(int(b.hora_inicio), int(b.hora_fin), b.x) for b in bandas_saturadas],
            format_func=lambda x: f'{x[0]:02d}-{x[1]:02d}h (x={x[2]:.2f})')
        n_rep = st.slider('Réplicas Monte Carlo', 50, 500, 200, 50)
        if st.button('Correr microsimulación', type='primary'):
            mc = microsim_desde_resultados(rb, hora_inicio=banda_sel[0],
                                           hora_fin=banda_sel[1], n_replicas=n_rep)
            b = next(b for b in sat_a.bandas if b.hora_inicio == banda_sel[0])
            c1, c2, c3, c4 = st.columns(4)
            c1.metric('Motor (Newell)', f'{b.espera_motor_vh:.1f} vh')
            c2.metric('Akcelik analítico', f'{b.espera_d1_vh + b.espera_d2_vh:.1f} vh')
            c3.metric('Microsim (media)', f'{mc.espera_total_vh_media:.1f} vh',
                      f'P90: {mc.espera_total_vh_p90:.1f}')
            c4.metric('Estable',
                      '✅' if mc.estable else '❌',
                      f'cola final: {mc.cola_final_media:.0f} veh')
            st.code(mc.resumen())

# ---------- Tab 2: Tornado ----------
with tabs[1]:
    st.subheader('Sensibilidad multivariable (tornado)')
    metrica = st.selectbox('Métrica objetivo',
                            ['van', 'tir', 'b_c', 'beneficio_anual'])
    if st.button('Correr tornado', type='primary'):
        with st.spinner('Calculando sensibilidades (≈30s)...'):
            t = sensibilidad_van_cruce(con, cruce, metrica=metrica)
        st.metric('Baseline', f'{t.metrica_base:,.0f}')
        # Tabla
        df = pd.DataFrame([{
            'Parámetro': p.nombre,
            'Mín': p.valor_min, 'Máx': p.valor_max,
            'Métrica mín': p.metrica_min, 'Métrica máx': p.metrica_max,
            'Impacto |Δ|': p.impacto_absoluto,
            'Impacto %': round(p.impacto_pct, 1),
        } for p in t.parametros])
        st.dataframe(df, use_container_width=True, hide_index=True)
        # Tornado bar chart simple
        import altair as alt
        chart_df = pd.DataFrame([{
            'Parámetro': p.nombre,
            'Mínimo': p.metrica_min - t.metrica_base,
            'Máximo': p.metrica_max - t.metrica_base,
            'Impacto': p.impacto_absoluto,
        } for p in t.parametros])
        st.altair_chart(
            alt.Chart(chart_df).mark_bar().encode(
                x=alt.X('Mínimo:Q', title=f'Δ vs baseline ({t.metrica_nombre})'),
                x2='Máximo:Q',
                y=alt.Y('Parámetro:N', sort='-x'),
                tooltip=['Parámetro', 'Mínimo', 'Máximo', 'Impacto'],
            ).properties(height=300),
            use_container_width=True)
        st.caption('Los parámetros más arriba son los más sensibles. '
                   'Priorizar evidencia empírica en ellos.')

# ---------- Tab 3: Alternativas ----------
with tabs[2]:
    st.subheader('Comparación de alternativas')
    benef_solo_pre = (rb.espera_vh - rb.espera_pre_vh) * 250 * 1.5 * 3338
    benef_solo_rec = (rb.espera_vh - rr.espera_vh) * 250 * 1.5 * 3338
    espera_actual_clp = rb.espera_vh * 250 * 1.5 * 3338
    capex_pd = st.number_input('CAPEX paso a desnivel (CLP M)', 500, 10000, 3500, 100)
    comp = alternativas_estandar(
        cruce=cruce,
        beneficio_proyecto_completo=total_anual,
        beneficio_solo_prevaciado=benef_solo_pre,
        beneficio_solo_reconfig=benef_solo_rec,
        espera_actual_total_clp=espera_actual_clp,
        capex_proyecto=capex * 1e6, capex_paso_desnivel=capex_pd * 1e6)
    st.code(comp.imprimir())
    if not comp.es_postulada_optima:
        st.warning(f'⚠ La alternativa óptima NO es la postulada. '
                   f'Diferencia VAN: CLP {comp.diferencia_van_vs_optima/1e6:,.0f} M. '
                   'La memoria SNI debe justificar la selección.')

# ---------- Tab 4: Desglose modal ----------
with tabs[3]:
    st.subheader('Desglose modal del beneficio')
    st.caption('Composición modal: ajustable. Sin aforos modales reales '
               'usar la composición típica de Concepción como referencia.')
    composicion = {}
    cols = st.columns(3)
    for i, (modo, pct) in enumerate(COMPOSICION_TIPICA_CONCEPCION.items()):
        composicion[modo] = cols[i % 3].slider(
            modo.replace('_', ' '), 0.0, 1.0, pct, 0.01)
    desg = desglosar_beneficio(ben.ahorro_anual_veh_h, composicion=composicion)
    c1, c2 = st.columns(2)
    c1.metric('Beneficio modal total',
              f'CLP {desg.beneficio_anual_total:,.0f}')
    c2.metric('Modo mayor aporte',
              desg.modo_mayor_aporte.replace('_', ' '),
              f'{desg.pct_mayor_aporte:.1f}% del total')
    df_mod = pd.DataFrame([{
        'Modo': d.modo.replace('_', ' '),
        '% flujo': f'{d.pct_flujo*100:.1f}%',
        'veh·h/año': round(d.veh_h_anual_modo),
        'Ocupación': d.ocupacion,
        'pax·h/año': round(d.pax_h_anual_modo),
        'VST CLP/h': round(d.vst_clp_h),
        'Beneficio CLP': round(d.beneficio_anual_clp),
    } for d in desg.desglose])
    st.dataframe(df_mod, use_container_width=True, hide_index=True)
    st.caption('Para postular, sustituir composición con aforos modales reales.')

# ---------- Tab 5: Riesgos ----------
with tabs[4]:
    st.subheader('Matriz de riesgos del proyecto')
    mr = matriz_riesgos_estandar()
    res = mr.resumen()
    cols = st.columns(4)
    cols[0].metric('Críticos', res['criticos'], 'requieren acción correctiva')
    cols[1].metric('Altos', res['altos'], 'plan de contingencia')
    cols[2].metric('Medios', res['medios'], 'mitigación documentada')
    cols[3].metric('Bajos', res['bajos'], 'seguimiento periódico')

    cat_sel = st.multiselect('Filtrar por categoría',
                              ['tecnico', 'operacional', 'economico', 'institucional'],
                              default=['tecnico', 'operacional',
                                       'economico', 'institucional'])
    df_riesgos = pd.DataFrame([{
        'Cód': r.codigo, 'Categ.': r.categoria,
        'Severidad': r.severidad_etiqueta, 'P': r.probabilidad,
        'I': r.impacto, 'Descripción': r.descripcion[:70] + '...',
        'Mitigación': r.mitigacion[:70] + '...',
    } for r in mr.riesgos_ordenados if r.categoria in cat_sel])
    st.dataframe(df_riesgos, use_container_width=True, hide_index=True)

    # Detalle de riesgos críticos
    if mr.riesgos_criticos:
        st.error('**Riesgos críticos** (severidad ≥ 7):')
        for r in mr.riesgos_criticos:
            with st.expander(f'{r.codigo}: {r.descripcion[:60]}...'):
                st.markdown(f'**Categoría:** {r.categoria}')
                st.markdown(f'**Probabilidad:** {r.probabilidad}  **Impacto:** {r.impacto}')
                st.markdown(f'**Descripción completa:** {r.descripcion}')
                st.markdown(f'**Mitigación:** {r.mitigacion}')
                st.markdown(f'**Disparador:** {r.disparador}')
                st.markdown(f'**Responsable:** {r.responsable}')

con.close()
