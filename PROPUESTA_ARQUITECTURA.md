# Arquitectura del modelo

Este documento describe el diseño del modelo de evaluación de la
semaforización de cruces ferroviarios del Servicio Biotrén Línea 2: la
separación de responsabilidades, el modelo de datos y la organización del
código.

---

## 1. Principios de diseño

- **Separación de datos y lógica.** Los datos del corredor residen en
  bases de datos relacionales; la lógica de cálculo, en un paquete de
  módulos independientes. Ningún cálculo depende de la posición física de
  un dato en un archivo: todo se consulta por esquema.
- **Trazabilidad.** Cada dato tiene una fuente y una ubicación definidas, y
  cada resultado es reconstruible a partir de su método de cálculo y sus
  entradas.
- **Coherencia entre casos.** La evaluación de un cruce se realiza en un
  único punto del código, de modo que la simulación individual y la
  cartera arrojan resultados idénticos para el mismo cruce.
- **Validación.** Reglas de integridad sobre las bases y pruebas de
  consistencia del motor protegen contra datos inconsistentes y
  regresiones.

---

## 2. Modelo de datos

Tres bases SQLite separadas por dominio, unidas en tiempo de ejecución
mediante `ATTACH`:

| Base | Dominio | Contenido principal |
|---|---|---|
| `infraestructura.db` | Infraestructura | Cruces y su antecedente, programaciones semafóricas (planes, fases, ciclos), parámetros de barrera, estaciones. |
| `demanda.db` | Demanda y operación | Flujos vehiculares por banda, líneas de buses, eventos de barrera (HCALL), itinerario vigente de la Línea 2. |
| `escenarios.db` | Escenarios | Definición de escenarios y resultados persistidos. |

El esquema de cada base y sus datos de inicialización se encuentran en
`data/schema/` y `data/seeds/`. Las plantillas CSV de `plantillas/`
permiten preparar y validar datos antes de cargarlos, con convenciones
explícitas (tiempos en segundos enteros del día, identificadores estables).

---

## 3. Organización del código

El paquete `modelo_cruces` agrupa la lógica por responsabilidad:

| Módulo | Responsabilidad |
|---|---|
| `motor.py` | Simulación de colas segundo a segundo (capacidad, cola, HCALL, pre-vaciado). |
| `modelos.py` | Estructuras de datos del dominio (entradas y resultados de simulación). |
| `catalogo.py` | Catálogo de cruces y sus variantes (base, reconfiguración). |
| `saturacion.py` | Corrección de demora del HCM (Webster `d₁`, Akçelik `d₂`) y régimen por banda. |
| `microsim.py` | Microsimulación de eventos discretos para régimen de sobre-saturación. |
| `proyecto_incremental.py` | Marco incremental: situación actual, base optimizada, con proyecto. |
| `beneficios.py` | Valoración social del tiempo (VST, ocupación, ponderadores). |
| `composicion.py` | Ocupación efectiva por cruce a partir de la composición de buses. |
| `externalidades.py` | Externalidades: combustible, emisiones, seguridad. |
| `horizonte.py` | Flujo temporal e indicadores (VAN, TIR, B/C). |
| `cartera.py` | Consolidación de la cartera y conversión a UF. |
| `tipologia.py` | Clasificación de cruces y criterio de evaluación. |
| `extrapolacion.py` | Estimación de cruces evaluables sin programación registrada. |
| `movimiento_principal.py` | Análisis del eje Ruta 160. |
| `sensibilidad.py`, `incertidumbre.py` | Sensibilidad (tornado) e incertidumbre (Monte Carlo, Sobol). |
| `alternativas.py`, `desglose_modal.py`, `riesgos.py` | Comparación de alternativas, valor del tiempo por modo y matriz de riesgos. |
| `validadores.py`, `importador.py`, `config.py` | Integridad de las bases, carga de datos y parámetros globales. |

`datos.py`, en la raíz, concentra el acceso a las bases y la función
`evaluar_cruce_corregido`, punto único de evaluación de un cruce que
aplica la corrección de saturación con el número de pistas real y devuelve
las esperas de las tres situaciones y los ahorros de reconfiguración y de
GPS. La interfaz Streamlit (`app.py` y `pages/`) consume esta capa.

---

## 4. Regla de coherencia

El motor segundo a segundo captura la dinámica fina (recuperación tras el
cierre de barrera, pre-vaciado). La corrección del HCM acota la
sobreestimación del modelo determinístico en sobre-saturación. La regla de
coherencia que une ambos:

- El beneficio de la **reconfiguración** es la diferencia de esperas
  corregidas por el HCM entre la situación actual y la base.
- El beneficio del **pre-vaciado** se obtiene de la simulación y se acota
  por el factor de saturación del cruce, porque es un efecto transitorio
  que la formulación estacionaria no representa.
- El **número de pistas del movimiento de estudio** se toma del
  antecedente de cada cruce, no de un valor uniforme.

Al residir esta regla en una única función, la simulación individual y la
cartera son consistentes por construcción.

---

## 5. Pruebas

- `test_validacion.py` — consistencia del motor: verifica que la demanda
  procesada y los resultados del cruce se mantengan dentro de tolerancia
  para los cruces de control.
- `test_validadores.py` — integridad de las bases: comprueba las reglas de
  consistencia del modelo de datos.
- `test_catalogo.py` — construcción correcta del catálogo de cruces.
