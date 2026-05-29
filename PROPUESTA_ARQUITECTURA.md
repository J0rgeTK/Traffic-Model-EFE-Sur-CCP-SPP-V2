# Propuesta de arquitectura — modelo de cruces ferroviarios L2

Documento técnico que responde al rediseño solicitado. Marca con
**[implementado]** lo que ya está en el repositorio en esta iteración y con
**[propuesto]** lo que queda como etapa siguiente con su diseño definido.

---

## 1. Diagnóstico de la arquitectura actual

La versión previa funcionaba y reproducía el Excel, pero arrastraba
acoplamientos al origen:

- **Separación de capas** razonable pero incompleta: interfaz (`app.py`,
  `pages/`), acceso a datos (`datos.py`), motor (`motor_sim.py`),
  migración (`scripts/migrar_xlsx.py`) y pruebas (`tests/`) estaban
  separados, pero la lógica de dominio vivía en módulos planos sin
  paquete ni modelos tipados.
- **Dependencias rígidas del Excel.** El importador hardcodeaba las filas
  HCALL por cruce (`HCALL_ROWS = {'Conavicop': (15, 41), ...}`) y los
  nombres de hoja. Cualquier reordenamiento del libro rompía la carga, y
  solo se cargaban 7 de los 22 cruces.
- **«Escenario» como interruptor global.** La simulación elegía una
  *versión de programación* global, sin declarar qué modelo corresponde a
  cada cruce. No quedaba explícito que solo un cruce (Diagonal Bio Bío)
  tiene reconfiguración y el resto solo base.
- **Trazabilidad limitada.** El factor `k_dem` venía incrustado, los
  flujos no distinguían movimiento ni tipo de día, y no había validadores
  formales de integridad.

---

## 2. Arquitectura de código objetivo

**[implementado]** Se introdujo el paquete `modelo_cruces/` con
responsabilidades separadas:

| Módulo | Responsabilidad |
|---|---|
| `motor.py` | Simulación segundo a segundo (validado; movido desde `motor_sim.py`, que ahora es un *shim* de compatibilidad). |
| `modelos.py` | Dataclasses del dominio: `Variante`, `CatalogoCruce`, e insumos canónicos (`FaseCanonica`, `FlujoCanonico`, `EventoBarreraCanonico`). |
| `config.py` | Único punto de acoplamiento al Excel: nombres de hoja, columnas y **marcas de texto** para detectar bloques HCALL. Sin filas hardcodeadas. |
| `catalogo.py` | Variantes por cruce (ver §0 más abajo). |
| `validadores.py` | Reglas de integridad. |
| `importador.py` | Importadores modulares (Excel original de-hardcodeado). |

`datos.py` se mantiene como capa de acceso a la BD para la app y ahora
consume el paquete. Los nombres heredados de columnas Excel quedaron
encapsulados en `config.py`; el resto del código usa nombres semánticos.

**Sobre `src/modelo_cruces/`.** El pedido sugería *layout* `src/`. Para una
app desplegada en Streamlit Community Cloud, que ejecuta desde la raíz del
repo e instala solo `requirements.txt` (sin `pip install -e .`), un paquete
de nivel superior `modelo_cruces/` es directamente importable y evita
fricción de empaquetado. **Recomendación:** mantener `modelo_cruces/` en la
raíz mientras el entregable principal sea la app; migrar a `src/` solo si en
el futuro se distribuye como librería instalable.

---

## 0. Catálogo de variantes por cruce (pedido adicional) **[implementado]**

El escenario deja de ser un interruptor global; **cada cruce declara qué
modelo le corresponde**. El catálogo combina dos fuentes data-driven (sin
listas hardcodeadas):

1. **Detección por datos** — qué cruce tiene programación base (fases v1).
2. **Declaración operacional** — tabla `cruces_reconfiguracion` poblada
   desde `data/seeds/cruces_reconfiguracion.csv`, con la vía principal y
   código SCATS de los cruces del proyecto.

### Significado físico de la reconfiguración

Al **terminar el HCALL** (la barrera vuelve a operación normal), el
controlador puede:

- **Base / operación actual**: saltar a la **fase 1** del ciclo (el
  movimiento principal — Ruta 160). El movimiento lateral espera hasta
  que la fase 1 termine.
