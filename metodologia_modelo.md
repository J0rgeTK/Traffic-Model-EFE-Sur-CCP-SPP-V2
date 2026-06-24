# Metodología del modelo predictivo de afluencia EFE Sur 2027

## 1. Propósito y alcance del modelo

El modelo estima la afluencia mensual proyectada de pasajeros para los servicios de EFE Sur durante 2027. Su objetivo es apoyar planificación operacional y evaluación de escenarios de oferta por servicio, unidad operacional, mes y tipo de día.

La metodología separa tres componentes:

1. **Modelo temporal mensual:** estima la demanda mensual total por servicio.
2. **Módulos OD por servicio:** distribuyen la demanda mensual ya proyectada por pares origen-destino y tipo de pasajero/tarjeta cuando existen matrices disponibles.
3. **Ingresos y subsidios:** calculan venta de pasajes y subsidios sólo para los servicios con regla tarifaria implementada. Biotren y Tren Araucanía incluyen subsidio normal y estudiante; Laja-Talcahuano sólo calcula venta de pasajes; Llanquihue-Puerto Montt no tiene módulo tarifario implementado en esta etapa.

Los módulos OD no reemplazan la proyección temporal ni generan el total mensual de demanda; sólo distribuyen la afluencia mensual proyectada y calculan ingresos sobre esa distribución.

## 2. Insumos y fuentes de información

Los insumos principales son la afluencia diaria histórica consolidada, parámetros de oferta por servicio, calendario operacional 2027, feriados nacionales, matrices OD históricas procesadas de Biotren, mapeos de estación-línea, participaciones históricas por tipo de tarjeta, tarifas 2026 por tipo de pasajero y distancias entre estaciones. Los CSV procesados versionados permiten ejecutar el modelo sin depender de archivos Excel binarios.

## 3. Modelo temporal mensual de proyección

El cálculo se realiza por unidad operacional `u`, mes `m` y tipo de día `d`, distinguiendo lunes-viernes, sábado y domingo. Cada mes se calcula de manera independiente. El total anual corresponde a la suma de los doce meses, por lo que una modificación de oferta afecta el mes editado y el total anual por agregación.

```text
V0(u,m,d) = S0(u,m,d) × N_op(u,m,d) × (1 - tau(u,m,d))
D0(u,m,d) = V0(u,m,d) × q(u,m,d) × F_nivel(s) × F_est(s,m)
V1(u,m,d) = S1(u,m,d) × N_op(u,m,d) × (1 - tau(u,m,d) - c(u))
D1(u,m,d) = D0(u,m,d) × (V1(u,m,d) / V0(u,m,d)) ^ epsilon(s)
```

Donde `S0` es la oferta base del escenario, `S1` es la oferta editable, `N_op` corresponde a días operacionales efectivos, `tau` es la tasa de supresión histórica, `q` es productividad media, `F_nivel` es el factor de nivel, `F_est` representa estacionalidad mensual, `epsilon` es elasticidad de demanda respecto de oferta y `c` es una contingencia adicional de supresión para análisis de sensibilidad.

La elasticidad es menor que 1 para representar respuesta parcial de demanda ante cambios de oferta.

## 4. Calendario operacional, oferta y feriados

El calendario 2027 se transforma en días operacionales efectivos por servicio, mes y tipo de día. Las reglas implementadas son:

- **Biotren, Tren Araucanía y Llanquihue-Puerto Montt:** feriados nacionales con oferta efectiva cero.
- **Laja-Talcahuano:** feriados nacionales con oferta de fin de semana. Si el feriado cae lunes-viernes, se imputa como día operacional tipo domingo.

Los feriados nacionales utilizados se encuentran en `data/feriados_chile_2027.csv`. El conteo operacional resultante se exporta en `data/calendario_operacional_2027.csv` y `outputs/calendario_operacional_2027.csv`.

## 5. Tratamiento por servicio

### 5.1 Biotren

