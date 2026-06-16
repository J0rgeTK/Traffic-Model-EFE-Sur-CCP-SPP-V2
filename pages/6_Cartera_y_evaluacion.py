"""Sección 6 — Cartera del proyecto y evaluación económica.

Descompone el impacto en las tres fases de la iniciativa:
  Situación actual (sin proyecto, sin optimización)
    -> Reconfiguración semafórica (Iniciativa 1, situación base optimizada)
       -> Integración GPS-SCATS (proyecto), con pre-vaciado predictivo
y reporta tanto el impacto total como el incremental atribuible al proyecto.
"""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import (
    Simulador, evaluar_incremental, calcular_beneficio,
    caracterizar_anclas, extrapolar_cruce, estimar_capacidad_pico_ref,
    clasificar_catalogo, analizar_saturacion, OCUPACION_VEH_DEFAULT,
    ocupacion_efectiva_cruce, OCUPACION_BUS_DEFAULT,
)
from modelo_cruces.catalogo import buscar, construir_catalogo
import modelo_cruces.cartera as cartera_mod

st.set_page_config(page_title='Cartera y evaluación', page_icon='📦', layout='wide')
st.title('6 · Cartera del proyecto y evaluación económica')
st.caption('Impacto de las tres fases (situación actual → reconfiguración → '
           'GPS–SCATS), beneficio por zona e indicadores de rentabilidad social.')

con = datos.conectar(); cur = con.cursor()
clasif = clasificar_catalogo(con, ids_corredor={2,4,6,7,8,10,11,12,14})
camp = datos.listar_campanias(con)[0]
CAMP_ID, CAMP_NOM = camp['campania_id'], camp['nombre']


@st.cache_data(show_spinner=False)
def evaluar_fisico(nombre: str, campania_id: int) -> dict:
    """Evaluación física de un cruce (esperas), cacheada e independiente de
    los parámetros económicos."""
    c2 = datos.conectar()
    try:
        return datos.evaluar_cruce_corregido(c2, nombre, campania_id=campania_id)
    finally:
        c2.close()

with st.sidebar:
    st.header('Parámetros de evaluación')
    st.caption(f'Flujos: {CAMP_NOM}.')
    costo_uf = st.number_input('Costo del proyecto (UF)', 5000, 30000, 14000, 500)
    uf_clp = st.number_input('Valor de la UF (CLP)', 30000.0, 50000.0, 40695.38, 0.01,
                             format='%.2f')
    ocupacion = st.slider('Ocupación vehículo liviano (pax/veh)', 1.0, 2.5,
                          float(OCUPACION_VEH_DEFAULT), 0.1)
    incluir_buses = st.checkbox('Incluir buses', value=True)
    ocup_bus = st.number_input('Ocupación por bus (pax)', 10.0, 50.0,
                               25.0, 1.0) if incluir_buses else 25.0
    factor_espera = st.slider('Ponderador VST de espera', 1.0, 2.0, 1.0, 0.5)
    crec = st.slider('Crecimiento demanda anual %', 0.0, 5.0, 2.0, 0.5) / 100
    horizonte = st.slider('Horizonte (años)', 10, 30, 20, 1)
    tsd = st.slider('Tasa social de descuento %', 4.0, 7.0, 5.5, 0.5) / 100
    correr = st.button('Evaluar cartera', type='primary', use_container_width=True)

evaluables = [c for c in clasif.values() if c.admite_reconfiguracion]
ids_sim = [c.cruce_id for c in evaluables if c.simulable_directo]
ids_est = [c.cruce_id for c in evaluables if not c.simulable_directo]

if not correr:
    st.info('Configure los parámetros y pulse «Evaluar cartera».')
    st.markdown(f"""
La cartera reúne los **{len(evaluables)} cruces evaluables** del corredor.
La evaluación descompone el impacto en las tres fases de la iniciativa:

1. **Situación actual** — operación vigente, sin proyecto ni optimización.
2. **Reconfiguración semafórica** (Iniciativa 1) — situación base optimizada.
3. **Integración GPS–SCATS** (el proyecto) — suma el pre-vaciado predictivo.

Se reporta el **impacto total** de la iniciativa completa y el beneficio
**incremental** atribuible al proyecto GPS–SCATS, que es el que sustenta
los indicadores económicos.
""")
    con.close(); st.stop()

