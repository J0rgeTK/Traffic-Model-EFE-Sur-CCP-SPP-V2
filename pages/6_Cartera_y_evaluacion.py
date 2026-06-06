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

with st.sidebar:
    st.header('Parámetros de evaluación')
    st.caption(f'Flujos: {CAMP_NOM}.')
    costo_uf = st.number_input('Costo del proyecto (UF)', 5000, 30000, 15000, 500)
    uf_clp = st.number_input('Valor de la UF (CLP)', 30000.0, 50000.0, 40695.38, 0.01,
                             format='%.2f')
    ocupacion = st.slider('Ocupación vehicular (pax/veh)', 1.0, 2.5,
                          float(OCUPACION_VEH_DEFAULT), 0.1)
    factor_espera = st.slider('Ponderador VST de espera', 1.0, 2.0, 2.0, 0.5)
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
    c = buscar(cat, nom); vb = c.variante('base'); vr = c.variante('reconfiguracion') or vb
    rb = Simulador(datos.inputs_de_variante(con, vb, campania_id=CAMP_ID, k_dem=1.0,
        hora_inicio_s=6*3600, hora_fin_s=24*3600)).run(mode='corrected', keep_series=True)
    rr = Simulador(datos.inputs_de_variante(con, vr, campania_id=CAMP_ID, k_dem=1.0,
        hora_inicio_s=6*3600, hora_fin_s=24*3600)).run(mode='corrected', keep_series=True)
    ev = evaluar_incremental(rb.espera_vh, rr.espera_vh, rr.espera_pre_vh, nom)
    # Beneficios de cada fase (valorizados con ocupación y VST configurados)
    ben_reconfig = calcular_beneficio(ev.ahorro_reconfiguracion, ocupacion=ocupacion,
                                      factor_espera=factor_espera)
    ben_gps = calcular_beneficio(ev.ahorro_gps_incremental, ocupacion=ocupacion,
                                 factor_espera=factor_espera)
    tot_reconfig += ben_reconfig.beneficio_anual_clp
    tot_gps += ben_gps.beneficio_anual_clp
    sa = analizar_saturacion(rb, n_carriles=2.0, usar_pre=False)
    diario, pico = flujos_cruce(cid); bc = sa.banda_critica
    g = 'San Pedro' if 'Pedro' in comuna(cid) else 'Coronel'
    anclas_raw.append(dict(cruce=nom, cruce_id=cid, grupo=g,
        flujo_lateral_diario=diario, flujo_pico_h=pico, n_carriles_lateral=2.0,
        x_max=sa.x_max, capacidad_pico_h=bc.capacidad_h if bc else 900,
        balance_neto_vh=ev.ahorro_gps_incremental,
        beneficio_anual_clp=ben_gps.beneficio_anual_clp))
    items.append({'Cruce': nom, 'Grupo': g, 'Origen': 'Simulación',
                  'x_max': round(sa.x_max, 2),
                  'Ahorro reconfig. (v·h/día)': round(ev.ahorro_reconfiguracion, 1),
                  'Ahorro GPS (v·h/día)': round(ev.ahorro_gps_incremental, 1),
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
st.subheader('Indicadores de rentabilidad social del proyecto')
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

con.close()