Biotren se modela separando L1 y L2 en el motor temporal. La oferta se edita por línea, mes y tipo de día. El escenario Biotren distingue entre frecuencia comercial y capacidad efectiva. La Línea 1 considera 47 servicios lunes-viernes durante el año. La Línea 2 mantiene 110 servicios de lunes a viernes durante 2027; desde mayo, tres servicios de punta mañana operan acoplados dentro de esa misma frecuencia. Por ello, estos servicios no se contabilizan como frecuencia adicional, sino como refuerzo de capacidad efectiva.

El escenario Biotren 2027 corresponde a un escenario de gestión operacional-comercial sustentado en la oferta programada, la capacidad efectiva disponible, la integración con buses del transporte público, la recuperación de viajes registrados mediante plan de evasión y la validación mensual de ocupación. La afluencia total proyectada se distribuye posteriormente por línea, tipo de tarjeta y matriz OD para efectos de ingresos y subsidios.

El escenario ajustado considera una validación operacional por ocupación promedio general. La referencia de pasajeros por servicio comercial se calcula con la frecuencia comercial vigente de L1 y L2; la capacidad equivalente por servicios acoplados se reporta sólo como diagnóstico técnico y no aumenta el denominador comercial. El ajuste mensual se distribuye según tendencia histórica, estacionalidad y oferta: enero y febrero se contrastan especialmente con el comportamiento reciente para evitar niveles estivales artificialmente bajos, mientras los demás meses reciben correcciones asociadas a brechas de ocupación. La proyección resultante para Biotren es **13.095.300 pasajeros** y no se recalibra en esta fase para forzar una ocupación promedio anual de 300 pasajeros por servicio comercial.

#### Oferta operacional corregida

La oferta Biotren 2027 distingue entre frecuencia comercial y capacidad efectiva. La Línea 2 mantiene 110 servicios de lunes a viernes durante todo el año. Desde mayo a diciembre, tres servicios de punta mañana operan acoplados dentro de esa frecuencia, por lo que se modelan como capacidad efectiva adicional y no como aumento de frecuencia.

| Periodo | L1 L-V | L1 sábado | L1 domingo | L2 L-V | L2 sábado | L2 domingo | L2 acoplados L-V |
|---|---:|---:|---:|---:|---:|---:|---:|
| Enero-febrero | 47 | 8 | 0 | 110 | 14 | 14 | 0 |
| Marzo-abril | 47 | 8 | 0 | 110 | 53 | 32 | 0 |
| Mayo-diciembre | 47 | 8 | 0 | 110 | 53 | 32 | 3 |

Los servicios acoplados no agregan frecuencia comercial ni aumento directo de demanda, pero aumentan la capacidad efectiva del sistema. Su rol metodológico es actuar como refuerzo de capacidad, alivio de saturación y soporte para absorber viajes en meses u horarios de alta utilización, especialmente en L2 y punta mañana. Por ello, el indicador ejecutivo de ocupación se calcula sobre servicios comerciales, mientras que el indicador de capacidad equivalente se utiliza como diagnóstico técnico.

#### Integración con buses del transporte público

La integración con buses del transporte público se incorpora como una medida de captura y alimentación de demanda. Su efecto principal se concentra en estación Concepción, por su rol de nodo estructurante de la red Biotren y su vinculación con los flujos urbanos de mayor escala. No obstante, desde el punto de vista operacional, la integración puede extenderse al resto de estaciones, generando mejoras de accesibilidad y continuidad de viaje en toda la red.

Dado que en esta etapa no se dispone de una matriz observada de transbordos bus-tren por estación, la integración TP se utiliza como fundamento del escenario de gestión y no como una redistribución OD específica.

#### Plan de evasión

El plan de evasión se incorpora como una medida de recuperación de viajes registrados equivalente a 1% del cierre 2026 de Biotren. Este componente no se interpreta necesariamente como demanda física completamente nueva, sino como mejora en la captura de validaciones, reducción de viajes no registrados y fortalecimiento de la trazabilidad de la demanda efectiva. El efecto del plan de evasión fundamenta el crecimiento del escenario de gestión y no debe sumarse nuevamente si la afluencia anual ya fue calibrada al escenario consolidado.

