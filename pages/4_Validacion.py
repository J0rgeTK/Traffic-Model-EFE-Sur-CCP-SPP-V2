"""Página de administración / validación de insumos."""
import pandas as pd
import streamlit as st

import datos
from modelo_cruces import validadores as val

st.set_page_config(page_title='Validación', page_icon='✅', layout='wide')
st.title('Validación de insumos')
st.caption('Ejecuta las reglas de integridad sobre las tres bases antes de '
           'confiar en los resultados.')

con = datos.conectar()
hallazgos = val.validar_todo(con)
r = val.resumen(hallazgos)

c = st.columns(3)
c[0].metric('Errores', r['errores'])
c[1].metric('Advertencias', r['advertencias'])
c[2].metric('Estado', 'OK' if r['ok'] else 'CON ERRORES')

if not hallazgos:
    st.success('Todas las reglas de integridad se cumplen.')
else:
    st.dataframe(
        pd.DataFrame([{'Nivel': h.nivel, 'Regla': h.regla, 'Detalle': h.detalle}
                      for h in hallazgos]),
        use_container_width=True, hide_index=True)

st.subheader('Catálogo de variantes detectado')
st.caption('Modelo aplicable a cada cruce, combinando detección por datos '
           '(programación v2 distinta de v1) y declaración operacional '
           '(tabla cruces_reconfiguracion).')
filas = []
for c in datos.catalogo(con):
    cod = c.proyecto.codigo_proyecto if c.proyecto else None
    filas.append({
        'Cruce': c.cruce, 'Comuna': c.comuna,
        'En proyecto': 'Sí' if c.en_proyecto else 'No',
        'Código': cod or '',
        'Modelo': c.etiqueta_modelo,
        'Variantes': len(c.variantes),
        'Simulable': 'Sí' if c.simulable else 'No',
    })
st.dataframe(filas, use_container_width=True, hide_index=True)
con.close()