- **Reconfiguración**: saltar al `cum_inicio` del **verde lateral**
  (la fase que evacua los vehículos acumulados durante el cierre). El
  ciclo continúa desde ahí.

La diferencia se modela con un flag `post_hcall_lateral` en `Inputs`
(default `False`). El motor lo aplica en sus cuatro sitios HCALL-END
(líneas 200–213 y 241–250 del bloque principal; equivalentes en el
método estocástico). Cuando el flag es `True`, el reset usa
`PhasePlan.green_start` (ya disponible en el motor) en vez de 0. Con el
flag en `False` (default) el motor reproduce exactamente el Excel.

### Variantes generadas por el catálogo

- Cruce con fases v1 y **declarado**: dos variantes — *base* (`post_hcall_lateral=False`) y *reconfiguración* (`post_hcall_lateral=True`).
- Cruce con fases v1 **no declarado**: solo *base* (Costa Verde).
- Cruce declarado **sin fases v1**: 0 variantes simulables (Masisa, Escuadrón 2 — aparecen en el catálogo como informativo).

Resultado sobre los 8 cruces declarados:

| Cruce | Código | Modelo | Variantes |
|---|---|---|---:|
| Diagonal Bio Bío | 3031 | base + reconfiguración + pre-vaciado | 2 |
| Los Claveles | 3051 | base + reconfiguración + pre-vaciado | 2 |
| Michaihue | 3011 | base + reconfiguración + pre-vaciado | 2 |
| Masisa | 3161 | declarado, sin programación cargada | 0 |
| Lomas Coloradas | 3181 | base + reconfiguración + pre-vaciado | 2 |
| Portal San Pedro | 3191 | base + reconfiguración + pre-vaciado | 2 |
| Conavicop | 3196 | base + reconfiguración + pre-vaciado | 2 |
| Escuadrón 2 (Coronel) | — | declarado, sin programación cargada | 0 |

### Beneficio del proyecto

`datos.simular_proyecto(cruce)` ejecuta internamente las dos corridas
necesarias y entrega las cuatro situaciones del modelo:

```
actual            → variante base, sin pre-vaciado     (post_hcall = fase 1)
solo_prevaciado   → variante base, con pre-vaciado
solo_reconfig     → variante reconfig, sin pre-vaciado (post_hcall = lateral)
proyecto          → variante reconfig, con pre-vaciado  (proyecto completo)
```

El beneficio del proyecto es `actual − proyecto`, con desglose en
*aporte del pre-vaciado* y *aporte de la reconfiguración*. La página de
*Simulación* lo muestra en un panel dedicado.

---

## 3. Rediseño de base de datos

**Decisión sobre tres bases vs una.** Se recomienda **mantener los tres
archivos** (`infraestructura`, `demanda`, `escenarios`) por ciclo de vida,
porque ya quedan unificados lógicamente en tiempo de consulta vía `ATTACH`
(la app los ve como un solo espacio con prefijos `infra.`, `dem.`). Esto da
separación de mantención sin costo de integración.

**[implementado] ya en el esquema actual:** `flujo_veh_h` crudo;
`eventos_barrera` con `sentido` e `instante_paso_s`; `campanias_medicion`
con `fuente`; programación por versión.

**[propuesto] evolución del esquema** (DDL de referencia):

