"""Sección 6 — Cartera del proyecto y evaluación económica."""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import (
    Simulador, evaluar_incremental, calcular_beneficio,
    caracterizar_anclas, extrapolar_cruce, estimar_capacidad_pico_ref,
    clasificar_catalogo, analizar_saturacion,
)
from modelo_cruces.catalogo import buscar, construir_catalogo
from modelo_cruces.cartera import UF_CLP

st.set_page_config(page_title='Cartera y evaluación', page_icon='📦', layout='wide')
st.title('6 · Cartera del proyecto y evaluación económica')
st.caption('Beneficio incremental por cruce, agrupación por zona e '
           'indicadores de rentabilidad social.')

con = datos.conectar()
cur = con.cursor()
clasif = clasificar_catalogo(con, ids_corredor={2,4,6,7,8,10,11,12})

with st.sidebar:
    st.header('Parámetros de evaluación')
    campania = st.selectbox('Campaña de flujos',
                            [(r['campania_id'], r['nombre']) for r in datos.listar_campanias(con)],
                            format_func=lambda x: x[1])[0]
    costo_uf = st.number_input('Costo del proyecto (UF)', 5000, 30000, 15000, 500)
    factor_espera = st.slider('Ponderador VST de espera', 1.0, 2.0, 2.0, 0.5)
    crec = st.slider('Crecimiento demanda anual %', 0.0, 5.0, 2.0, 0.5) / 100
    horizonte = st.slider('Horizonte (años)', 10, 30, 20, 1)
    tsd = st.slider('Tasa social de descuento %', 4.0, 7.0, 5.5, 0.5) / 100
    correr = st.button('Evaluar cartera', type='primary', use_container_width=True)

SIM = {2:'Los Claveles',4:'Diagonal Bio Bio',6:'Michaihue',7:'Costa Verde',
       8:'Masisa',10:'Lomas Coloradas',11:'Portal San Pedro',12:'Conavicop'}

if not correr:
    st.info('Configure los parámetros y pulse «Evaluar cartera».')
    st.markdown("""
La cartera reúne los cruces evaluables del corredor. El beneficio de cada
cruce es el **incremental** de la integración GPS–SCATS sobre la base
optimizada con reconfiguración. Los cruces se agrupan por zona (San Pedro
de la Paz / Coronel) y se reportan los indicadores económicos del conjunto.
""")
    con.close(); st.stop()

def flujos_cruce(cid):
    rows = cur.execute("SELECT flujo_veh_h FROM dem.llegadas_vehiculares "
                       "WHERE campania_id=? AND cruce_id=? ORDER BY t_inicio_s",
                       (campania, cid)).fetchall()
    f = [r['flujo_veh_h'] for r in rows]
    return (sum(f), max(f)) if f else (0, 0)

cat = construir_catalogo(con)
prog = st.progress(0.0, 'Evaluando cruces...')
items = []; anclas_raw = []
for i, (cid, nom) in enumerate(SIM.items()):
    c = buscar(cat, nom); vb = c.variante('base'); vr = c.variante('reconfiguracion') or vb
    rb = Simulador(datos.inputs_de_variante(con, vb, campania_id=campania, k_dem=1.0,
        hora_inicio_s=6*3600, hora_fin_s=24*3600)).run(mode='corrected', keep_series=True)
    rr = Simulador(datos.inputs_de_variante(con, vr, campania_id=campania, k_dem=1.0,
        hora_inicio_s=6*3600, hora_fin_s=24*3600)).run(mode='corrected', keep_series=True)
    ev = evaluar_incremental(rb.espera_vh, rr.espera_vh, rr.espera_pre_vh, nom)
    ben = calcular_beneficio(ev.ahorro_gps_incremental, factor_espera=factor_espera)
    sa = analizar_saturacion(rb, n_carriles=2.0, usar_pre=False)
    diario, pico = flujos_cruce(cid)
    bc = sa.banda_critica
    anclas_raw.append(dict(cruce=nom, cruce_id=cid, grupo='SPP',
        flujo_lateral_diario=diario, flujo_pico_h=pico, n_carriles_lateral=2.0,
        x_max=sa.x_max, capacidad_pico_h=bc.capacidad_h if bc else 900,
        balance_neto_vh=ev.ahorro_gps_incremental,
        beneficio_anual_clp=ben.beneficio_anual_clp))
    items.append({'Cruce': nom, 'Grupo': 'San Pedro', 'Origen': 'Simulación',
                  'x_max': round(sa.x_max, 2),
                  'Ahorro incremental (v·h/día)': round(ev.ahorro_gps_incremental, 1),
                  'Beneficio anual (CLP)': round(ben.beneficio_anual_clp)})
    prog.progress((i+1)/len(SIM), f'Evaluado {nom}')
