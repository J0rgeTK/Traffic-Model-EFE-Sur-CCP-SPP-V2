# Modelo de cruces ferroviarios — Línea 2 Biotren

Aplicación que estima la **espera vehicular en cruces a nivel** con
prioridad semafórica GPS/SCATS (*pre-vaciado N2*) en la Línea 2 del
Biotren. Reemplaza el modelo original en planilla Excel por un motor de
simulación en Python —validado celda a celda contra el Excel— con bases
de datos relacionales separadas y una interfaz Streamlit.

---

## Qué hace

Simula segundo a segundo, para un cruce, dos escenarios:

- **Base** — el plan semafórico actual; cuando baja la barrera del tren
  (Hurry Call) se fuerza rojo y la cola se acumula.
- **Pre-vaciado** — un sistema GPS/ETA anticipa el tren y adelanta el
  verde del movimiento lateral para evacuar la cola antes del cierre.

El modelo de cola es determinístico (cola puntual de Newell): la espera
total es la integral de la cola en el tiempo.

---

## Estructura del repositorio

```
modelo-cruces-l2/
├── app.py                 Página principal Streamlit
├── motor_sim.py           Motor de simulación (validado)
├── datos.py               Capa de acceso a las bases de datos
├── pages/
│   ├── 1_Simulacion.py    Corre el modelo para un cruce
│   ├── 2_Mapa.py          Mapa georreferenciado de los cruces
│   └── 3_Comparacion.py   Compara cruces y modos de cálculo
├── data/
│   ├── schema/*.sql       DDL de las tres bases
│   ├── infraestructura.db Estaciones, cruces, barreras, semáforos
│   ├── demanda.db         Aforos vehiculares y eventos de barrera
│   └── escenarios.db      Configuración y resultados de corridas
├── scripts/
│   └── migrar_xlsx.py     Genera las bases desde los .xlsx originales
├── tests/
│   └── test_validacion.py Verifica que el motor reproduce el Excel
├── fuentes/               (los .xlsx originales — no se versionan)
├── requirements.txt
└── .streamlit/config.toml
```

Las bases `.db` **se versionan** (son datos de solo lectura listos para
usar). Los `.xlsx` originales **no** se versionan (pesan ~45 MB c/u).

---

## Uso local

```bash
pip install -r requirements.txt
streamlit run app.py
```

La app abre en `http://localhost:8501`.

### Regenerar las bases de datos

Solo si cambian los datos fuente. Copie los dos `.xlsx` originales en
`fuentes/` y ejecute:

```bash
python scripts/migrar_xlsx.py
```

### Verificar el motor

```bash
python tests/test_validacion.py
```

---

## Despliegue en Streamlit Community Cloud

1. Suba este repositorio a GitHub (las bases `.db` van incluidas).
2. En [share.streamlit.io](https://share.streamlit.io) conecte la cuenta
   de GitHub, elija el repositorio y el archivo `app.py`.
3. La app queda publicada en una URL `*.streamlit.app` y se actualiza
   sola con cada `git push`.

**Persistencia.** Community Cloud tiene sistema de archivos efímero: las
bases `infraestructura.db` y `demanda.db` funcionan perfecto por ser de
solo lectura, pero lo que la app *escriba* en `escenarios.db` no
persiste entre reinicios. La app está pensada para trabajar en memoria y
exportar resultados (CSV). Para persistencia multiusuario, migrar
`escenarios.db` a un servicio externo (p. ej. Turso/libSQL).

---

## Las tres bases de datos

Separadas por ciclo de vida, para que una nueva campaña de aforos o una
reprogramación semafórica no afecte los datos maestros:

| Base | Contenido | Cambia |
|---|---|---|
| `infraestructura.db` | Estaciones, cruces (georreferencia), barreras, programación de fases | Rara vez |
| `demanda.db` | Aforos vehiculares, itinerario, eventos de barrera | Por campaña |
| `escenarios.db` | Configuración y resultados de corridas | Cada análisis |

En la aplicación se unen con `ATTACH`. Las relaciones dentro de cada
archivo son claves foráneas reales; las que cruzan archivos se validan
en la capa de aplicación (`datos.py`).

---

## Notas de validación importantes

El motor fue verificado contra el Excel **columna por columna**: las
columnas de entrada coinciden al 100 %. Durante esa verificación se
detectaron errores en el modelo Excel que esta versión corrige:

- **Ventana inconsistente.** El Excel sumaba la espera *base* sobre 15 h
  y la *pre-vaciado* sobre solo 3 h, inflando la reducción reportada
  (87–98 %). El modo `corrected` usa la misma ventana para ambos; la
  reducción real ronda 20–32 % en los cruces no saturados. El modo
  `faithful` reproduce el comportamiento del Excel (con su error) a
  efectos de auditoría.
- **`k_dem` desconectado.** En el Excel el factor 1,1 estaba incrustado
  en los datos y el parámetro del panel no tenía efecto. Aquí
  `flujo_veh_h` se guarda crudo y `k_dem` es un parámetro real.
- **Cruces saturados.** En cruces cerca de la saturación (p. ej.
  Diagonal Bio Bío) la cola determinística diverge y el resultado no es
  representativo. La app lo advierte cuando la cola final es alta.

El detalle completo está en el informe de verificación del motor.
