"""Simulación de un cruce: actual vs proyecto (pre-vaciado + reconfig si aplica)."""
import numpy as np
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import (
    calcular_beneficio,
    VST_URBANO_VIAJE_2026, DIAS_LABORALES_AÑO, OCUPACION_VEH_DEFAULT,
)

st.set_page_config(page_title='Simulación', page_icon='🚦', layout='wide')
st.title('Simulación: actual vs proyecto')

con = datos.conectar()
cat = {c.cruce: c for c in datos.catalogo_simulable(con)}
campanias = {r['nombre']: r['campania_id'] for r in datos.listar_campanias(con)}

with st.sidebar:
    st.header('Configuración')
    cruce = st.selectbox('Cruce', list(cat))
    cc = cat[cruce]
    st.caption(f'Modelo del cruce: **{cc.etiqueta_modelo}**')
    if cc.proyecto:
        cod = cc.proyecto.codigo_proyecto or '—'
        st.caption(f'Proyecto: {cc.proyecto.via_principal or ""} · código {cod}')
    if cc.tiene_reconfiguracion:
        st.success('Cruce con reconfiguración declarada — post-HCALL se '
                   'salta al verde lateral para evacuar la cola.')
    else:
        st.info('Cruce sin reconfiguración — post-HCALL retorna a fase 1 '
                '(operación actual).')

    campania = st.selectbox('Campaña de aforos', list(campanias))
    tipo_dia = st.radio('Tipo de día', ['Laboral', 'Sabado', 'Domingo/Festivo'],
                        help='Selecciona la malla horaria de planes. Los '
                             'aforos cargados son solo Laboral.')
    k_dem = st.slider('Factor de demanda k_dem', 0.5, 1.5, 1.1, 0.05,
                      help='1.1 reproduce el modelo Excel original.')
    buffer = st.slider('Buffer pre-vaciado (s)', 0, 60, 0, 5)
    h = st.slider('Headway de saturación h (s)', 1.0, 3.0, 2.0, 0.5)
    n_carriles = st.slider('Carriles del movimiento lateral', 1, 4, 2, 1)
    h_ini, h_fin = st.select_slider(
        'Ventana horaria', options=list(range(0, 25)), value=(6, 24),
        format_func=lambda x: f'{x:02d}:00')
    st.divider()
    st.caption('**Beneficio social (MDS 2026)**')
    ocup = st.slider('Ocupación (pax/veh)', 1.0, 3.0,
                     OCUPACION_VEH_DEFAULT, 0.1)
    correr = st.button('Ejecutar simulación', type='primary',
                       use_container_width=True)

if not correr:
    st.info('Configure y pulse «Ejecutar simulación». Se evaluarán cuatro '
            'situaciones: operación actual, solo pre-vaciado, solo '
            'reconfiguración y proyecto completo (pre-vaciado + reconfig).')
    con.close(); st.stop()

p = datos.simular_proyecto(
    con, cruce, campania_id=campanias[campania],
    hora_inicio_s=h_ini * 3600, hora_fin_s=h_fin * 3600,
    h=h, n_carriles=n_carriles, buffer=buffer, k_dem=k_dem,
    tipo_dia=tipo_dia)

if tipo_dia != 'Laboral' and p['demanda'] == 0:
    st.warning(f'No hay aforos cargados para {tipo_dia}. Para evaluar '
               'sábados/domingos cargue una campaña de aforos del día '
               'correspondiente.')

st.subheader(f'Resultados — {cruce}')
c = st.columns(4)
c[0].metric('Operación actual', f'{p["actual"]:,.1f} veh·h',
            'sin pre-vaciado, post-HCALL → fase 1')
c[1].metric('Solo pre-vaciado', f'{p["solo_prevaciado"]:,.1f} veh·h',
            f'−{p["aporte_prevaciado"]:.1f} veh·h')
if p['tiene_reconfig']:
    c[2].metric('Solo reconfiguración', f'{p["solo_reconfig"]:,.1f} veh·h',
                'sin pre-vaciado, post-HCALL → verde lateral')
    c[3].metric('Proyecto completo', f'{p["proyecto"]:,.1f} veh·h',
                f'−{p["aporte_reconfig"]:.1f} veh·h vs solo pre-vaciado',
                delta_color='inverse')
