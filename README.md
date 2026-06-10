# Modelo de evaluación — Semaforización de cruces ferroviarios, Servicio Biotrén Línea 2

Programa de evaluación técnico-económica del proyecto de integración
**GPS–SCATS** al control semafórico de los cruces a nivel del Servicio
Biotrén, Línea 2, en el Gran Concepción (San Pedro de la Paz y Coronel,
Región del Biobío). El programa simula la operación de cada cruce segundo a
segundo, corrige los resultados con la formulación de saturación del
*Highway Capacity Manual*, valoriza el ahorro de tiempo con los precios
sociales del Sistema Nacional de Inversiones (SNI) y entrega los
indicadores de rentabilidad social de la cartera.

Está construido en Python con una interfaz **Streamlit** de seis secciones
y tres bases de datos relacionales. Es un modelo autocontenido: los datos
de infraestructura, demanda y operación ferroviaria residen en las bases,
y la lógica de cálculo en el paquete `modelo_cruces`.

---

## 1. Problema y enfoque

Cada cruce a nivel es un punto donde un movimiento vial lateral, que cruza
la vía férrea, comparte el derecho de paso con la Ruta 160 bajo control
semafórico. El paso del tren obliga a cerrar la barrera (rutina de
seguridad *Hurry Call*, HCALL), interrumpiendo el flujo. El proyecto
integra la posición del tren (GPS) al controlador SCATS para anticipar el
cierre y **pre-vaciar** la cola lateral antes de que baje la barrera.

La evaluación sigue el principio incremental del SNI y distingue tres
situaciones:

| Situación | Descripción |
|---|---|
| **Actual** | Operación vigente, sin intervención. |
| **Base optimizada** (sin proyecto) | Reconfiguración semafórica: verde inmediato al movimiento lateral tras el HCALL. |
| **Con proyecto** | Base optimizada + integración GPS–SCATS con pre-vaciado predictivo. |

El beneficio atribuible al proyecto es el **incremento de la situación con
proyecto sobre la base optimizada**, no sobre la situación actual.
Atribuirle el beneficio de la reconfiguración —que pertenece a la base—
sobreestimaría su rentabilidad.

---

## 2. Metodología de cálculo

El cálculo encadena cuatro métodos. La sección 4 de la aplicación los
documenta con sus ecuaciones; aquí se resumen.

### 2.1 Simulación de colas segundo a segundo
Modelo determinístico de colas en tiempo discreto (pasos de 1 s) basado en
las curvas acumulativas de llegadas y salidas. La capacidad instantánea es
`c(t) = g(t)·N/h` (verde efectivo × pistas / headway de saturación) y la
cola evoluciona según `Q(t) = máx{0, Q(t−1) + q(t) − d(t)}`. La
integración de la cola da el tiempo total de detención. La rutina HCALL, la
reconfiguración y el pre-vaciado se representan en la dinámica
segundo a segundo.

### 2.2 Corrección por saturación (HCM)
Cerca y por encima de la capacidad, la demora deja de ser proporcional al
flujo. Por banda horaria se aplica la formulación del HCM: retardo
uniforme de Webster (`d₁`) y retardo incremental de Akçelik (`d₂`). El
grado de saturación `X = q/c` gobierna el régimen (estable, saturación
próxima, sobre-saturación) y el método aplicable. Esta corrección acota la
sobreestimación del modelo determinístico en sobre-saturación.

### 2.3 Criterio de coherencia entre situaciones
El beneficio de la **reconfiguración** se calcula como diferencia de
esperas corregidas por el HCM entre la situación actual y la base, lo que
distingue ambas por la capacidad efectiva resultante de la recuperación
tras el cierre de barrera. El beneficio del **pre-vaciado** (GPS) es un
efecto transitorio que la formulación estacionaria no representa: se toma
de la simulación segundo a segundo y se acota por el factor de saturación
del cruce. El número de pistas del movimiento de estudio se toma del
antecedente de cada cruce. Esta lógica está centralizada en
`datos.evaluar_cruce_corregido`, que usan por igual la simulación y la
cartera, garantizando coherencia entre casos.

### 2.4 Valoración social y evaluación económica
El ahorro diario de detención se anualiza y se monetiza:
`B = ΔW · D · O · VST · fₑ`, con `O` la ocupación media (que incorpora la
composición de buses, 20 pax/bus) y `fₑ` el ponderador del tiempo de
espera. Los beneficios se proyectan con el crecimiento de la demanda y se
descuentan a la tasa social para obtener **VAN, TIR y B/C**, con
reinversión de equipos e valor residual al cierre del horizonte.

---

## 3. El modelo de datos

Tres bases SQLite separadas por dominio, unidas en tiempo de ejecución
mediante `ATTACH`:

- **`infraestructura.db`** — cruces y su antecedente (pistas totales y del
  movimiento de estudio, presencia de semáforo, vía principal, evaluación,
  coordenadas, distancia sobre la traza), programaciones semafóricas
  (planes, fases, ciclos, verde lateral), parámetros de barrera y
  estaciones de la línea.
- **`demanda.db`** — flujos vehiculares por cruce y banda horaria
  (campaña de aforo vigente), líneas de buses por cruce y hora, eventos de
  barrera (HCALL por pasada) e itinerario vigente de la Línea 2
  (servicios y horarios con distancia por estación).
- **`escenarios.db`** — definición de escenarios y resultados persistidos.

---

## 4. Estructura del código