#### Ocupación mensual y bandas de funcionamiento

El modelo distingue entre ocupación por servicio comercial y ocupación por capacidad equivalente. La primera corresponde al indicador principal de gestión y se calcula dividiendo la afluencia mensual por los servicios comerciales programados. La segunda incorpora el efecto de servicios acoplados como capacidad adicional y se utiliza sólo como diagnóstico técnico.

Las bandas de funcionamiento mensual se calculan sobre `Pax/servicio comercial`: baja utilización bajo 270, operación estable desde 270 y menor a 300, alta utilización entre 300 y 330, y tensión operacional sobre 330. La clasificación mensual por bandas permite evaluar si el promedio anual cercano a 300 pasajeros por servicio comercial se distribuye de manera razonable durante el año. Las bandas son diagnósticas, ayudan a identificar meses con baja utilización, operación estable, alta utilización o tensión operacional, y no modifican por sí mismas la demanda proyectada; el resultado vigente no presenta meses en tensión operacional.

#### Distribución posterior

Una vez consolidada la demanda total de Biotren, el modelo distribuye la afluencia por línea, tipo de tarjeta y matriz OD. Sobre esa distribución se estiman ingresos por venta de pasajes, subsidio normal y subsidio estudiante. Estas capas distribuyen e interpretan la demanda ya proyectada, sin recalcular la afluencia total.


El modelo distingue entre ocupación por servicio comercial y ocupación por capacidad equivalente. La primera corresponde al indicador principal de gestión y se calcula dividiendo la afluencia mensual por los servicios comerciales programados. La segunda incorpora el efecto de servicios acoplados como capacidad adicional y se utiliza sólo como diagnóstico técnico. La clasificación mensual por bandas permite identificar meses de baja utilización, operación estable, alta utilización o tensión operacional, sin modificar por sí misma la proyección de demanda.

Las bandas de funcionamiento mensual de Biotren se calculan sobre `Pax/servicio comercial`: baja utilización bajo 270, operación estable desde 270 y menor a 300, alta utilización entre 300 y 330, y tensión operacional sobre 330. Los servicios acoplados L2 de mayo a diciembre no aumentan la frecuencia comercial; sólo elevan los servicios equivalentes de capacidad utilizados para el indicador técnico `Pax/capacidad equivalente`. Esta fase mantiene sin cambios la demanda anual Biotren 2027.

### 5.2 Tren Araucanía

Tren Araucanía se modela por componente de servicio:

- Temuco - Victoria.
- Temuco - Pitrufquén.
- Claret.

El escenario operacional vigente proyecta **840.777 pasajeros** para Tren Araucanía. La oferta Victoria-Temuco considera 11 servicios lunes-viernes durante todo 2027; adicionalmente, se refuerza mayo para mantener coherencia con el bloque marzo-mayo 2026 y se aplica un incremento marginal al resto de los meses para preservar el perfil mensual observado en 2025, especialmente la señal estival.

Cada componente responde a su propia oferta y elasticidad. Temuco-Victoria tiene mayor respuesta marginal esperada que Pitrufquén y Claret. Claret se trata como componente escolar específico y se restringe a marzo-diciembre; enero y febrero no generan oferta ni demanda para este componente. La distribución mensual combina patrón histórico, calendario operacional, oferta mensual y tratamiento escolar. El control de marzo evita concentración artificial mediante suavizamiento técnico cuando la relación frente al promedio abril-diciembre supera el umbral definido.

Tren Araucanía utiliza su propia MOD y reglas tarifarias/subsidio. No utiliza MOD Biotren, categorías L1/L2/L1-L2, distribución OD Biotren ni tipo de tarjeta Biotren.

### 5.3 Llanquihue-Puerto Montt

Llanquihue-Puerto Montt se modela con operación de lunes a viernes. En el escenario base no se consideran servicios planificados de fin de semana ni operación en feriados nacionales.

