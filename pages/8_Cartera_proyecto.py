"""Cartera del proyecto: simulados + extrapolados, grupos, VAN/TIR, cortes."""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import (
    Simulador, analizar_saturacion, analizar_principal,
    balance_lateral_principal, calcular_beneficio, calcular_externalidades,
    caracterizar_anclas, extrapolar_cruce, estimar_capacidad_pico_ref,
    evaluar_cartera, ItemCartera,
)
from modelo_cruces.catalogo import buscar, construir_catalogo

st.set_page_config(page_title='Cartera del proyecto', page_icon='📦', layout='wide')
st.title('Evaluación de cartera — proyecto completo')
st.caption('Simulados (con programación) + extrapolados (sin programación, por '
           'régimen de saturación), agrupados por zona, con costo total e '
           'indicadores SNI en cortes temporales. Excluye San Francisco–Lo Rojas.')

con = datos.conectar(); cur = con.cursor()
cat = construir_catalogo(con)

with st.sidebar:
    st.header('Parámetros')
    campania = st.selectbox('Campaña de flujos', [3, 1, 2],
                            format_func=lambda c: {3:'Actualizados 2026',
                            1:'Base (NOREPROG)', 2:'Reprog Mar9'}[c])
    flujo_pri = st.number_input('Flujo principal R160 (v/h)', 500, 4000, 1500, 100)
    costo_uf = st.number_input('Costo total proyecto (UF)', 1000, 30000, 15000, 500)
    crec = st.slider('Crecimiento demanda anual %', 0.0, 5.0, 2.0, 0.5) / 100
    horizonte = st.slider('Horizonte (años)', 10, 30, 20, 1)
    correr = st.button('Evaluar cartera', type='primary', use_container_width=True)

SIM = {2:'Los Claveles',4:'Diagonal Bio Bio',6:'Michaihue',7:'Costa Verde',
       8:'Masisa',10:'Lomas Coloradas',11:'Portal San Pedro',12:'Conavicop'}
EXTRAP = {3:('Las Garzas','SPP',2),5:('Daniel Belmar','SPP',2),
          13:('Grau','Coronel',2),14:('Escuadron 2','Coronel',2),
          15:('Escuadron 1','Coronel',2),16:('Escuadron 3','Coronel',2)}

if not correr:
    st.info('Configure parámetros y pulse «Evaluar cartera».')
    st.markdown('**Grupos de presentación:** San Pedro (PAC/R160) y Coronel. '
                'Los cruces San Francisco a Lo Rojas se excluyen por tener '
                'lógica de intersección clásica sin fase lateral definible.')
    con.close(); st.stop()

def flujos_cruce(cid):
    rows = cur.execute("SELECT flujo_veh_h FROM dem.llegadas_vehiculares "
                       "WHERE campania_id=? AND cruce_id=? ORDER BY t_inicio_s",
                       (campania, cid)).fetchall()
    f = [r['flujo_veh_h'] for r in rows]
    return (sum(f), max(f)) if f else (0, 0)

# --- Simular anclas ---
prog = st.progress(0.0, 'Simulando cruces con programación...')
anclas_raw, items = [], []
for i, (cid, nom) in enumerate(SIM.items()):
    c = buscar(cat, nom); vb = c.variante('base'); vr = c.variante('reconfiguracion') or vb
    ib = datos.inputs_de_variante(con, vb, campania_id=campania, k_dem=1.0,
                                  hora_inicio_s=6*3600, hora_fin_s=24*3600)
    ir = datos.inputs_de_variante(con, vr, campania_id=campania, k_dem=1.0,
                                  hora_inicio_s=6*3600, hora_fin_s=24*3600)
    rb = Simulador(ib).run(mode='corrected', keep_series=True)
    rr = Simulador(ir).run(mode='corrected', keep_series=True)
    sa = analizar_saturacion(rb, n_carriles=2.0, usar_pre=False)
    sp = analizar_saturacion(rr, n_carriles=2.0, usar_pre=True)
    pa = analizar_principal(rb, flujo_principal_h=flujo_pri, usar_pre=False)
    pp = analizar_principal(rr, flujo_principal_h=flujo_pri, usar_pre=True)
    bal = balance_lateral_principal(sa, pa, sp, pp)
    ben = calcular_beneficio(bal['balance_neto_vh'])
    ext = calcular_externalidades(ben.ahorro_anual_veh_h, ben.beneficio_anual_clp)
    total = ben.beneficio_anual_clp + ext.beneficio_externalidades_clp
    diario, pico = flujos_cruce(cid)
    bc = sa.banda_critica
    anclas_raw.append(dict(cruce=nom, cruce_id=cid, grupo='SPP',
        flujo_lateral_diario=diario, flujo_pico_h=pico, n_carriles_lateral=2.0,
        x_max=sa.x_max, capacidad_pico_h=bc.capacidad_h if bc else 900,
        balance_neto_vh=bal['balance_neto_vh'], beneficio_anual_clp=total))
    items.append(ItemCartera(nom, 'SPP', 'simulado', total, sa.x_max))
    prog.progress((i+1)/len(SIM), f'Simulado {nom}')
