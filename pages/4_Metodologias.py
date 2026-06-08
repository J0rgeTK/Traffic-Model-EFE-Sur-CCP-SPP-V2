"""Sección 4 — Metodología detallada del modelo y su justificación."""
import streamlit as st

st.set_page_config(page_title='Metodología', page_icon='📐', layout='wide')
st.title('4 · Metodología del modelo')
st.caption('Formulación del problema, métodos de cálculo paso a paso y su '
           'fundamento, para una lectura informada de los resultados.')

st.markdown("""
La evaluación se inscribe en el Sistema Nacional de Inversiones (SNI) y
adopta el Análisis Costo-Beneficio. Combina cuatro métodos encadenados:
una simulación de la operación segundo a segundo, una corrección analítica
de saturación, la valoración social del tiempo y la evaluación económica.
Esta sección documenta cada uno con sus ecuaciones, de modo que cada
resultado sea trazable hasta su método de cálculo.
""")

# --- Marco incremental ---
st.subheader('Marco de evaluación incremental')
st.markdown("""
Siguiendo el principio de comparación del SNI, se distinguen tres
situaciones, y el beneficio del proyecto es el **incremento de la última
sobre la segunda**:
""")
c = st.columns(3)
c[0].markdown('**Situación actual**\n\nOperación vigente, sin intervención.')
c[1].markdown('**Sin proyecto (base optimizada)**\n\nReconfiguración semafórica: '
              'verde inmediato a las laterales tras el tren.')
c[2].markdown('**Con proyecto**\n\nReconfiguración + integración GPS–SCATS con '
              'pre-vaciado predictivo.')
st.info('El beneficio atribuible al proyecto es el incremental de la '
        'integración GPS–SCATS sobre la base ya reconfigurada, no sobre la '
        'situación actual. Atribuirle el beneficio de la reconfiguración —que '
        'pertenece a la base sin proyecto— sobreestimaría su rentabilidad.')

# --- Método 1: simulación ---
with st.expander('Método 1 · Simulación de colas segundo a segundo', expanded=True):
    st.markdown("""
El núcleo del modelo es una simulación determinística de colas en tiempo
discreto (pasos de un segundo), basada en el método de **curvas
acumulativas de llegadas y salidas** (Newell, 1982; May, 1990). A
diferencia de los modelos de promedios horarios, representa el estado
exacto del semáforo y de la barrera en cada instante, lo que es
indispensable para capturar la interacción con cada pasada del tren.

**Capacidad instantánea.** La tasa de servicio en cada segundo es el flujo
de saturación por el indicador de verde efectivo *g(t)* (1 si el
movimiento lateral tiene paso y la barrera está arriba; 0 en otro caso):
""")
    st.latex(r'c(t) = g(t)\cdot s = g(t)\cdot \frac{N}{h}')
    st.markdown('con *N* el número de pistas del movimiento y *h* el headway '
                'de saturación (s/veh).')
    st.markdown('**Balance de la cola.** En cada segundo se sirven tantos '
                'vehículos como permita el menor valor entre la capacidad y la '
                'cola disponible; la cola remanente es:')
    st.latex(r'd(t) = \min\{\,c(t),\; Q(t-1)+q(t)\,\}')
    st.latex(r'Q(t) = \max\{\,0,\; Q(t-1)+q(t)-d(t)\,\}')
    st.markdown('donde *q(t)* es la tasa de llegada (veh/s). El tiempo total '
                'de detención del día se obtiene integrando la cola:')
    st.latex(r'W = \sum_{t} Q(t)\,\Delta t \quad (\Delta t = 1\ \text{s}),\ \text{en veh·h}')
    st.markdown("""
**Hurry Call y reconfiguración.** La rutina HCALL anula el verde lateral
durante el cierre de barrera de cada pasada. La reconfiguración (situación
sin proyecto) reinicia el ciclo otorgando verde inmediato a la lateral al
terminar el HCALL. El **pre-vaciado** (componente del proyecto) usa la
predicción del tiempo de llegada del tren (ETA por GPS) para adelantar el
despeje de la cola antes del descenso de la barrera; su beneficio es la
diferencia de detención con y sin este mecanismo, sobre la base
reconfigurada.
""")

# --- Método 2: saturación ---
with st.expander('Método 2 · Corrección analítica por saturación (HCM)'):
    st.markdown("""
Cerca y por encima de la capacidad, la demora deja de ser proporcional al
flujo. En esos regímenes se aplica, banda horaria por banda, la
formulación de demora en intersecciones semaforizadas del **Highway
Capacity Manual** (TRB, 2022), que descompone la demora media por
vehículo en un término uniforme y uno incremental:
""")
    st.latex(r'd = d_1\cdot PF + d_2')
    st.markdown('**Grado de saturación** de la banda (flujo sobre capacidad):')
    st.latex(r'X = \frac{q}{c}')
    st.markdown('**Retardo uniforme** (Webster, 1958), donde *C* es el ciclo y '
                '*g* el verde efectivo de la fase:')
    st.latex(r'd_1 = \frac{0{,}5\,C\,(1 - g/C)^2}{1 - \min(1,X)\,(g/C)}')
    st.markdown('**Retardo incremental** (Akçelik, 1988), donde *T* es el '
                'período de análisis (h), *c* la capacidad, *k = 0,50* para '
                'semáforos de tiempos fijos e *I = 1,0* para llegadas tipo '
                'Poisson sin coordinación:')
    st.latex(r'd_2 = 900\,T\left[(X-1) + \sqrt{(X-1)^2 + \frac{8\,k\,I\,X}{c\,T}}\right]')
    st.markdown('**Régimen y método aplicable:**')
    st.table({
        'Régimen': ['Estable', 'Saturación próxima', 'Sobre-saturación'],
        'Grado de saturación': ['X ≤ 0,85', '0,85 < X ≤ 1,20', 'X > 1,20'],
        'Método': ['Simulación directa', 'Corrección HCM (d₁·PF + d₂)',
                   'Contraste con microsimulación'],
    })
    st.caption('Umbrales según la práctica de ingeniería de tránsito '
               '(Roess, Prassas y McShane, 2019).')