El escenario operacional vigente proyecta **412.132 pasajeros** para Llanquihue-Puerto Montt. Marzo-diciembre se calibra con un promedio laboral referencial cercano a 1.500 pasajeros por día laboral; el promedio reportado para el bloque es aproximadamente **1.499,85 pasajeros por día laboral**. Esta referencia opera como ancla metodológica y no como restricción rígida idéntica para todos los meses. Enero y febrero consideran una reducción por menor efecto de novedad del servicio.

El servicio mantiene independencia metodológica respecto de módulos OD Biotren, categorías L1/L2/L1-L2, tipo de tarjeta, ingresos Biotren y base referencial de subsidio Biotren.

### 5.4 Laja-Talcahuano / Corto Laja

Laja-Talcahuano se proyecta como servicio propio. La oferta base considera 8 servicios diarios durante el año, con excepción de sábados y domingos de enero y febrero, donde se consideran 10 servicios. Los feriados nacionales se modelan con oferta de fin de semana.

El escenario operacional vigente proyecta **540.842 pasajeros** para Laja-Talcahuano. El servicio no recibe ajuste operacional específico nuevo dentro de la recalibración; su tratamiento sigue asociado a patrón histórico, oferta operacional, calendario y regla de feriados como operación de fin de semana.

Laja-Talcahuano no utiliza MOD Biotren, categorías L1/L2/L1-L2, distribución OD Biotren, tipo de tarjeta Biotren, ingresos Biotren ni base referencial de subsidio Biotren.

## 6. Escenario operacional 2027 vigente

| Servicio | Proyección anual vigente 2027 |
|---|---:|
| Biotren | 13.095.299 |
| Tren Araucanía | 840.777 |
| Llanquihue-Puerto Montt | 412.132 |
| Laja-Talcahuano / Corto Laja | 540.842 |
| **Total sistema** | **14.857.758** |

Estos valores corresponden a la base operacional vigente sobre la cual se ejecutan los módulos OD de Biotren, el backtesting diagnóstico y las bandas de incertidumbre.

## 7. Biotren: distribución por línea OD basada en MOD

La demanda total mensual de Biotren proviene del modelo temporal. La MOD histórica atribuible no genera ese total; sólo distribuye la demanda ya proyectada por línea OD.

Cada par origen-destino se clasifica con el mapeo estación-línea versionado en `data/od_biotren/processed/mapeo_estacion_linea_biotren.csv`. Las categorías estándar proyectadas son:

| Categoría OD | Interpretación |
|---|---|
| `L1` | Origen y destino atribuibles al corredor L1, incluyendo viajes desde/hacia estación común cuando el otro extremo es L1. |
| `L2` | Origen y destino atribuibles al corredor L2, incluyendo viajes desde/hacia estación común cuando el otro extremo es L2. |
| `L1-L2` | Viajes entre corredores o que implican combinación entre líneas. |

Concepción se marca como estación común/intercambio (`L1_L2`). El par `Concepción → Concepción` se mantiene como control `No clasificado`, porque corresponde a diagonal común-común y no debe asignarse artificialmente a L1, L2 ni L1-L2. El `No clasificado` se reporta como control diagnóstico histórico y no recibe proyección estándar.

```text
Participación_linea_m = Viajes_observados_linea_m / (Viajes_L1_m + Viajes_L2_m + Viajes_L1-L2_m)
Proyección_linea_m = Proyección_Biotren_m × Participación_linea_m
```

El supuesto fijo 80/20 no corresponde al criterio metodológico vigente; fue reemplazado por participaciones mensuales calculadas con MOD histórica atribuible. La suma mensual `L1 + L2 + L1-L2` conserva el total mensual de Biotren, salvo diferencias numéricas de redondeo.

## 8. Biotren: distribución OD por tipo de tarjeta

El módulo OD por tipo de tarjeta distribuye el total mensual vigente de Biotren entre tipos de tarjeta y pares origen-destino. La suma de todos los tipos de tarjeta conserva la demanda mensual total de Biotren.

