"""
Programa de evaluacion — Mejoramiento de Semaforizacion en Cruces
Ferroviarios, Servicio Biotren, Gran Concepcion.

Portada y navegacion. Las secciones estan en pages/ y aparecen en el
menu lateral, en orden de lectura.
"""
import streamlit as st
import datos

st.set_page_config(page_title='Semaforizacion Cruces Biotren — Programa de evaluacion',
                   page_icon='🚦', layout='wide')

st.title('Mejoramiento Sistema de Semaforización en Cruces a Nivel '
         'Ferroviarios')
st.subheader('Servicio Biotrén — Gran Concepción · Programa de evaluación técnico-económica')

st.markdown("""
Este programa integra, en un solo entorno, la evaluación técnica y
económica del proyecto de integración **GPS–SCATS** del servicio Biotrén
a la gestión semafórica del Gran Concepción. Reúne la base de datos del
corredor, el motor de simulación de la operación semáforo–barrera, las
metodologías de cuantificación de beneficios y la evaluación social de la
cartera de cruces.

El propósito del entorno es procesar de forma eficiente y trazable los
datos del corredor —flujos vehiculares, programaciones semafóricas e
itinerario ferroviario— y producir los indicadores que respaldan la
formulación del proyecto.
""")

st.divider()
st.markdown('### Cómo está organizado el programa')

secciones = [
    ('1 · Cruces estudiados',
     'El universo de cruces del corredor, su tipología operacional y su '
     'ubicación. Define qué cruces se evalúan y bajo qué modelo.'),
    ('2 · Supuestos y consideraciones',
     'Todos los parámetros de cálculo y decisiones metodológicas en un '
     'solo lugar: valor social del tiempo, tasa de descuento, horizonte, '
     'headway, ocupación, crecimiento de demanda.'),
    ('3 · Base de datos',
     'Estructura y contenido de la información que alimenta el modelo: '
     'flujos vehiculares, programaciones semafóricas, itinerario '
     'ferroviario e infraestructura de cada cruce.'),
    ('4 · Metodologías',
     'Las metodologías empleadas y su justificación: simulación segundo a '
     'segundo, corrección de saturación, marco incremental de evaluación '
     'y valoración social.'),
    ('5 · Simulación',
     'Herramienta de simulación de la operación de un cruce: estados del '
     'semáforo y la barrera, formación y disipación de cola.'),
    ('6 · Cartera y evaluación',
     'La cartera del proyecto: cruces evaluados, beneficio incremental, '
     'agrupación por zona e indicadores económicos (VAN, TIR, B/C).'),
]
cols = st.columns(2)
for i, (titulo, desc) in enumerate(secciones):
    with cols[i % 2]:
        st.markdown(f'**{titulo}**')
        st.caption(desc)

st.divider()

con = datos.conectar()
n_cruces = con.execute('SELECT count(*) FROM infra.cruces').fetchone()[0]
n_sim = len(datos.cruces_simulables(con))
c1, c2, c3 = st.columns(3)
c1.metric('Cruces en el corredor', n_cruces)
c2.metric('Cruces con simulación directa', n_sim)
c3.metric('Horizonte de evaluación', '20 años')
con.close()

st.caption('Use el menú lateral para navegar las secciones en orden.')