```sql
-- Programación por cruce, tipo de día y versión
ALTER TABLE planes_horarios ADD COLUMN tipo_dia TEXT DEFAULT 'laboral';
CREATE TABLE planes_horarios_cruce (        -- planes específicos por cruce
    version_prog_id INTEGER, cruce_id INTEGER, tipo_dia TEXT,
    plan_id INTEGER, hora_inicio_s INTEGER, hora_fin_s INTEGER,
    PRIMARY KEY (version_prog_id, cruce_id, tipo_dia, hora_inicio_s));

-- Movimientos y su relación con las fases
CREATE TABLE movimientos_cruce (
    movimiento_id INTEGER PRIMARY KEY, cruce_id INTEGER,
    codigo TEXT, descripcion TEXT, es_lateral INTEGER);
CREATE TABLE fase_movimiento (
    version_prog_id INTEGER, cruce_id INTEGER, plan_id INTEGER,
    fase_id INTEGER, movimiento_id INTEGER, estado TEXT,  -- verde/rojo/ambar
    PRIMARY KEY (version_prog_id, cruce_id, plan_id, fase_id, movimiento_id));

-- Metadata ampliada
ALTER TABLE versiones_programacion ADD COLUMN autor TEXT;
ALTER TABLE versiones_programacion ADD COLUMN estado TEXT;   -- borrador/vigente
ALTER TABLE llegadas_vehiculares ADD COLUMN movimiento_id INTEGER;
ALTER TABLE llegadas_vehiculares ADD COLUMN tipo_dia TEXT DEFAULT 'laboral';
ALTER TABLE llegadas_vehiculares ADD COLUMN fuente TEXT;
ALTER TABLE llegadas_vehiculares ADD COLUMN calidad TEXT;
ALTER TABLE eventos_barrera ADD COLUMN servicio_id INTEGER;
ALTER TABLE eventos_barrera ADD COLUMN metodo TEXT;          -- medido/estimado
ALTER TABLE eventos_barrera ADD COLUMN confianza TEXT;

-- Parámetros y series de resultados
CREATE TABLE escenario_parametros (
    escenario_id INTEGER, clave TEXT, valor TEXT,
    PRIMARY KEY (escenario_id, clave));
CREATE TABLE resultados_series (             -- trayectoria de cola opcional
    escenario_id INTEGER, t_s INTEGER, cola_base REAL, cola_pre REAL,
    PRIMARY KEY (escenario_id, t_s));
```

El motor no requiere `fase_movimiento` para reproducir el Excel (la fase
lateral se marca con `es_verde_lateral`), pero esa tabla habilita modelar
cruces con varios movimientos sin reescribir el motor.

---

## 4. Plantilla canónica de insumos **[implementado, formato]**

`plantillas/` contiene CSV planos con encabezados semánticos, sin celdas
fijas ni fórmulas, validables antes de cargar:

`cruces.csv`, `programaciones.csv`, `planes_horarios.csv`, `fases.csv`,
`flujos.csv`, `eventos_hcall.csv`, `escenarios.csv`.

Se generan con `scripts/exportar_plantillas.py` (sirve de export de
auditoría y de ejemplo de formato real). Reglas clave de la plantilla:

- tiempos en **segundos enteros del día** (no horas-Excel);
- flujos **crudos** (sin `k_dem`);
- claves por nombre o id explícito, nunca por posición;
- una fila = un hecho (una fase, una banda de aforo, un evento HCALL).

---

## 5. Migración / importadores

- **[implementado]** Importador de compatibilidad del Excel original,
  de-hardcodeado: hojas y columnas desde `config.py`; bloques HCALL
  detectados por la etiqueta de texto en la columna A. Ahora carga **los 22
  cruces** (2 403 eventos HCALL) en vez de 7. `scripts/migrar_xlsx.py` es un
  CLI delgado que solo declara las fuentes.
- **[propuesto]** Importador de la plantilla canónica
  (`importador.importar_plantilla(dir_csv)`), que lee los CSV de §4, corre
  los validadores de §6 y recién entonces escribe en SQLite. El diseño ya
  está: mismas tablas, lectura por encabezado.

---

## 6. Validaciones **[implementado]**

`modelo_cruces/validadores.py` ejecuta y agrega hallazgos (error/advertencia):

- `cum_inicio_s < cum_fin_s <= ciclo_s` y duración/ciclo positivos;
- planes horarios de una versión **sin solape**;
- todo plan referido tiene fases;
- `hcall_in <= hcall_out`;
- flujos **crudos** (no negativos; alerta si superan un umbral plausible,
  señal de `k_dem` ya aplicado);
- todo cruce simulable tiene programación, flujo y eventos HCALL;
- escenarios apuntan a cruces existentes.

Estado actual de las bases: **0 errores, 0 advertencias**. La página
*Validación* de la app muestra el reporte.

---

## 7. Pruebas **[implementado]**

- `test_validacion.py` — regresión contra el Excel (modo *faithful*):
  Costa Verde 1371,2 veh y Diagonal Bio Bío 4676,8 veh.
- `test_catalogo.py` — Diagonal Bio Bío debe tener reconfiguración; Costa
  Verde no; toda variante simulable tiene pre-vaciado.
- `test_validadores.py` — las bases pasan todas las reglas de integridad.

**[propuesto]** Ampliar a pruebas unitarias de HCALL, rojo efectivo, cola y
KPIs por separado, y una prueba de carga de una nueva programación desde la
plantilla canónica.