| Tipo de tarjeta | Regla de ingreso tarifario preliminar |
|---|---|
| `monedero` | Usa tarifa normal/adulto. |
| `media_superior` | Usa tarifa estudiante. |
| `adulto_mayor` | Usa tarifa adulto mayor. |
| `estudiante_basica` | Tarifa 0. |
| `discapacitado` | Tarifa 0. |
| `funcionario_normal` | Tarifa 0. |
| `funcionario_especial` | Tarifa 0. |
| `convenio_colectivo` | Tarifa 0. |

Los tipos con tarifa 0 conservan viajes proyectados en la distribución de afluencia, pero no generan ingreso tarifario directo.

## 9. Ingresos por venta de pasajes

Los ingresos por venta de pasajes se calculan en memoria multiplicando la matriz de viajes por la tarifa directa aplicable a cada tipo de tarjeta:

```text
Ingreso_ij,t,m = Viajes_ij,t,m × Tarifa_ij,t
```

Los ingresos por venta de pasajes aplican sólo donde existe tarifa directa: `monedero`, `media_superior` y `adulto_mayor`. Los tipos `estudiante_basica`, `discapacitado`, `funcionario_normal`, `funcionario_especial` y `convenio_colectivo` usan tarifa 0. La tarifa estudiante pagada se mantiene para la venta de pasajes de `media_superior` y no se reemplaza por la tarifa estudiante BT sin subsidio.

## 10. Subsidio e ingreso total Biotren

Venta de pasajes y subsidio son conceptos distintos. El cálculo se aplica sobre la proyección OD por tipo de tarjeta vigente de Biotren y no modifica la afluencia proyectada.

### 10.1 Subsidio normal

El grupo normal incluye todas las tarjetas excepto `media_superior` y `adulto_mayor`: `monedero`, `estudiante_basica`, `discapacitado`, `funcionario_normal`, `funcionario_especial` y `convenio_colectivo`.

Monto_normal_base = Σ(MOD_normal_base_ij × tarifa_normal_ij), con diagonal en cero.

Subsidio_normal = Monto_normal_base / (1 - tasa_descuento) - Monto_normal_base

La tasa de descuento queda parametrizada en `data/tarifas_biotren/parametros_subsidio_biotren.csv` como `tasa_descuento_normal = 0,189`.

### 10.2 Subsidio estudiante

El grupo estudiante incluye sólo `media_superior`.

Subsidio_estudiante = Ingreso_teorico_estudiante_sin_subsidio_sin_diagonal - Venta_media_superior_con_diagonal.

Donde `Ingreso_teorico_estudiante_sin_subsidio_sin_diagonal = Σ_{i≠j}(MOD_media_superior_ij × tarifa_estudiante_BT_sin_subsidio_ij)` y `Venta_media_superior_con_diagonal = Σ_{todos i,j}(MOD_media_superior_ij × tarifa_estudiante_pagada_ij)`. La matriz estudiante sin subsidio proviene del presupuesto base `Presupuesto 2026 Biotren v4.xlsx`, hoja `Tarifa Escolar Feb-sep`, bloque `Estudiante Sin subsidio 2026`, normalizada en `data/tarifas_biotren/tarifa_estudiante_bt_sin_subsidio_long.csv`. No debe usarse como fórmula final la brecha OD `max(0, tarifa_sin_subsidio - tarifa_pagada)` por par OD. No se imputan automáticamente tarifas faltantes, las brechas de cobertura se reportan como advertencias y el cálculo no modifica la afluencia proyectada.

### 10.3 Total

Subsidio_total = Subsidio_normal + Subsidio_estudiante

Ingreso_total_Biotren = Ingreso_venta + Subsidio_normal + Subsidio_estudiante

`adulto_mayor` queda fuera de los grupos de subsidio indicados.

## 10A. Subsidio e ingreso total Tren Araucanía

La distribución OD de Tren Araucanía conserva la afluencia mensual proyectada y la reparte por tipo de pasajero y par OD según la MOD base. La venta de pasajes y la base de subsidio son conceptos distintos.

### 10A.1 Venta de pasajes