else:
    c[2].metric('Solo reconfiguración', '— (no aplica)',
                'cruce sin reconfiguración declarada')
    c[3].metric('Proyecto completo', f'{p["proyecto"]:,.1f} veh·h',
                'solo pre-vaciado (no hay reconfig)')

st.subheader('Beneficio del proyecto (actual vs proyecto completo)')
b = st.columns(3)
b[0].metric('Ahorro de espera', f'{p["ahorro_total"]:,.1f} veh·h/día',
            f'{p["reduccion_pct"]*100:.1f} % de reducción')
ben = calcular_beneficio(p['ahorro_total'], ocupacion=ocup)
b[1].metric('Ahorro anual', f'{ben.ahorro_anual_veh_h:,.0f} veh·h',
            f'× {ben.dias_laborales} días laborales')
b[2].metric('Beneficio social anual', f'CLP {ben.beneficio_anual_clp:,.0f}',
            f'≈ {ben.beneficio_anual_uf_aprox:,.0f} UF')

if p['tiene_reconfig']:
    st.caption(f'**Desglose**: aporte del pre-vaciado = '
               f'{p["aporte_prevaciado"]:.1f} veh·h ({p["aporte_prevaciado"]/p["ahorro_total"]*100 if p["ahorro_total"] else 0:.0f} %).  '
               f'Aporte de la reconfiguración = '
               f'{p["aporte_reconfig"]:.1f} veh·h ({p["aporte_reconfig"]/p["ahorro_total"]*100 if p["ahorro_total"] else 0:.0f} %).')
st.caption(f'VST urbano viaje MDS 2026: {VST_URBANO_VIAJE_2026:,} CLP/h-pax · '
           f'ocupación {ben.ocupacion} pax/veh · {ben.dias_laborales} días/año.')

if p['cola_final_actual'] > 1.0:
    st.warning(f'La cola actual termina con {p["cola_final_actual"]:.0f} '
               'vehículos: el cruce opera cerca de saturación. La cola '
               'determinística diverge — los números son orden de magnitud, '
               'no representativos.')

# --- gráficos ---
s_a, s_p = p['serie_actual'], p['serie_proyecto']
paso = 15
horas = s_a['C'][::paso] / 3600.0
cumA = np.cumsum(s_a['V'])[::paso]
st.subheader('Curvas acumuladas (diagrama de Newell)')
st.line_chart(pd.DataFrame(
    {'Llegadas': cumA,
     'Salidas operación actual': cumA - s_a['Q'][::paso],
     'Salidas proyecto completo': cumA - s_p['Qpre'][::paso]},
    index=pd.Index(horas, name='Hora')))
st.subheader('Cola a lo largo del día')
st.area_chart(pd.DataFrame(
    {'Cola actual': s_a['Q'][::paso],
     'Cola proyecto': s_p['Qpre'][::paso]},
    index=pd.Index(horas, name='Hora')))

resumen = pd.DataFrame([{
    'cruce': cruce, 'demanda_veh': p['demanda'], 'k_dem': k_dem,
    'actual_veh_h': p['actual'], 'solo_prevaciado_veh_h': p['solo_prevaciado'],
    'solo_reconfig_veh_h': p['solo_reconfig'], 'proyecto_veh_h': p['proyecto'],
    'ahorro_veh_h_dia': p['ahorro_total'], 'reduccion_pct': p['reduccion_pct'],
    'aporte_prevaciado_veh_h': p['aporte_prevaciado'],
    'aporte_reconfig_veh_h': p['aporte_reconfig'],
    'ahorro_veh_h_anio': ben.ahorro_anual_veh_h,
    'beneficio_anual_clp': ben.beneficio_anual_clp,
    'ocupacion': ben.ocupacion, 'vst_clp_pax_h': ben.vst_clp_pax_h,
}])
st.download_button('Descargar resumen (CSV)',
                   resumen.to_csv(index=False).encode('utf-8'),
                   file_name=f'resultado_{cruce.replace(" ", "_")}.csv',
                   mime='text/csv')
con.close()
