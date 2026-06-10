# Plantilla canónica de insumos

CSV planos, con encabezados semánticos, **independientes de la estructura
de las bases**. No usan celdas fijas ni fórmulas y se pueden validar antes de
cargar a SQLite.

Se generan/actualizan con:

```bash
python scripts/exportar_plantillas.py
```

## Reglas generales

- Tiempos en **segundos enteros del día** (`06:00` = `21600`), no en formato de hora del reloj.
- Flujos vehiculares **crudos**, sin el factor `k_dem` (el motor lo aplica).
- Relaciones por **id explícito** (o nombre), nunca por posición de fila.
- Una fila = un hecho: una fase, una banda de aforo, un evento HCALL.

## Archivos y columnas

| Archivo | Columnas |
|---|---|
| `cruces.csv` | `cruce_id, nombre, comuna, latitud, longitud, num_pistas_total, tiene_semaforo, sentido_afectacion` |
| `cruces_reconfiguracion.csv` | `cruce_id, via_principal, codigo_proyecto, comuna_referencia, fuente` — declaración operacional del alcance del proyecto (8 cruces); se carga desde `data/seeds/cruces_reconfiguracion.csv` |
| `programaciones.csv` | `version_prog_id, nombre, fecha, descripcion` |
| `planes_horarios.csv` | `version_prog_id, plan_id, hora_inicio_s, hora_fin_s` |
| `fases.csv` | `version_prog_id, cruce_id, plan_id, fase_id, duracion_s, entreverde_s, cum_inicio_s, cum_fin_s, es_verde_lateral, ciclo_s` |
| `flujos.csv` | `campania_id, cruce_id, t_inicio_s, t_fin_s, flujo_veh_h` |
| `eventos_hcall.csv` | `itinerario_id, cruce_id, sentido, instante_paso_s, hcall_in_s, hcall_out_s` |
| `escenarios.csv` | `escenario_id, nombre, cruce_id, version_prog_id, campania_id, itinerario_id, k_dem, modo` |

## Invariantes que se validan

- `cum_inicio_s < cum_fin_s <= ciclo_s`
- `hcall_in_s <= hcall_out_s`
- planes de una versión sin solape horario
- cada plan con fases; cada cruce simulable con programación, flujo y HCALL
- `flujo_veh_h >= 0` y en rango plausible (crudo)