cartera_mod.UF_CLP = uf_clp  # aplicar UF configurada

def flujos_cruce(cid):
    rows = cur.execute("SELECT flujo_veh_h FROM dem.llegadas_vehiculares "
                       "WHERE campania_id=? AND cruce_id=? ORDER BY t_inicio_s",
                       (CAMP_ID, cid)).fetchall()
    f = [r['flujo_veh_h'] for r in rows]
    return (sum(f), max(f)) if f else (0, 0)

def comuna(cid):
    return cur.execute("SELECT comuna FROM infra.antecedentes_cruce WHERE cruce_id=?",
                       (cid,)).fetchone()[0]

cat = construir_catalogo(con)
prog = st.progress(0.0, 'Evaluando cruces...')
items = []; anclas_raw = []
tot_reconfig = 0.0; tot_gps = 0.0
for i, cid in enumerate(ids_sim):
    nom = clasif[cid].nombre
    # Evaluación coherente con corrección de saturación (n_carriles real),
    # cacheada: los parámetros económicos no obligan a re-simular.
    ec = evaluar_fisico(nom, CAMP_ID)
    # Ocupación efectiva del cruce (considera buses si está activado)
    if incluir_buses:
        oc = ocupacion_efectiva_cruce(con, cid, CAMP_ID, ocupacion, ocup_bus)
        ocup_cruce = oc['ocupacion_efectiva']
    else:
        ocup_cruce = ocupacion
    ben_reconfig = calcular_beneficio(ec['ahorro_reconfiguracion_vh'], ocupacion=ocup_cruce,
                                      factor_espera=factor_espera)
    ben_gps = calcular_beneficio(ec['ahorro_gps_incremental_vh'], ocupacion=ocup_cruce,
                                 factor_espera=factor_espera)
    tot_reconfig += ben_reconfig.beneficio_anual_clp
    tot_gps += ben_gps.beneficio_anual_clp
    diario, pico = flujos_cruce(cid)
    g = 'San Pedro' if 'Pedro' in comuna(cid) else 'Coronel'
    cap_pico = pico / ec['x_max'] if ec['x_max'] > 0 else pico
    anclas_raw.append(dict(cruce=nom, cruce_id=cid, grupo=g,
        flujo_lateral_diario=diario, flujo_pico_h=pico,
        n_carriles_lateral=ec['n_carriles'], x_max=ec['x_max'],
        capacidad_pico_h=cap_pico, balance_neto_vh=ec['ahorro_gps_incremental_vh'],
        beneficio_anual_clp=ben_gps.beneficio_anual_clp))
    items.append({'Cruce': nom, 'Grupo': g, 'Origen': 'Simulación',
                  'x_max': round(ec['x_max'], 2), 'Ocup. (pax/veh)': round(ocup_cruce, 2),
                  'Ahorro reconfig. (v·h/día)': round(ec['ahorro_reconfiguracion_vh'], 1),
                  'Ahorro GPS (v·h/día)': round(ec['ahorro_gps_incremental_vh'], 1),
                  'Benef. reconfig. (CLP)': round(ben_reconfig.beneficio_anual_clp),
                  'Benef. GPS (CLP)': round(ben_gps.beneficio_anual_clp)})
    prog.progress((i+1)/max(1,len(ids_sim)), f'Evaluado {nom}')
prog.empty()

anclas = caracterizar_anclas(anclas_raw)
cap_ref = estimar_capacidad_pico_ref(anclas)
for cid in ids_est:
    nom = clasif[cid].nombre
    g = 'San Pedro' if 'Pedro' in comuna(cid) else 'Coronel'
    diario, pico = flujos_cruce(cid)
    if diario > 0:
        ex = extrapolar_cruce(nom, cid, g, diario, pico, 2, anclas, cap_ref)
        b_gps = max(0, ex.beneficio_estimado_clp * 0.10)
        tot_gps += b_gps
        items.append({'Cruce': nom, 'Grupo': g, 'Origen': 'Estimación (tipología)',
                      'x_max': round(ex.x_estimado, 2),
                      'Ahorro reconfig. (v·h/día)': '—', 'Ahorro GPS (v·h/día)': '—',
                      'Benef. reconfig. (CLP)': '—', 'Benef. GPS (CLP)': round(b_gps)})

