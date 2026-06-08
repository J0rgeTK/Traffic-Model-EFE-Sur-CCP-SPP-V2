"""Sección 3 — Base de datos: estructura, contenido, itinerario y buses."""
import pandas as pd
import altair as alt
import streamlit as st

import datos

st.set_page_config(page_title='Base de datos', page_icon='🗄️', layout='wide')
st.title('3 · Base de datos')
st.caption('Estructura y contenido de la información que alimenta el modelo.')

st.markdown("""
El programa organiza la información del corredor en bases de datos
relacionales separadas por dominio: infraestructura, demanda y operación
ferroviaria. Cada dato tiene una fuente y una ubicación definidas, y las
consultas combinan los dominios según se necesite.
""")

con = datos.conectar(); cur = con.cursor()
nombres = {r['cruce_id']: r['nombre'] for r in
           cur.execute("SELECT cruce_id, nombre FROM infra.cruces").fetchall()}

# --- Flujos vehiculares ---
st.subheader('Flujos vehiculares')
camp = datos.listar_campanias(con)[0]
rows = cur.execute(
    "SELECT cruce_id, COUNT(*) n, MIN(flujo_veh_h) mn, MAX(flujo_veh_h) mx, AVG(flujo_veh_h) av "
    "FROM dem.llegadas_vehiculares WHERE campania_id=? GROUP BY cruce_id ORDER BY cruce_id",
    (camp['campania_id'],)).fetchall()
if rows:
    df = pd.DataFrame([{'Cruce': nombres.get(r['cruce_id']), 'Bandas': r['n'],
        'Mín (v/h)': round(r['mn']), 'Máx (v/h)': round(r['mx']),
        'Medio (v/h)': round(r['av'])} for r in rows])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f'Campaña vigente: {camp["nombre"]}, por banda horaria de una hora.')

# --- Diagrama de Marey ---
st.subheader('Itinerario del servicio Biotrén — diagrama de Marey (Línea 2)')
st.markdown("""
El diagrama de Marey representa la operación del servicio en el plano
tiempo–distancia: el eje vertical recorre la línea de norte a sur, de
Concepción (km 0) a Coronel (km 27), y el horizontal es la hora del día.
Cada línea es una circulación; su pendiente indica la velocidad y los
cruces entre líneas, los encuentros entre trenes. Las posiciones en el eje
vertical son proporcionales a la distancia real, obtenida de las
coordenadas geográficas.
""")

# Datos de circulaciones
serv = {r['service_id']: r['sentido'] for r in
        cur.execute("SELECT service_id, sentido FROM dem.itin_l2_servicios").fetchall()}
filas = []
for r in cur.execute("SELECT service_id, dist_km, llega_s, sale_s FROM dem.itin_l2_horarios "
                     "ORDER BY service_id, orden").fetchall():
    t = r['sale_s'] if r['sale_s'] is not None else r['llega_s']
    if t is not None and r['dist_km'] is not None:
        sentido = serv.get(r['service_id']) or ''
        filas.append({'servicio': r['service_id'], 'hora': t/3600.0, 'km': r['dist_km'],
                      'Sentido': 'Concepción → Coronel' if sentido[:2] == 'CC'
                                 else 'Coronel → Concepción'})
df_serv = pd.DataFrame(filas)

# Cruces y estaciones en el eje
cruces = pd.DataFrame([{'nombre': r['nombre'], 'km': r['dist_km'],
    'Tipo': 'Cruce evaluado' if r['evaluacion'] else 'Cruce no evaluado'}
    for r in cur.execute("""SELECT c.nombre, a.dist_km, a.evaluacion
        FROM infra.antecedentes_cruce a JOIN infra.cruces c ON c.cruce_id=a.cruce_id
        WHERE a.dist_km IS NOT NULL ORDER BY a.dist_km""").fetchall()])
estaciones = pd.DataFrame([{'nombre': r['nombre'], 'km': r['dist_km']}
    for r in cur.execute("SELECT nombre, dist_km FROM infra.estaciones_l2 "
        "WHERE dist_km IS NOT NULL ORDER BY dist_km").fetchall()])

if not df_serv.empty:
    tick30 = [h/2 for h in range(12, 45)]  # 6.0 .. 22.0 cada 0.5
    fmt = "(datum.value < 10 ? '0' : '') + floor(datum.value) + ':' + ((datum.value % 1) == 0 ? '00' : '30')"
    xenc = alt.X('hora:Q', title='Hora del día',
                 scale=alt.Scale(domain=[6, 22.5]),
                 axis=alt.Axis(values=tick30, labelExpr=fmt, labelAngle=-90, grid=True))
    yenc = alt.Y('km:Q', title='Distancia desde Concepción (km)',
                 scale=alt.Scale(domain=[27.5, -0.5]))

    lineas = alt.Chart(df_serv).mark_line(strokeWidth=1, opacity=0.6).encode(
        x=xenc, y=yenc, detail='servicio:N',
        color=alt.Color('Sentido:N', scale=alt.Scale(
            domain=['Concepción → Coronel', 'Coronel → Concepción'],
            range=['#1f6fb2', '#d97a2b']),
            legend=alt.Legend(orient='bottom')))

    reglas_cruces = alt.Chart(cruces).mark_rule(opacity=0.5, strokeDash=[2, 2]).encode(
        y='km:Q',
        color=alt.Color('Tipo:N', scale=alt.Scale(
            domain=['Cruce evaluado', 'Cruce no evaluado'],
            range=['#2e7d32', '#bbbbbb']), legend=alt.Legend(orient='bottom')))
    texto_cruces = alt.Chart(cruces).mark_text(align='left', dx=4, fontSize=8).encode(
        x=alt.value(660), y='km:Q', text='nombre:N',
        color=alt.Color('Tipo:N', scale=alt.Scale(
            domain=['Cruce evaluado', 'Cruce no evaluado'],
            range=['#2e7d32', '#999999']), legend=None))
    texto_est = alt.Chart(estaciones).mark_text(align='right', dx=-4, fontSize=8,
        color='#555555').encode(x=alt.value(95), y='km:Q', text='nombre:N')

    chart = (lineas + reglas_cruces + texto_cruces + texto_est).properties(
        width=560, height=620).resolve_scale(color='independent')
    st.altair_chart(chart, use_container_width=True)
    st.caption(f'{df_serv["servicio"].nunique()} circulaciones de día laboral. '
               'Etiquetas verdes: cruces evaluados; grises: no evaluados. '
               'Se aprecian las dos puntas de operación, mañana y tarde.')

# --- Líneas de buses ---
st.subheader('Líneas de transporte público por cruce')
st.markdown("""
La frecuencia de buses por cruce y hora permite estimar la composición del
flujo: de los vehículos aforados en cada hora, una fracción son buses (con
mayor ocupación) y el resto, livianos. El flujo total se mantiene; lo que
cambia es la ocupación media, y con ella el beneficio en pasajeros-hora.
""")
bus = cur.execute("""SELECT cruce_id, COUNT(DISTINCT linea_tp) lineas, SUM(buses_hora) bd
    FROM dem.buses_cruce GROUP BY cruce_id ORDER BY SUM(buses_hora) DESC""").fetchall()
if bus:
    dfb = pd.DataFrame([{'Cruce': nombres.get(r['cruce_id']),
        'Líneas TP': r['lineas'], 'Buses/día (suma horas)': int(r['bd'])} for r in bus])
    st.dataframe(dfb, use_container_width=True, hide_index=True)
    st.caption('Se aplica una ocupación de 20 pasajeros por bus para calcular la '
               'ocupación efectiva de cada cruce (ver sección de Cartera).')

con.close()