# --- Método 3: valoración ---
with st.expander('Método 3 · Valoración social del beneficio'):
    st.markdown("""
El ahorro diario de detención se anualiza y se monetiza con los precios
sociales del Ministerio de Desarrollo Social y Familia:
""")
    st.latex(r'B = \Delta W \cdot D \cdot O \cdot VST \cdot f_e')
    st.markdown("""
donde *ΔW* es el ahorro diario de detención (veh·h), *D* los días
laborales equivalentes del año, *O* la ocupación media (pax/veh), *VST* el
valor social del tiempo (CLP por pax·h) y *fₑ* un ponderador del tiempo
detenido. El MDSF reconoce un valor del tiempo de espera igual al doble
del de viaje, lo que corresponde a *fₑ = 2,0*. A este beneficio se suman,
cuando corresponde, las externalidades por menor consumo de combustible y
emisiones en cola.
""")

# --- Método 4: evaluación económica ---
with st.expander('Método 4 · Evaluación económica'):
    st.markdown('El beneficio crece con la demanda y se descuenta a la tasa '
                'social *r*:')
    st.latex(r'B_t = B_0\,(1+\gamma)^{\,t-1}')
    st.latex(r'VAN = -I_0 + \sum_{t=1}^{n} \frac{B_t - R_t + L_t}{(1+r)^{t}}')
    st.markdown("""
donde *I₀* es la inversión inicial, *Rₜ* las reinversiones (reposición de
los equipos de posicionamiento al término de su vida útil), *Lₜ* el valor
residual y *n* el horizonte. La **TIR** es la tasa que anula el VAN
(resuelta por bisección) y la **relación B/C** es el cociente entre el
valor actual de beneficios y costos. Los parámetros —tasa de descuento,
horizonte, crecimiento, UF y ocupación— se documentan en la sección de
supuestos y son configurables.
""")

# --- Tipología e incertidumbre ---
with st.expander('Tratamiento por tipología e incertidumbre'):
    st.markdown("""
**Por tipología.** Los cruces semaforizados sobre el eje interurbano, con
movimiento lateral caracterizado, se evalúan con la simulación descrita.
Los cruces sin semáforo quedan fuera del alcance. Las intersecciones
urbanas de múltiples movimientos requieren un modelo específico y un
levantamiento de información, propios de una fase posterior. Un cruce
evaluable sin programación registrada se estima por transferencia desde
cruces análogos, con su banda de incertidumbre.

**Incertidumbre.** Los parámetros de mayor incidencia —demanda, headway de
saturación y precisión de la predicción del tren— se someten a análisis de
sensibilidad. La variabilidad del instante del HCALL se representa con
perturbaciones controladas (jitter), lo que permite evaluar la robustez
del beneficio del pre-vaciado.
""")

st.divider()
st.subheader('Referencias bibliográficas')
st.markdown("""
1. Akçelik, R. (1981). *Traffic Signals: Capacity and Timing Analysis*. Research Report ARR No. 123. Australian Road Research Board.
2. Akçelik, R. (1988). The Highway Capacity Manual delay formula for signalized intersections. *ITE Journal*, 58(3), 23–27.
3. Daganzo, C. F. (1997). *Fundamentals of Transportation and Traffic Operations*. Pergamon, Oxford.
4. May, A. D. (1990). *Traffic Flow Fundamentals*. Prentice-Hall.
5. Ministerio de Desarrollo Social y Familia. *Precios Sociales Vigentes* y *Metodología de Vialidad Urbana e Intermedia*. Sistema Nacional de Inversiones, Chile.
6. Newell, G. F. (1982). *Applications of Queueing Theory* (2.ª ed.). Chapman and Hall, Londres.
7. Roess, R. P., Prassas, E. S. y McShane, W. R. (2019). *Traffic Engineering* (5.ª ed.). Pearson.
8. SECTRA, Ministerio de Transportes y Telecomunicaciones. *Metodologías de evaluación de proyectos de transporte urbano*. Chile.
9. Smith, H. R., Hemily, B. e Ivanovic, M. (2005). *Transit Signal Priority (TSP): A Planning and Implementation Handbook*. ITS America.
10. Transportation Research Board (2022). *Highway Capacity Manual, 7th Edition*. The National Academies Press, Washington, D.C.
11. Webster, F. V. (1958). *Traffic Signal Settings*. Road Research Technical Paper No. 39. Road Research Laboratory, HMSO, Londres.
""")