st.subheader('Cruces de la cartera — impacto por fase')
st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)

# Impacto agregado de las tres fases
st.subheader('Impacto agregado de la iniciativa')
c = st.columns(3)
c[0].metric('Fase 1 — Reconfiguración', f'CLP {tot_reconfig/1e6:,.0f} MM/año',
            'situación base optimizada')
c[1].metric('Fase 2/3 — GPS–SCATS (proyecto)', f'CLP {tot_gps/1e6:,.0f} MM/año',
            'incremental del proyecto')
c[2].metric('Impacto total de la iniciativa', f'CLP {(tot_reconfig+tot_gps)/1e6:,.0f} MM/año',
            'actual → proyecto completo')
st.caption('La reconfiguración (Fase 1) es la situación base optimizada y no '
           'forma parte de la inversión del proyecto. El beneficio que sustenta '
           'los indicadores económicos es el incremental del GPS–SCATS.')

# Beneficio del proyecto por zona
benef_anual = tot_gps
por_grupo = {}
for it in items:
    b = it['Benef. GPS (CLP)']
    if isinstance(b, (int, float)):
        por_grupo[it['Grupo']] = por_grupo.get(it['Grupo'], 0) + b
st.subheader('Beneficio del proyecto por zona')
cols = st.columns(len(por_grupo) + 1)
for i, (g, v) in enumerate(por_grupo.items()):
    cols[i].metric(g, f'CLP {v/1e6:,.0f} MM/año')
cols[-1].metric('Total proyecto', f'CLP {benef_anual/1e6:,.0f} MM/año')

# Indicadores económicos (sobre el beneficio incremental del proyecto)
st.subheader('Indicadores de rentabilidad social — Proyecto GPS–SCATS (incremental)')
capex = costo_uf * uf_clp
reinv10 = capex * 0.20
vr20 = capex * 0.13
flujos = [-capex]
for t in range(1, horizonte + 1):
    b = benef_anual * (1 + crec) ** (t - 1)
    if t == 10: b -= reinv10
    if t == horizonte: b += vr20
    flujos.append(b)
van = sum(f / (1 + tsd) ** i for i, f in enumerate(flujos))
lo, hi, tir = -0.99, 5.0, None
for _ in range(200):
    mid = (lo + hi) / 2
    v = sum(f / (1 + mid) ** i for i, f in enumerate(flujos))
    if abs(v) < 1: tir = mid; break
    lo, hi = (mid, hi) if v > 0 else (lo, mid)
else:
    tir = mid
bva = sum(flujos[t] / (1 + tsd) ** t for t in range(1, horizonte + 1) if flujos[t] > 0)
bc = bva / capex
acc = -capex; pb = None
for t in range(1, horizonte + 1):
    b = benef_anual * (1 + crec) ** (t - 1)
    if t == 10: b -= reinv10
    acc += b / (1 + tsd) ** t
    if pb is None and acc >= 0: pb = t

c = st.columns(4)
c[0].metric('VAN', f'CLP {van/1e6:,.0f} MM', 'positivo' if van > 0 else 'negativo')
c[1].metric('TIR', f'{tir*100:.1f} %', f'vs TSD {tsd*100:.1f}%')
c[2].metric('B/C', f'{bc:.2f}')
c[3].metric('Payback', f'{pb} años' if pb else '> horizonte')
st.caption(f'Costo {costo_uf:,.0f} UF × CLP {uf_clp:,.2f} = CLP {capex/1e6:,.0f} MM, '
           f'mantenimiento incluido. Ocupación {ocupacion:.1f} pax/veh. '
           f'Reinversión AVL/GPS año 10, valor residual año {horizonte}.')

st.subheader('Beneficio del proyecto en cortes temporales')
cols = st.columns(3)
for i, a in enumerate((0, 10, 20)):
    cols[i].metric(f'Año {a}', f'CLP {benef_anual*(1+crec)**a/1e6:,.0f} MM')

# ----------------------------------------------------------------------
#  Evaluación social en formato SNI (flujo año por año, en UF)
# ----------------------------------------------------------------------
st.divider()
st.subheader('Evaluación social del proyecto GPS–SCATS (incremental, UF)')
st.caption('Flujo del beneficio incremental del proyecto GPS–SCATS —el ahorro '
           'de tiempo atribuible al pre-vaciado, sobre la base ya '
           f'reconfigurada (CLP {benef_anual/1e6:,.0f} MM/año)— y de su '
           'inversión, en unidades de fomento. **No** incluye el beneficio de '
           'la reconfiguración, que pertenece a la situación sin proyecto.')

