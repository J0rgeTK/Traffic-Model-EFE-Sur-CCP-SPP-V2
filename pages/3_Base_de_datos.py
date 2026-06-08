"""Sección 3 — Base de datos: estructura, contenido e itinerario ferroviario."""
import numpy as np
import pandas as pd
import streamlit as st

import datos

st.set_page_config(page_title='Base de datos', page_icon='🗄️', layout='wide')
st.title('3 · Base de datos')
st.caption('Estructura y contenido de la información que alimenta el modelo.')

st.markdown("""
El programa organiza la información del corredor en bases de datos
relacionales separadas por dominio. Este diseño permite un procesamiento
eficiente y trazable: cada dato tiene una fuente y una ubicación
definidas, y las consultas combinan los dominios según se necesite.
""")

con = datos.conectar(); cur = con.cursor()

st.subheader('Dominios de datos')
st.dataframe(pd.DataFrame([
    {'Dominio': 'Infraestructura', 'Contenido': 'Cruces, semáforos, '
     'programaciones semafóricas, modelo operacional, parámetros de barrera, '
     'estaciones y geometría.'},
    {'Dominio': 'Demanda', 'Contenido': 'Flujos vehiculares por cruce, '
     'banda horaria y tipo de día; campañas de medición.'},
    {'Dominio': 'Operación ferroviaria', 'Contenido': 'Itinerario del '
     'servicio, pasadas por cruce e instantes de cierre de barrera (HCALL).'},
], columns=['Dominio', 'Contenido']),
    use_container_width=True, hide_index=True)

# --- Flujos vehiculares ---
st.subheader('Flujos vehiculares')
camp = datos.listar_campanias(con)[0]
rows = cur.execute(
    "SELECT cruce_id, COUNT(*) n, MIN(flujo_veh_h) mn, MAX(flujo_veh_h) mx, "
    "AVG(flujo_veh_h) av FROM dem.llegadas_vehiculares WHERE campania_id=? "
    "GROUP BY cruce_id ORDER BY cruce_id", (camp['campania_id'],)).fetchall()
nombres = {r['cruce_id']: r['nombre'] for r in
           cur.execute("SELECT cruce_id, nombre FROM infra.cruces").fetchall()}
if rows:
    df = pd.DataFrame([{
        'Cruce': nombres.get(r['cruce_id'], f"#{r['cruce_id']}"),
        'Bandas horarias': r['n'], 'Flujo mín (v/h)': round(r['mn']),
        'Flujo máx (v/h)': round(r['mx']), 'Flujo medio (v/h)': round(r['av']),
    } for r in rows])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f'Campaña vigente: {camp["nombre"]}. {len(rows)} cruces con flujo '
               'medido, desagregado por banda horaria de una hora.')

# --- Programaciones ---
st.subheader('Programaciones semafóricas')
prog = cur.execute("SELECT cruce_id, COUNT(*) n FROM infra.planes_horarios_cruce "
                   "GROUP BY cruce_id ORDER BY cruce_id").fetchall()
if prog:
    dfp = pd.DataFrame([{'Cruce': nombres.get(r['cruce_id'], f"#{r['cruce_id']}"),
                         'Planes horarios registrados': r['n']} for r in prog])
    st.caption(f'{len(prog)} cruces con programación semafórica registrada '
               '(ciclo, fases y repartos por banda horaria).')

# --- Itinerario del servicio Biotrén ---
st.subheader('Itinerario del servicio Biotrén — Línea 2')
itv = cur.execute("SELECT nombre, descripcion FROM dem.itinerario_versiones "
                  "WHERE itinerario_id=1").fetchone()
if itv:
    st.markdown(f"**{itv['nombre']}.** {itv['descripcion']}.")

# Traza de estaciones
est = cur.execute("SELECT nombre, orden_linea FROM infra.estaciones "
                  "ORDER BY orden_linea").fetchall()
if est:
    traza = '  →  '.join(e['nombre'] for e in est)
    st.markdown(f'**Traza de la línea ({len(est)} estaciones):**')
    st.markdown(f'<div style="font-size:0.85em;color:#444">{traza}</div>',
                unsafe_allow_html=True)

# Perfil horario de pasadas
st.markdown('**Frecuencia del servicio a lo largo del día**')
total_eventos = cur.execute("SELECT COUNT(*) FROM dem.eventos_barrera "
                            "WHERE itinerario_id=1").fetchone()[0]
n_cruces_it = cur.execute("SELECT COUNT(DISTINCT cruce_id) FROM dem.eventos_barrera "
                          "WHERE itinerario_id=1").fetchone()[0]
perfil = []
for h in range(5, 24):
    n = cur.execute("SELECT COUNT(*) FROM dem.eventos_barrera WHERE itinerario_id=1 "
                    "AND instante_paso_s>=? AND instante_paso_s<?",
                    (h*3600, (h+1)*3600)).fetchone()[0]
    # pasadas por hora promediadas por cruce (n eventos / n cruces)
    perfil.append({'Hora': f'{h:02d}h', 'Pasadas/hora (media por cruce)':
                   round(n / max(1, n_cruces_it), 1)})
dfh = pd.DataFrame(perfil).set_index('Hora')
st.bar_chart(dfh, height=240)
st.caption('El servicio presenta dos puntas —mañana y tarde— características '
           'de un servicio de cercanías, separadas por un valle de mediodía. '
           'Cada cruce registra del orden de un centenar de pasadas en un día.')

# Pasadas y tiempos de barrera por cruce
pasadas = cur.execute("""SELECT e.cruce_id, COUNT(*) n,
    AVG(e.hcall_out_s - e.hcall_in_s) hcall, AVG(b.tiempo_barrera_s) tb
    FROM dem.eventos_barrera e
    LEFT JOIN infra.parametros_barrera b ON b.cruce_id=e.cruce_id
    WHERE e.itinerario_id=1 GROUP BY e.cruce_id ORDER BY e.cruce_id""").fetchall()
if pasadas:
    dfb = pd.DataFrame([{
        'Cruce': nombres.get(r['cruce_id'], f"#{r['cruce_id']}"),
        'Pasadas/día': r['n'],
        'HCALL medio (s)': round(r['hcall']) if r['hcall'] else '—',
        'Tiempo barrera medio (s)': round(r['tb']) if r['tb'] else '—',
    } for r in pasadas])
    with st.expander('Pasadas e impacto de barrera por cruce'):
        st.dataframe(dfb, use_container_width=True, hide_index=True)
        st.caption(f'Itinerario de referencia: {total_eventos} eventos de paso '
                   f'registrados sobre {n_cruces_it} cruces. El HCALL medio es el '
                   'tiempo medio que la barrera permanece activa en cada pasada.')

con.close()