- `normal`: paga 100% de tarifa normal.
- `delegacion`: paga 70% de tarifa normal.
- `adulto_mayor`: paga tarifa adulto mayor.
- `estudiante` y `claret`: pagan tarifa estudiante.
- `discapacitado`, `estudiante_basica`, `funcionario` y `sindicato`: no generan venta directa.

### 10A.2 Subsidio normal

El grupo normal para subsidio incluye `normal`, `discapacitado`, `funcionario`, `sindicato` y `delegacion`. La base se calcula con tarifa normal completa, por lo que puede ser mayor que la venta normal directa.

Subsidio_normal = Monto_normal_base / (1 - 0,127) - Monto_normal_base

### 10A.3 Subsidio estudiante

El grupo estudiante para subsidio incluye `estudiante`, `claret` y `estudiante_basica`. El subsidio se calcula con la diferencia entre la matriz estudiante sin subsidio y la matriz estudiante con subsidio. Esta base es independiente de la venta directa; por lo tanto, `estudiante_basica` puede no generar venta de pasajes, pero sí participa en la base de subsidio estudiantil.

Subsidio_estudiante = Base_estudiante_sin_subsidio - Base_estudiante_con_subsidio

`adulto_mayor` no integra subsidio normal ni estudiante.

## 11. Backtesting histórico diagnóstico

El modelo incluye un módulo de backtesting histórico para contrastar periodos observados conocidos contra estimaciones producidas por el mismo motor mensual-elástico utilizado en el escenario vigente. El backtesting es retrospectivo diagnóstico no holdout: audita consistencia, escala y perfil mensual, pero no reemplaza ni recalibra la proyección operacional 2027.

El backtesting entrega métricas por servicio y para el total sistema: MAE, RMSE, MAPE, WMAPE y sesgo. WMAPE es la referencia agregada principal porque pondera por volumen observado.

## 12. Bandas de incertidumbre diagnósticas

Las bandas de incertidumbre derivan de métricas históricas de error del backtesting, especialmente WMAPE. No son intervalos estadísticos formales ni intervalos de confianza. El ajuste por sesgo es una sensibilidad diagnóstica.

Las bandas se calculan sobre la proyección base 2027 vigente:

| Servicio | Base 2027 usada por incertidumbre |
|---|---:|
| Biotren | 13.095.299 |
| Tren Araucanía | 840.777 |
| Llanquihue-Puerto Montt | 412.132 |
| Laja-Talcahuano | 540.842 |

## 13. Validaciones, limitaciones y próximos pasos

El modelo genera controles de consistencia mensual/anual, feriados por servicio, sensibilidad de oferta, conservación de totales OD de Biotren, suma de participaciones MOD por línea, consistencia por tipo de tarjeta, ingresos sólo para tipos con tarifa aplicable, subsidio normal y estudiante con controles de cobertura, backtesting diagnóstico y bandas de incertidumbre sin valores negativos.

- el backtesting es diagnóstico y no modifica resultados del escenario 2027;
- la comparación se limita a meses con observación histórica disponible;
- meses incompletos no se descartan automáticamente: se reporta cobertura para su interpretación;
- servicios con baja afluencia pueden mostrar MAPE elevado por denominadores pequeños;
- meses con observado cero no entran al MAPE y se contabilizan explícitamente;
- WMAPE es la referencia agregada principal para comparar desempeño por servicio y sistema;
- las estimaciones usan la lógica vigente del motor mensual-elástico y pueden incorporar parámetros calibrados con información posterior al periodo evaluado;
- los feriados parametrizados explícitamente corresponden al horizonte operacional 2027, por lo que la lectura histórica debe interpretarse como prueba de consistencia mensual y no como reconstrucción operacional diaria completa;
- el proceso se ejecuta en memoria, sin generar archivos binarios, sin modificar outputs masivos y sin tocar `data/od_biotren/processed/`.

## Recalibración operacional del escenario 2027

La proyección 2027 se presenta como escenario recalibrado a partir de nuevos supuestos operacionales. La recalibración se aplica después del motor mensual-elástico y antes de las distribuciones OD, ingresos por venta de pasajes y bandas de incertidumbre, manteniendo separadas la proyección base, el backtesting histórico y el módulo de incertidumbre.

