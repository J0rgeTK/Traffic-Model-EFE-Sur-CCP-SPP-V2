"""Sección 3 — Base de datos: estructura, contenido, itinerario y buses."""
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

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

# Servicios y sus paradas
serv = {r['service_id']: r['sentido'] for r in
        cur.execute("SELECT service_id, sentido FROM dem.itin_l2_servicios").fetchall()}
paradas = {}
for r in cur.execute("SELECT service_id, dist_km, llega_s, sale_s FROM dem.itin_l2_horarios "
                     "ORDER BY service_id, orden").fetchall():
    t = r['sale_s'] if r['sale_s'] is not None else r['llega_s']
    if t is not None and r['dist_km'] is not None:
        paradas.setdefault(r['service_id'], []).append((t/3600.0, r['dist_km']))

# Estaciones y cruces en el eje Y
estaciones = cur.execute("SELECT nombre, dist_km FROM infra.estaciones_l2 "
                         "WHERE dist_km IS NOT NULL ORDER BY dist_km").fetchall()
cruces = cur.execute("""SELECT c.nombre, a.dist_km, a.evaluacion FROM infra.antecedentes_cruce a
    JOIN infra.cruces c ON c.cruce_id=a.cruce_id WHERE a.dist_km IS NOT NULL
    ORDER BY a.dist_km""").fetchall()

fig, ax = plt.subplots(figsize=(12, 8))
C_CCW, C_CWC = '#1f6fb2', '#d97a2b'
for sid, ps in paradas.items():
    if len(ps) < 2: continue
    xs, ys = zip(*ps)
    es_ida = 'CC' in (serv.get(sid) or '')[:2]  # CC->CW = Concepción->Coronel
    ax.plot(xs, ys, color=C_CCW if es_ida else C_CWC, lw=0.8, alpha=0.65)

# Cruces ferroviarios (líneas horizontales)
for cnt in cruces:
    ev = cnt['evaluacion']
    ax.axhline(cnt['dist_km'], ls=':', lw=0.7,
               color='#2e7d32' if ev else '#bbbbbb', alpha=0.7 if ev else 0.5)
    ax.text(22.05, cnt['dist_km'], cnt['nombre'], va='center', ha='left',
            fontsize=6.5, color='#2e7d32' if ev else '#999999')

# Estaciones (marcas en eje izquierdo)
ax.set_yticks([e['dist_km'] for e in estaciones])
ax.set_yticklabels([f"{e['nombre']} ({e['dist_km']:.0f})" for e in estaciones], fontsize=7)

ax.set_ylim(27.5, -0.5)                       # Concepción arriba, Coronel abajo
ax.set_xlim(6, 22)
ax.set_xticks(np.arange(6, 22.01, 0.5))            # cada 30 min
ax.set_xticklabels([f'{int(h):02d}:{int((h%1)*60):02d}'
                    for h in np.arange(6, 22.01, 0.5)], rotation=90, fontsize=7)
ax.set_xlabel('Hora del día'); ax.set_ylabel('Distancia desde Concepción (km)')
ax.grid(True, axis='x', ls='-', lw=0.3, alpha=0.3)
ax.set_title('Circulaciones Biotrén L2 — día laboral', fontsize=11)
from matplotlib.lines import Line2D
ax.legend(handles=[Line2D([0],[0],color=C_CCW,label='Concepción → Coronel'),
                   Line2D([0],[0],color=C_CWC,label='Coronel → Concepción'),
                   Line2D([0],[0],color='#2e7d32',ls=':',label='Cruce evaluado'),
                   Line2D([0],[0],color='#bbbbbb',ls=':',label='Cruce no evaluado')],
          loc='lower left', fontsize=7, framealpha=0.9)
plt.tight_layout()
st.pyplot(fig)
st.caption(f'{len(paradas)} circulaciones de día laboral. Las etiquetas verdes '
           'son los cruces evaluados; las grises, los no evaluados. Se aprecian '
           'las dos puntas de operación, mañana y tarde.')

# --- Líneas de buses ---
st.subheader('Líneas de transporte público por cruce')
st.markdown("""
La frecuencia de buses por cruce y hora permite estimar la composición del
flujo: de los vehículos aforados en cada hora, una fracción son buses (con
mayor ocupación) y el resto, livianos. El flujo total se mantiene; lo que
cambia es la ocupación media, y con ella el beneficio en pasajeros-hora.
""")
bus = cur.execute("""SELECT cruce_id, COUNT(DISTINCT linea_tp) lineas, SUM(buses_hora) bd,
    MAX(hora) FROM dem.buses_cruce GROUP BY cruce_id ORDER BY SUM(buses_hora) DESC""").fetchall()
if bus:
    dfb = pd.DataFrame([{'Cruce': nombres.get(r['cruce_id']),
        'Líneas TP': r['lineas'], 'Buses/día (suma horas)': int(r['bd'])} for r in bus])
    st.dataframe(dfb, use_container_width=True, hide_index=True)
    st.caption('Se aplica una ocupación de 20 pasajeros por bus, frente a la '
               'ocupación de vehículo liviano, para calcular la ocupación '
               'efectiva de cada cruce (ver sección de Cartera).')

con.close()