a_uf = lambda clp: clp / uf_clp                   # CLP -> UF
inv_uf = costo_uf
reinv_uf = inv_uf * 0.20
resid_uf = inv_uf * 0.13
benef_tiempo_uf = a_uf(benef_anual)               # ahorro de tiempo (UF/año base)

filas = []
flujo_social = [-inv_uf]
filas.append({'Año': 0, 'Inversión': f'-{inv_uf:,.0f}',
              'Beneficio tiempo': '', 'Total': f'-{inv_uf:,.0f}'})
for t in range(1, horizonte + 1):
    ben = benef_tiempo_uf * (1 + crec) ** (t - 1)
    inv = 0.0
    if t == 10: inv -= reinv_uf
    if t == horizonte: inv += resid_uf
    total = ben + inv
    flujo_social.append(total)
    filas.append({'Año': t, 'Inversión': f'{inv:,.0f}' if inv else '',
                  'Beneficio tiempo': f'{ben:,.0f}', 'Total': f'{total:,.0f}'})

van_uf = sum(f / (1 + tsd) ** i for i, f in enumerate(flujo_social))
lo, hi, tir_s = -0.99, 5.0, None
for _ in range(200):
    m = (lo + hi) / 2
    v = sum(f / (1 + m) ** i for i, f in enumerate(flujo_social))
    if abs(v) < 0.5: tir_s = m; break
    lo, hi = (m, hi) if v > 0 else (lo, m)
else:
    tir_s = m

st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True, height=380)
c = st.columns(2)
c[0].metric(f'VAN ({tsd*100:.1f}%)', f'{van_uf:,.0f} UF')
c[1].metric('TIR', f'{tir_s*100:.1f} %')
st.caption('Beneficio = ahorro de tiempo de espera valorizado con el VST. La '
           'Inversión incluye la reinversión de equipos en el año 10 y el valor '
           'residual al cierre del horizonte. El modelo no cuantifica beneficios '
           'por combustible, emisiones ni accidentes: requerirían factores y '
           'datos de siniestralidad propios del corredor que no forman parte '
           'de esta evaluación.')

# ----------------------------------------------------------------------
#  Análisis de sensibilidad (Inversión x Beneficios)
# ----------------------------------------------------------------------
st.subheader('Análisis de sensibilidad')
st.caption('Variación del VAN y la TIR del proyecto GPS–SCATS ante cambios de '
           '±20% en la inversión y en su beneficio incremental por ahorro de '
           'tiempo (no en el de la iniciativa completa).')

def van_tir(f_inv, f_ben):
    inv = inv_uf * (1 + f_inv)
    rein = inv * 0.20; resid = inv * 0.13
    fl = [-inv]
    for t in range(1, horizonte + 1):
        b = benef_tiempo_uf * (1 + crec) ** (t - 1) * (1 + f_ben)
        if t == 10: b -= rein
        if t == horizonte: b += resid
        fl.append(b)
    van = sum(x / (1 + tsd) ** i for i, x in enumerate(fl))
    lo, hi = -0.99, 5.0
    for _ in range(200):
        mm = (lo + hi) / 2
        vv = sum(x / (1 + mm) ** i for i, x in enumerate(fl))
        if abs(vv) < 0.5: break
        lo, hi = (mm, hi) if vv > 0 else (lo, mm)
    return van, mm

niveles = [(-0.20, '-20%'), (0.0, '0%'), (0.20, '+20%')]
filas_s = []
for fi, li in niveles:
    for fb, lb in niveles:
        van, tir_c = van_tir(fi, fb)
        filas_s.append({'Inversión': li, 'Beneficios': lb,
                        'VAN (UF)': f'{van:,.0f}', 'TIR (%)': f'{tir_c*100:.1f}%'})
st.dataframe(pd.DataFrame(filas_s), use_container_width=True, hide_index=True)
st.caption('La combinación más adversa (inversión +20%, beneficios −20%) es la '
           'prueba de robustez del proyecto: un VAN que se mantiene positivo en '
           'ese escenario indica una rentabilidad social sólida.')

con.close()