### Biotren

Biotren incorpora una validación operacional por ocupación promedio general. Primero se calcula una trayectoria mensual con oferta vigente, calendario operacional, estacionalidad y afectación de Línea 2 en fines de semana de enero y febrero. Luego se evalúan los servicios comerciales mensuales distinguiendo que los acoplados L2 son capacidad efectiva y no frecuencia adicional. Enero y febrero se contrastan con el comportamiento histórico reciente; los demás meses se ajustan según brechas de ocupación y oferta mensual. La distribución por línea MOD, la distribución OD por tipo de tarjeta y los ingresos por venta de pasajes se recalculan desde el total mensual ajustado. La base referencial de subsidio continúa sin cálculo de montos.

### Tren Araucanía

Tren Araucanía mantiene una metodología por tramo: Temuco-Victoria, Temuco-Pitrufquén y Claret. Victoria-Temuco opera con 11 servicios de lunes a viernes durante 2027. Claret conserva su carácter escolar y sólo aporta en marzo-diciembre. El perfil mensual combina patrón histórico, calendario operacional, oferta mensual, componente escolar y suavizamiento de marzo cuando el diagnóstico lo identifica como outlier respecto del promedio abril-diciembre y del promedio anual.

### Llanquihue-Puerto Montt

Llanquihue-Puerto Montt se calibra con el indicador de pasajeros por día laboral operacional. Para marzo-diciembre se aproxima al entorno de 1.500 pasajeros por día laboral, permitiendo variaciones por estacionalidad y cantidad de días laborales. Enero y febrero reciben factores de reducción por menor efecto novedad y no usan la restricción de 1.500 como regla rígida.

### Laja-Talcahuano

Laja-Talcahuano no recibe ajuste específico nuevo dentro de la recalibración. El servicio mantiene su tratamiento vigente, incluida la operación de feriados con regla de fin de semana cuando corresponde.

### Incertidumbre

Las bandas bajo/base/alto se recalculan sobre la nueva base 2027. El WMAPE y el sesgo provienen del backtesting histórico y no modifican su metodología; el ajuste por sesgo se interpreta como sensibilidad diagnóstica sobre la base recalibrada y se controla que no genere valores negativos.

## Referencias históricas normalizadas y cierre 2026 estimado

Los CSV normalizados de `data/referencias_cierre_2026/` se incorporan como insumo auxiliar de visualización histórica. La lectura separa **Histórico observado**, **Cierre 2026 estimado** y **Proyección 2027 modelo**, evitando interpretar el cierre 2026 como observado definitivo.

Estos archivos no forman parte de la calibración del motor de proyección, no modifican elasticidades, factores operacionales ni resultados del escenario 2027 vigente. Se usan para presentar la trayectoria anual y mensual de Biotren, Laja-Talcahuano y Tren Araucanía, manteniendo la proyección 2027 como resultado del modelo operacional vigente.

### Redistribución mensual Biotren 2027 por participación anual

La proyección anual Biotren se mantiene en 13.095.299 pasajeros. La revisión mensual usa la participación de cada mes sobre el total anual, calculada como afluencia mensual dividida por afluencia anual, y compara el escenario 2027 contra 2024 observado, 2025 observado y cierre 2026 estimado disponible en las referencias versionadas.

La participación objetivo mensual combina el patrón reciente ponderado por cercanía temporal (2024: 25%, 2025: 35%, cierre 2026: 40%) con la participación mensual de los servicios comerciales 2027. Esta combinación conserva la estacionalidad histórica, incorpora la oferta mensual y evita meses artificialmente bajos o altos frente al comportamiento reciente.

La redistribución se aplica sólo al total mensual Biotren. Las capas por línea, OD, tipo de tarjeta, venta de pasajes, subsidio normal, subsidio estudiante, subsidio total e ingreso total Biotren se calculan después de esa afluencia mensual redistribuida, conservando los totales mensuales de entrada.
