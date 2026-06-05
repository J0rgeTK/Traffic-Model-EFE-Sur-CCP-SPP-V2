"""Sección 4 — Metodologías utilizadas y su justificación."""
import streamlit as st

st.set_page_config(page_title='Metodologías', page_icon='📐', layout='wide')
st.title('4 · Metodologías utilizadas y justificación')
st.caption('Qué método se aplica en cada etapa de la evaluación y por qué '
           'es el apropiado.')

st.markdown("""
La evaluación combina cuatro metodologías encadenadas. Cada una responde a
una pregunta distinta y está justificada por la naturaleza del problema y
por el principio de proporcionalidad del Sistema Nacional de Inversiones.
""")

with st.expander('1 · Simulación discreta segundo a segundo', expanded=True):
    st.markdown("""
**Qué hace.** Para cada cruce y cada pasada del tren, reproduce segundo a
segundo el estado del semáforo (fase activa, tiempo restante), el estado
de la barrera y la acumulación y disipación de la cola en las vías
laterales. El resultado es el tiempo que transcurre desde que la barrera
sube hasta que los vehículos del lateral obtienen verde.

**Por qué este método.** El impacto de cada pasada del tren depende del
estado exacto del semáforo en ese instante, que varía a lo largo del día.
Un modelo que trabaje con promedios de hora punta perdería esa
información. La simulación segundo a segundo es la herramienta que captura
la interacción real entre el itinerario ferroviario y el ciclo semafórico.

**Por qué no un modelo de asignación de red (tipo SATURN).** El proyecto
no redistribuye flujos: no cambia la capacidad de ninguna vía, no crea ni
elimina rutas; los conductores siguen los mismos recorridos. Los modelos
de red son pertinentes cuando hay redistribución (desniveles, nuevas
vías), no cuando solo cambia la calidad del servicio semafórico. Además,
esos modelos no representan fases condicionales al paso del tren ni la
dinámica de barreras. Por proporcionalidad, la simulación segundo a
segundo es el método correcto y suficiente.
""")

with st.expander('2 · Corrección de saturación (HCM / Akcelik) por banda horaria'):
    st.markdown("""
**Qué hace.** Cuando el grado de saturación de un movimiento supera ~0,85,
la cola deja de comportarse de forma estable. En ese régimen se aplica la
formulación del *Highway Capacity Manual* (componente uniforme de Webster
más componente incremental de Akcelik) banda horaria por banda horaria,
identificando las horas críticas.

**Por qué este método.** La demora no escala linealmente con el flujo
cerca de la saturación. Tratar todo el día con un promedio ocultaría las
horas punta, donde se concentra el impacto. La corrección por banda
entrega una medición representativa del régimen de cada hora.

**Régimen y método aplicable:**
- x ≤ 0,85 — operación estable, cálculo directo de la simulación.
- 0,85 < x ≤ 1,20 — saturación; se aplica la corrección analítica.
- x > 1,20 — sobre-saturación; se contrasta con microsimulación de
  eventos discretos para acotar el resultado.
""")

with st.expander('3 · Marco incremental de evaluación (situación sin / con proyecto)'):
    st.markdown("""
**Qué hace.** Separa el beneficio total de la optimización semafórica en
dos componentes: el que aporta la reconfiguración (verde inmediato a las
laterales) y el que aporta la integración GPS–SCATS por encima de ella.

**Por qué este método.** La reconfiguración es una medida de bajo costo
que pertenece a la situación base optimizada. El beneficio atribuible al
proyecto es únicamente el **incremental** de la integración GPS sobre esa
base. Medir el incremental, y no el total, es lo que exige el marco del
SNI para no sobreestimar la rentabilidad del proyecto.

**Componentes del beneficio del proyecto.** Además del ahorro de tiempo
incremental, el marco considera la seguridad operacional (despeje de la
zona de peligro antes del cierre de barrera), la confiabilidad del
transporte público, la optimización logística de carga y los beneficios
estratégicos de integración y escalabilidad.
""")

with st.expander('4 · Valoración social y evaluación de cartera'):
    st.markdown("""
**Qué hace.** Convierte el ahorro de tiempo (y las externalidades
asociadas) en beneficio social anual usando el valor social del tiempo, lo
proyecta sobre el horizonte de evaluación con la tasa social de descuento,
y agrega los cruces en una cartera con sus indicadores (VAN, TIR, B/C).

**Por qué este método.** El Análisis Costo-Beneficio es aplicable porque
el beneficio principal —ahorro de tiempo— es cuantificable y valorizable
con los precios sociales publicados. Permite calcular indicadores de
rentabilidad social, más sólidos que un análisis de costo-eficiencia.

**Tratamiento por tipología.** Cada cruce se evalúa con el modelo que
corresponde a su tipología operacional. Los cruces que no admiten el
proyecto (sin semáforo, o intersecciones clásicas) quedan fuera del
beneficio de la cartera; los que no tienen programación se estiman por
transferencia desde cruces análogos, con bandas de incertidumbre.
""")

st.divider()
st.markdown("""
**Tratamiento de la incertidumbre.** Los parámetros con mayor efecto sobre
el resultado —demanda, headway de saturación, precisión de la predicción
ferroviaria— se someten a análisis de sensibilidad. El resultado se
reporta como un rango con su probabilidad asociada, no como un punto
único, lo que refleja honestamente la confianza de la estimación.
""")
