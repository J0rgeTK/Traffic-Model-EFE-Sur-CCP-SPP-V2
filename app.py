"""
Modelo de cruces ferroviarios L2 - aplicacion Streamlit
=======================================================
Pagina principal. Las paginas de simulacion, mapa y comparacion estan
en la carpeta pages/ y aparecen en el menu lateral.
"""
import streamlit as st

import datos

st.set_page_config(
    page_title='Modelo cruces ferroviarios L2',
    page_icon='🚦',
    layout='wide',
)

st.title('Modelo de cruces ferroviarios — Línea 2 Biotren')
st.caption('Estimación de espera vehicular en cruces a nivel con prioridad '
           'semafórica GPS/SCATS (pre-vaciado N2)')

st.markdown("""
Esta aplicación reemplaza el modelo en planilla Excel por un motor de
simulación en Python, validado celda a celda contra el original, leyendo
desde bases de datos relacionales separadas.

**Cómo está organizado**

- **Simulación** — corre el modelo segundo a segundo para un cruce y
  compara el escenario base con el pre-vaciado.
- **Mapa** — ubica los cruces de la línea sobre el territorio.
- **Comparación** — contrasta varios cruces y muestra el efecto de los
  errores detectados en el modelo Excel (ventana de 3 h vs 15 h).
""")

con = datos.conectar()

c1, c2, c3 = st.columns(3)
n_cruces = con.execute('SELECT count(*) FROM infra.cruces').fetchone()[0]
n_sim = len(datos.cruces_simulables(con))
n_esc = con.execute('SELECT count(*) FROM escenarios').fetchone()[0]
c1.metric('Cruces en la base', n_cruces)
c2.metric('Cruces simulables', n_sim)
c3.metric('Escenarios guardados', n_esc)

st.subheader('Cruces simulables')
st.caption('Cruces que tienen aforos vehiculares y eventos de barrera cargados.')
filas = con.execute("""
    SELECT c.nombre AS Cruce, c.comuna AS Comuna,
           c.num_pistas_total AS Pistas,
           CASE c.tiene_semaforo WHEN 1 THEN 'Sí' ELSE 'No' END AS Semáforo,
           c.sentido_afectacion AS Sentido
    FROM   infra.cruces c
    WHERE  c.nombre IN (%s)
    ORDER  BY c.nombre
""" % ','.join('?' * n_sim), datos.cruces_simulables(con)).fetchall()
st.dataframe([dict(f) for f in filas], use_container_width=True, hide_index=True)

st.info('Modelo de referencia: cola determinística de Newell + preempción '
        'anticipada de cruce ferroviario. Las cifras del modelo deben '
        'interpretarse junto con el informe de verificación del motor.')

con.close()
