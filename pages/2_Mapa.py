"""Página de mapa: ubica los cruces de la Línea 2 sobre el territorio."""
import pandas as pd
import pydeck as pdk
import streamlit as st

import datos

st.set_page_config(page_title='Mapa', page_icon='🗺️', layout='wide')
st.title('Mapa de cruces — Línea 2')

con = datos.conectar()
simulables = set(datos.cruces_simulables(con))

filas = []
for r in datos.listar_cruces(con):
    if r['latitud'] is None or r['longitud'] is None:
        continue
    es_sim = r['nombre'] in simulables
    filas.append({
        'cruce_id': r['cruce_id'], 'nombre': r['nombre'],
        'comuna': r['comuna'], 'lat': r['latitud'], 'lon': r['longitud'],
        'pistas': r['num_pistas_total'] or 2,
        'semaforo': 'Sí' if r['tiene_semaforo'] else 'No',
        'simulable': 'Sí' if es_sim else 'No',
        # color: cruces simulables en azul, el resto en gris
        'color': [55, 138, 221] if es_sim else [150, 150, 150],
        'radio': 90 if es_sim else 55,
    })
con.close()

if not filas:
    st.warning('No hay cruces con georreferencia en la base.')
    st.stop()

df = pd.DataFrame(filas)
st.caption(f'{len(df)} cruces georreferenciados. '
           'En azul, los cruces con datos suficientes para simular.')

centro_lat = df['lat'].mean()
centro_lon = df['lon'].mean()

capa = pdk.Layer(
    'ScatterplotLayer', data=df,
    get_position='[lon, lat]', get_fill_color='color',
    get_radius='radio', pickable=True, opacity=0.8,
    stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=1,
)
tooltip = {
    'html': '<b>{nombre}</b><br/>Comuna: {comuna}<br/>'
            'Pistas: {pistas} &nbsp; Semáforo: {semaforo}<br/>'
            'Simulable: {simulable}',
    'style': {'backgroundColor': '#0c447c', 'color': 'white'},
}
st.pydeck_chart(pdk.Deck(
    map_style=None,
    initial_view_state=pdk.ViewState(
        latitude=centro_lat, longitude=centro_lon, zoom=11.5, pitch=0),
    layers=[capa], tooltip=tooltip,
))

st.subheader('Detalle de cruces')
st.dataframe(
    df[['nombre', 'comuna', 'pistas', 'semaforo', 'simulable', 'lat', 'lon']],
    use_container_width=True, hide_index=True)