prog.empty()

anclas = caracterizar_anclas(anclas_raw)
cap_ref = estimar_capacidad_pico_ref(anclas)

# --- Extrapolar ---
extrap_rows = []
for cid, (nom, grupo, ncarr) in EXTRAP.items():
    diario, pico = flujos_cruce(cid)
    ex = extrapolar_cruce(nom, cid, grupo, diario, pico, ncarr, anclas, cap_ref)
    items.append(ItemCartera(nom, grupo, 'extrapolado', ex.beneficio_estimado_clp, ex.x_estimado))
    extrap_rows.append(ex)

# --- Tabla de cruces ---
st.subheader('Cruces de la cartera')
df = pd.DataFrame([{
    'Cruce': it.cruce, 'Grupo': it.grupo, 'Origen': it.origen,
    'x': round(it.x, 2),
    'Beneficio anual CLP': round(it.beneficio_anual_clp),
    'Aporta': '✅' if it.beneficio_anual_clp > 0 else '❌',
} for it in items])
st.dataframe(df, use_container_width=True, hide_index=True)

# --- Tres escenarios ---
st.subheader('Indicadores SNI — tres escenarios de alcance')
esc = []
rA = evaluar_cartera(items, costo_total_uf=costo_uf, nombre_escenario='A. Completa',
                     crecimiento_demanda=crec, horizonte_anios=horizonte)
rB = evaluar_cartera(items, costo_total_uf=costo_uf, nombre_escenario='B. Solo positivos (costo total)',
                     crecimiento_demanda=crec, horizonte_anios=horizonte, solo_positivos=True)
items_pos = [it for it in items if it.beneficio_anual_clp > 0]
costo_red = costo_uf * len(items_pos) / len(items)
rC = evaluar_cartera(items_pos, costo_total_uf=costo_red,
                     nombre_escenario=f'C. Optimizado ({len(items_pos)} cruces)',
                     crecimiento_demanda=crec, horizonte_anios=horizonte)
for r in (rA, rB, rC):
    cols = st.columns(5)
    cols[0].metric(r.nombre_escenario, f'{r.costo_total_uf:,.0f} UF')
    cols[1].metric('Beneficio año 0', f'{r.beneficio_anual_inicial_clp/1e6:,.0f} MM')
    cols[2].metric('VAN', f'{r.van_clp/1e6:,.0f} MM',
                   '✅' if r.van_clp > 0 else '❌')
    cols[3].metric('TIR', f'{r.tir*100:.1f} %' if r.tir else '—')
    cols[4].metric('B/C', f'{r.relacion_b_c:.2f}')

# --- Cortes temporales del escenario óptimo ---
st.subheader('Cortes temporales — escenario optimizado')
cols = st.columns(3)
for i, c in enumerate(rC.cortes):
    cols[i].metric(f'Año {c.anio}', f'CLP {c.beneficio_anual_clp/1e6:,.0f} MM')

# --- Detalle extrapolación ---
with st.expander('Detalle de la extrapolación (régimen de saturación)'):
    df_ex = pd.DataFrame([{
        'Cruce': e.cruce, 'Grupo': e.grupo, 'x estimado': round(e.x_estimado, 2),
        'Régimen': e.regimen, 'Beneficio CLP': round(e.beneficio_estimado_clp),
        'Banda CLP': f'[{e.beneficio_min_clp/1e6:,.0f} .. {e.beneficio_max_clp/1e6:,.0f}] MM',
        'Advertencia': e.advertencia,
    } for e in extrap_rows])
    st.dataframe(df_ex, use_container_width=True, hide_index=True)

con.close()