---

## 8. Interfaz Streamlit **[implementado]**

- *Simulación*: selector de cruce → variante según el catálogo (radio solo
  si hay reconfiguración) + campaña + modo; curvas de Newell y cola.
- *Comparación*: recorre pares (cruce · variante); Diagonal Bio Bío aparece
  como base y como reconfiguración. Contrasta también reducción corregida
  vs «Excel».
- *Mapa*: cruces georreferenciados.
- *Validación* **(nueva)**: reporte de integridad + catálogo de variantes.

**[propuesto]** Página de comparación de versiones lado a lado y exportación
de un reporte de validación en PDF/Excel.

---

## 9. Plan de implementación por etapas

| Etapa | Contenido | Estado |
|---|---|---|
| 1 | Paquete `modelo_cruces/`, modelos tipados, motor movido + shim | **hecho** |
| 2 | De-hardcodear el importador Excel (HCALL por etiqueta, 22 cruces) | **hecho** |
| 3 | Catálogo de variantes por cruce + UI reorientada | **hecho** |
| 4 | Validadores + página de validación | **hecho** |
| 5 | Plantilla canónica (formato + export) | **hecho** |
| 6 | Beneficio social anualizado (MDS 2026) + ventana 06–24 | **hecho** |
| 7 | Importador de la plantilla canónica + validación previa a escritura | propuesto |
| 8 | Evolución del esquema (movimientos, tipo_día, metadata, series) | propuesto |
| 9 | Pruebas unitarias finas + carga de nueva programación | propuesto |
| 10 | Comparación de versiones y reporte exportable | propuesto |

## 10. Beneficio social anualizado **[implementado]**

Cuantificación del beneficio del proyecto según la metodología SNI:

```
ahorro_anual_veh·h  = ahorro_diario_veh·h × 250 días laborales
ahorro_anual_pax·h  = ahorro_anual_veh·h × ocupación_veh
beneficio_anual_CLP = ahorro_anual_pax·h × VST_urbano_pax
```

Constantes oficiales (módulo `modelo_cruces.beneficios`):

| Parámetro | Valor 2026 | Fuente |
|---|---:|---|
| VST urbano viaje en vehículo | **3.338 CLP/h-pax** | MDS Precios Sociales 2026, Tabla 2.1 |
| VST urbano espera (TP mayor) | 6.676 CLP/h-pax | MDS Precios Sociales 2026, Tabla 2.1 |
| Tasa social de descuento | 5,5 % | MDS Precios Sociales 2026, Tabla 1.1 |
| Días laborales / año | 250 | Convención SNI |
| Ocupación urbana (default) | 1,5 pax/veh | Configurable (SECTRA/EOD local) |

Las páginas *Simulación* y *Comparación* exponen el panel «Beneficio
social anualizado». Para integrar el horizonte de evaluación completo
basta con descontar los flujos anuales con la tasa social de 5,5 %.

**Ventana horaria por defecto: 06:00 — 24:00** porque los servicios
Biotren se extienden hasta el último viaje del día laboral. El usuario
puede acotarla si quiere comparar con una hora-punta específica.

## Tabla de equivalencias (auditoría Excel → modelo)

| Excel (origen) | Modelo (semántico) |
|---|---|
| `SIM!J` (TIME ITP) | reloj del controlador congelado en HCALL |
| `PROG_FASES` col F / G | `programacion_fases.cum_fin_s` / `cum_inicio_s` |
| `PROG_FASES` col H | `es_verde_lateral` |
| `Llegadas` col D | `llegadas_vehiculares.flujo_veh_h` (crudo) |
| `Llegadas` col E (×1,1) | `flujo_veh_h/3600 × k_dem` en el motor |
| `HCALL` filas IN/OUT por etiqueta | `eventos_barrera.hcall_in_s` / `hcall_out_s` |
| `BBDD` V / W | `parametros_barrera.tiempo_barrera_s` (CW / CC) |
| panel «escenario» global | catálogo de variantes por cruce |

---

### Criterios cumplidos

Compatibilidad con el modelo actual; app no rota; reproducibilidad
*faithful* contra el Excel intacta; nombres semánticos; supuestos
documentados; sin filas/hoja HCALL hardcodeadas; foco en trazabilidad,
validación e incorporación ordenada de nuevas programaciones.