prog.empty()

# Extrapolación de cruces tipo A/D sin programación
anclas = caracterizar_anclas(anclas_raw)
cap_ref = estimar_capacidad_pico_ref(anclas)
for cid in [5, 15]:  # Daniel Belmar (SPP), Escuadrón 1 (Coronel) — tipo A
    if cid in clasif and clasif[cid].tipologia in ('A', 'D') and clasif[cid].extrapolable:
        grupo = 'Coronel' if cid == 15 else 'San Pedro'
        diario, pico = flujos_cruce(cid)
        if diario > 0:
            ex = extrapolar_cruce(clasif[cid].nombre, cid, grupo, diario, pico, 2, anclas, cap_ref)
            # En marco incremental, el beneficio extrapolado se toma como fracción GPS
            items.append({'Cruce': clasif[cid].nombre, 'Grupo': grupo,
                          'Origen': 'Estimación (tipología)',
                          'x_max': round(ex.x_estimado, 2),
                          'Ahorro incremental (v·h/día)': '—',
                          'Beneficio anual (CLP)': round(max(0, ex.beneficio_estimado_clp * 0.10))})

st.subheader('Cruces de la cartera')
df = pd.DataFrame(items)
st.dataframe(df, use_container_width=True, hide_index=True)

# Beneficio agregado
benef_anual = sum(it['Beneficio anual (CLP)'] for it in items
                  if isinstance(it['Beneficio anual (CLP)'], (int, float)))
por_grupo = {}
for it in items:
    b = it['Beneficio anual (CLP)']
    if isinstance(b, (int, float)):
        por_grupo[it['Grupo']] = por_grupo.get(it['Grupo'], 0) + b

st.subheader('Beneficio por zona')
cols = st.columns(len(por_grupo) + 1)
for i, (g, v) in enumerate(por_grupo.items()):
    cols[i].metric(g, f'CLP {v/1e6:,.0f} MM/año')
cols[-1].metric('Total cartera', f'CLP {benef_anual/1e6:,.0f} MM/año')

# Evaluación económica
st.subheader('Indicadores de rentabilidad social')
capex = costo_uf * UF_CLP
reinv10 = capex * 0.20   # reinversión equipos AVL/GPS año 10 (vida útil 10 años)
vr20 = capex * 0.13      # valor residual licencia + comunicación
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
c[0].metric('VAN', f'CLP {van/1e6:,.0f} MM', '✅ positivo' if van > 0 else '❌ negativo')
c[1].metric('TIR', f'{tir*100:.1f} %', f'vs TSD {tsd*100:.1f}%')
c[2].metric('B/C', f'{bc:.2f}', '≥1 rentable')
c[3].metric('Payback', f'{pb} años' if pb else '> horizonte')

st.caption(f'Costo {costo_uf:,.0f} UF (CLP {capex/1e6:,.0f} MM), mantenimiento '
           f'incluido en la inversión. Reinversión de equipos AVL/GPS en año 10. '
           f'Valor residual en año {horizonte}. Beneficio incremental GPS sobre '
           'la base optimizada.')

# Cortes temporales
st.subheader('Beneficio en cortes temporales')
cols = st.columns(3)
for i, a in enumerate((0, 10, 20)):
    cols[i].metric(f'Año {a}', f'CLP {benef_anual*(1+crec)**a/1e6:,.0f} MM')

con.close()
