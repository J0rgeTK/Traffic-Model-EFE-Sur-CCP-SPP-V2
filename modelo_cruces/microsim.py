"""
Microsimulacion de eventos discretos para validar bandas saturadas
==================================================================
Cuando el grado de saturacion x > 1,20 en una banda, ni Newell
(deterministico segundo-a-segundo) ni Akcelik (formula analitica)
son metodologicamente defendibles. El estandar SNI / SECTRA es
microsimulacion.

Este modulo implementa una microsimulacion ligera de eventos discretos:

  - Llegadas: proceso de Poisson con tasa lambda(t).
  - Servicio: vehiculos abandonan la cola con headway h durante
    verde efectivo; ningun servicio durante rojo (R=1).
  - Espera por vehiculo: tiempo desde su llegada hasta que abandona
    la cola.
  - Replicas: N corridas independientes con distintas semillas.
  - Salida: distribucion completa de la espera (media, P10, P50, P90,
    P95, max), longitud maxima de cola, vehiculos no atendidos.

A diferencia de un motor segundo-a-segundo, aqui cada vehiculo es una
entidad con tiempo propio de llegada y servicio. Esto captura
correctamente la sobre-saturacion (cola que persiste entre eventos),
spillback no fisico (lista crece sin techo, pero al menos visible) y
variabilidad estadistica.

USO TIPICO:
    >>> mc = microsim_banda(
    ...     duracion_s=3600,            # 1 hora
    ...     flujo_h=350,                # V (veh/h)
    ...     patron_verde=lambda t: ...,  # funcion 1=verde, 0=rojo
    ...     headway_s=2.0,
    ...     n_carriles=2,
    ...     n_replicas=200,
    ...     semilla=1)
    >>> mc.espera_media_veh  # s/veh
    >>> mc.espera_p90_veh
    >>> mc.cola_max_p90

NOTA: esta microsimulacion NO reemplaza Vissim/Aimsun/SUMO; es una
herramienta de VALIDACION ANALITICA. Para postulacion final, se
recomienda complementar con SUMO (open-source) en el cruce critico.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass


@dataclass
class ResultadoMicrosim:
    """Distribucion empirica de la espera en una banda saturada."""
    duracion_s:           float
    flujo_h:              float
    n_replicas:           int
    # Espera por vehiculo (s/veh)
    espera_media:         float
    espera_p10:           float
    espera_p50:           float
    espera_p90:           float
    espera_p95:           float
    espera_max:           float
    # Espera total en la banda (veh*h)
    espera_total_vh_media: float
    espera_total_vh_p90:   float
    # Cola
    cola_max_media:       float
    cola_max_p90:         float
    cola_final_media:     float
    # Vehiculos
    n_atendidos_media:    float
    n_no_atendidos_media: float    # cola residual al final
    n_llegados_media:     float
    # Diagnostico
    grado_saturacion_emp: float    # x empirico de la simulacion
    estable:              bool      # True si cola final << demanda

    def resumen(self) -> str:
        return (
            f'Microsim {self.duracion_s/3600:.1f}h, V={self.flujo_h:.0f}v/h, '
            f'n_rep={self.n_replicas}\n'
            f'  Espera (s/veh): media={self.espera_media:.0f}  '
            f'P50={self.espera_p50:.0f}  P90={self.espera_p90:.0f}  '
            f'max={self.espera_max:.0f}\n'
            f'  Cola final media={self.cola_final_media:.0f}, '
            f'P90={self.cola_max_p90:.0f}\n'
            f'  Espera total media={self.espera_total_vh_media:.1f}vh, '
            f'P90={self.espera_total_vh_p90:.1f}vh\n'
            f'  x_empirico={self.grado_saturacion_emp:.2f}, '
            f'estable={self.estable}'
        )


def _correr_replica(duracion_s: int, flujo_h: float, verde_serie: np.ndarray,
                    headway_s: float, n_carriles: float,
                    rng: np.random.Generator) -> dict:
    """Una corrida de eventos discretos.

    `verde_serie` es un vector de longitud duracion_s con 1=verde y 0=rojo
    por segundo (el patron del semaforo agregado en esa banda).
    """
    # Llegadas: proceso de Poisson; intervalos exp con tasa lambda = flujo_h/3600
    lam_s = flujo_h / 3600.0
    if lam_s <= 0:
        return dict(espera_total=0.0, esperas=[], cola_max=0,
                    cola_final=0, atendidos=0, no_atendidos=0, llegados=0)

    # Generar tiempos de llegada
    intervalos = rng.exponential(1.0 / lam_s, int(duracion_s * lam_s * 3) + 50)
    tiempos_llegada = np.cumsum(intervalos)
    tiempos_llegada = tiempos_llegada[tiempos_llegada < duracion_s]
    n_llegados = len(tiempos_llegada)

    # Cola FIFO: lista de tiempos de llegada
    cola = []
    idx_llegada = 0
    esperas = []        # espera de cada vehiculo atendido
    cola_max = 0
    # Capacidad de servicio: n_carriles vehiculos por headway_s en verde
    # Atendemos hasta n_carriles vehiculos por segundo de verde, pero
    # acumulamos un "credito de servicio" para horarios fraccionarios
    credito_servicio = 0.0
    servicio_por_s = n_carriles / headway_s if headway_s > 0 else n_carriles

    for t in range(int(duracion_s)):
        # 1) Llegadas durante [t, t+1)
        while idx_llegada < n_llegados and tiempos_llegada[idx_llegada] < t + 1:
            cola.append(float(tiempos_llegada[idx_llegada]))
            idx_llegada += 1
        # 2) Servicios si esta verde
        if verde_serie[t] == 1:
            credito_servicio += servicio_por_s
            while credito_servicio >= 1.0 and cola:
                t_lleg = cola.pop(0)
                # Servicio promedio dentro del segundo: t + 0.5
                t_serv = t + 0.5
                espera = max(0.0, t_serv - t_lleg)
                esperas.append(espera)
                credito_servicio -= 1.0
        else:
            credito_servicio = 0.0           # se pierde al cambiar de rojo
        # 3) Actualizar cola maxima observada
        cola_max = max(cola_max, len(cola))

    # Al final pueden quedar llegadas no atendidas; contabilizar su
    # espera DENTRO de la banda (desde que llegaron hasta T_fin), que es
    # la fraccion de espera ocurrida en el periodo de analisis.
    # Esto hace la microsim comparable con el motor (integral de Q
    # hasta T_fin) y con Akcelik d2 (retardo total hasta vaciar la cola).
    no_atendidos = len(cola)
    atendidos = len(esperas)
    esperas_residuales = [duracion_s - t_lleg for t_lleg in cola]
    espera_atendidos = float(sum(esperas))
    espera_residuales = float(sum(esperas_residuales))
    espera_total = espera_atendidos + espera_residuales
    return dict(
        espera_total=espera_total, esperas=esperas,
        esperas_residuales=esperas_residuales, cola_max=cola_max,
        cola_final=no_atendidos, atendidos=atendidos,
        no_atendidos=no_atendidos, llegados=n_llegados,
    )


def microsim_banda(duracion_s: int = 3600, flujo_h: float = 350,
                   patron_verde: np.ndarray | None = None,
                   prop_verde: float = 0.30, ciclo_s: int = 142,
                   headway_s: float = 2.0, n_carriles: float = 2.0,
                   n_replicas: int = 100, semilla: int = 1) -> ResultadoMicrosim:
    """Microsimulacion de una banda saturada.

    Si `patron_verde` no se entrega, se genera uno deterministico con
    `prop_verde` de la duracion en verde y ciclo `ciclo_s`.
    """
    if patron_verde is None:
        patron_verde = np.zeros(duracion_s, dtype=np.int8)
        verde_por_ciclo = int(ciclo_s * prop_verde)
        for inicio_ciclo in range(0, duracion_s, ciclo_s):
            fin = min(inicio_ciclo + verde_por_ciclo, duracion_s)
            patron_verde[inicio_ciclo:fin] = 1
    else:
        patron_verde = np.asarray(patron_verde, dtype=np.int8)
        assert len(patron_verde) >= duracion_s, 'patron_verde demasiado corto'

    rng_master = np.random.default_rng(semilla)
    semillas = rng_master.integers(0, 2**31 - 1, n_replicas)

    esperas_media_rep = []
    esperas_p90_rep = []
    espera_total_vh_rep = []
    cola_max_rep = []
    cola_final_rep = []
    atendidos_rep = []
    no_atendidos_rep = []
    llegados_rep = []
    todas_las_esperas = []

    for sem in semillas:
        rng = np.random.default_rng(int(sem))
        out = _correr_replica(duracion_s, flujo_h, patron_verde,
                              headway_s, n_carriles, rng)
        if out['esperas']:
            esperas_media_rep.append(float(np.mean(out['esperas'])))
            esperas_p90_rep.append(float(np.percentile(out['esperas'], 90)))
        else:
            esperas_media_rep.append(0)
            esperas_p90_rep.append(0)
        espera_total_vh_rep.append(out['espera_total'] / 3600.0)
        cola_max_rep.append(out['cola_max'])
        cola_final_rep.append(out['cola_final'])
        atendidos_rep.append(out['atendidos'])
        no_atendidos_rep.append(out['no_atendidos'])
        llegados_rep.append(out['llegados'])
        todas_las_esperas.extend(out['esperas'])

    arr_esperas = np.array(todas_las_esperas) if todas_las_esperas else np.array([0])
    cap_servicio_h = (n_carriles / headway_s) * float(patron_verde.sum()) / duracion_s * 3600
    x_emp = flujo_h / cap_servicio_h if cap_servicio_h > 0 else float('inf')
    cola_final_media = float(np.mean(cola_final_rep))
    estable = cola_final_media < 0.05 * float(np.mean(llegados_rep))

    return ResultadoMicrosim(
        duracion_s=duracion_s, flujo_h=flujo_h, n_replicas=n_replicas,
        espera_media=float(np.mean(esperas_media_rep)),
        espera_p10=float(np.percentile(arr_esperas, 10)),
        espera_p50=float(np.percentile(arr_esperas, 50)),
        espera_p90=float(np.percentile(arr_esperas, 90)),
        espera_p95=float(np.percentile(arr_esperas, 95)),
        espera_max=float(np.max(arr_esperas)) if len(arr_esperas) else 0,
        espera_total_vh_media=float(np.mean(espera_total_vh_rep)),
        espera_total_vh_p90=float(np.percentile(espera_total_vh_rep, 90)),
        cola_max_media=float(np.mean(cola_max_rep)),
        cola_max_p90=float(np.percentile(cola_max_rep, 90)),
        cola_final_media=cola_final_media,
        n_atendidos_media=float(np.mean(atendidos_rep)),
        n_no_atendidos_media=float(np.mean(no_atendidos_rep)),
        n_llegados_media=float(np.mean(llegados_rep)),
        grado_saturacion_emp=x_emp, estable=estable,
    )


def microsim_desde_resultados(resultados, hora_inicio: float, hora_fin: float,
                              flujo_h: float | None = None,
                              n_replicas: int = 100, semilla: int = 1,
                              usar_pre: bool = False) -> ResultadoMicrosim:
    """Corre microsim sobre una banda especifica extraida de las series del motor.

    El patron de verde se toma directamente del motor (con o sin pre-vaciado),
    asegurando consistencia con el modelo deterministico de las otras bandas.
    """
    s = resultados.series
    if not s or 'Geff' not in s:
        raise ValueError('Resultados sin series con Geff. '
                         'Use run(keep_series=True).')
    C = np.asarray(s['C'])
    mask = (C >= hora_inicio * 3600) & (C < hora_fin * 3600)
    if not mask.any():
        raise ValueError(f'No hay datos en [{hora_inicio}, {hora_fin})')
    # Patron de verde efectivo en la banda
    geff_banda = np.asarray(s['Geff'])[mask].astype(np.int8)
    # Flujo: si no se entrega, usar el del motor en la banda
    if flujo_h is None:
        V_banda = np.asarray(s['V'])[mask]
        tt = float(mask.sum())
        flujo_h = float(V_banda.sum()) * 3600.0 / tt
    duracion = int(mask.sum())
    return microsim_banda(
        duracion_s=duracion, flujo_h=flujo_h, patron_verde=geff_banda,
        headway_s=2.0, n_carriles=2.0, n_replicas=n_replicas, semilla=semilla,
    )