```
modelo-cruces-l2/
├── app.py                      Portada de la aplicación
├── datos.py                    Acceso a datos y evaluación coherente por cruce
├── requirements.txt            Dependencias
├── pages/                      Interfaz Streamlit (6 secciones)
│   ├── 1_Cruces_estudiados.py        Antecedente, selección y justificación
│   ├── 2_Supuestos_y_consideraciones.py  Parámetros y supuestos de cálculo
│   ├── 3_Base_de_datos.py            Datos, diagrama de Marey, buses
│   ├── 4_Metodologias.py            Metodología con ecuaciones y referencias
│   ├── 5_Simulacion.py              Simulación de un cruce (3 situaciones)
│   └── 6_Cartera_y_evaluacion.py    Cartera, fases e indicadores económicos
├── modelo_cruces/              Paquete de lógica de cálculo
│   ├── motor.py                Simulación de colas segundo a segundo
│   ├── modelos.py              Estructuras de datos del dominio
│   ├── catalogo.py             Catálogo de cruces y variantes
│   ├── saturacion.py           Corrección Webster/Akçelik (HCM)
│   ├── microsim.py             Microsimulación de eventos (sobre-saturación)
│   ├── proyecto_incremental.py Marco incremental (actual/base/proyecto)
│   ├── beneficios.py           Valoración social del tiempo
│   ├── composicion.py          Ocupación efectiva con buses
│   ├── externalidades.py       Combustible, emisiones, seguridad
│   ├── horizonte.py            VAN/TIR y flujo temporal
│   ├── cartera.py              Evaluación de la cartera (UF, indicadores)
│   ├── tipologia.py            Clasificación de cruces por tipología
│   ├── extrapolacion.py        Estimación de cruces sin programación
│   ├── movimiento_principal.py Análisis del eje Ruta 160
│   ├── sensibilidad.py         Análisis de sensibilidad (tornado)
│   ├── incertidumbre.py        Monte Carlo y Sobol (carga diferida)
│   ├── alternativas.py         Comparación de alternativas
│   ├── desglose_modal.py       Valor del tiempo por modo
│   ├── riesgos.py              Matriz de riesgos
│   ├── validadores.py          Reglas de integridad de las bases
│   ├── importador.py           Carga de datos a las bases
│   └── config.py               Parámetros globales
├── data/                       Bases SQLite, esquemas y semillas
│   ├── infraestructura.db, demanda.db, escenarios.db
│   ├── schema/                 Definiciones de esquema
│   └── seeds/                  Datos de inicialización
├── tests/                      Pruebas de validación e integridad
├── plantillas/                 Plantillas CSV para carga de datos
└── scripts/                    Utilidades de mantenimiento de datos
```

### Componente central
`datos.evaluar_cruce_corregido(con, nombre, campania_id, n_carriles=None)`
es el punto único de evaluación de un cruce. Simula las variantes base y
reconfiguración, aplica la corrección de saturación con el número de pistas
real y devuelve las esperas de las tres situaciones y los ahorros de
reconfiguración y de GPS. Tanto la sección de Simulación como la de Cartera
lo invocan, de modo que un mismo cruce arroja idénticos resultados en
ambas.

---

## 5. Resultados esperados

Por cruce, el programa entrega la espera en las tres situaciones, el grado
de saturación, el régimen y método aplicable, y los ahorros de
reconfiguración y de GPS, valorizados. A nivel de cartera, descompone el
impacto en las tres fases (reconfiguración → GPS), lo agrega por zona
(San Pedro de la Paz / Coronel) y reporta VAN, TIR, B/C y período de
recuperación, con cortes de beneficio en el tiempo.

La reconfiguración concentra la mayor parte del beneficio total de la
iniciativa, y el incremental del GPS —el atribuible al proyecto— constituye
una fracción menor pero suficiente para sustentar la rentabilidad social.
El beneficio se distribuye principalmente en los cruces de mayor
saturación del corredor, que son los cuellos de botella donde la
priorización rinde más.

---

## 6. Documentos del proyecto

Junto al programa se elaboran los documentos formales de respaldo para la
presentación al SNI y al Comité Técnico:

- **Capítulo de Metodología** — formulación, métodos de cálculo y
  referencias bibliográficas.
- **Selección de cruces** — criterio y justificación técnica de los cruces
  evaluados y excluidos.
- **Metodología de cartera y tipología** — tratamiento diferenciado por
  tipo de cruce y consolidación de la cartera.
- **Reformulación del proyecto GPS–SCATS** — ejes de beneficio y
  escalabilidad.
- **Evaluación de cartera y viabilidad** — indicadores y análisis de
  resultados.
- **Análisis crítico del estado general** — vacíos y puntos a desarrollar.
- **Propuesta de arquitectura** (`PROPUESTA_ARQUITECTURA.md`) — diseño del
  modelo de datos y del código.

---

## 7. Ejecución

```bash
pip install -r requirements.txt
streamlit run app.py
```

Requiere Python 3.11+. Las dependencias son `streamlit`, `numpy`,
`pandas`, `openpyxl`, `pydeck` y `altair`. Las pruebas se ejecutan con
`python tests/test_validacion.py` (consistencia del motor) y
`python tests/test_validadores.py` (integridad de las bases).

---

## 8. Marco normativo y referencias

La evaluación se rige por la metodología de **Vialidad Urbana e
Intermedia** del SNI y los precios sociales del Ministerio de Desarrollo
Social y Familia. La formulación de demora se apoya en el *Highway Capacity
Manual* (TRB), Webster (1958) y Akçelik (1981, 1988); la priorización
semafórica, en la documentación del SCATS Priority Engine de Transport for
NSW. El detalle bibliográfico se encuentra en la sección de Metodología de
la aplicación y en el Capítulo de Metodología.
