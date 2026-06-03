"""
Analisis de saturacion con correccion Akcelik / HCM 7e
======================================================
Aplica la formula d = d1 + d2 del HCM 7e cap. 19 al resultado del motor
segundo-a-segundo, POR BANDA HORARIA. Esto resuelve un problema clave
para postulacion SNI:

  El motor deterministico promedia cola sobre la ventana completa, lo
  que NO detecta saturacion localizada (p.ej. hora-punta de la tarde).
  Akcelik por hora identifica la banda critica y entrega un retardo
  mas representativo.

Componentes:
  d1 = retardo uniforme (Webster 1958)
  d2 = retardo incremental por sobreflujo (Akcelik 1988 / HCM 7e Eq 19-39)

Rangos:
  x <= 0.85          Newell del motor preciso.
  0.85 < x <= 1.20   Akcelik valido. Reporta correccion.
  x > 1.20           Requiere microsimulacion o medicion de campo.

Referencias:
  Akcelik, R. (1988) ITE Journal 58(3), 23-27.
  HCM 7e (2022) cap. 19, Signalized Intersections, Methodology.
  Webster, F.V. (1958) Traffic Signal Settings. RR No. 39, RRL UK.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field

UMBRAL_X_LEVE  = 0.85
UMBRAL_X_GRAVE = 1.20
K_DEFAULT = 0.50            # HCM 7e Eq 19-39 para semaforos pre-tiempo
I_DEFAULT = 1.0             # Poisson, sin filtrado upstream


@dataclass
class BandaSaturacion:
    """Diagnostico Akcelik de UNA banda horaria."""
    hora_inicio:  float       # h decimal (ej. 7.0 = 07:00)
    hora_fin:     float
    demanda_veh:  float
    flujo_h:      float       # V (veh/h)
    capacidad_h:  float       # c (veh/h)
    ciclo_s:      float
    verde_eff_s:  float
    x:            float       # grado de saturacion
    d1_s:         float       # uniform delay (s/veh)
    d2_s:         float       # incremental delay (s/veh)
    espera_d1_vh: float
    espera_d2_vh: float
    espera_motor_vh: float    # del motor en la misma banda
    cola_max:     float
    cola_final:   float       # cola al final de la banda
    metodo:       str
    valida:       bool


@dataclass
class AnalisisSaturacion:
    """Diagnostico global = agregado de las bandas + banda critica."""
    cruce: str
    escenario: str
    ventana_h: float
    demanda_total: float
    espera_motor_total_vh: float
    espera_akcelik_total_vh: float
    espera_d1_total_vh: float
    espera_d2_total_vh: float
    ajuste_pct: float
    x_max: float
    banda_critica: BandaSaturacion | None
    bandas: list[BandaSaturacion] = field(default_factory=list)
    metodo_recomendado: str = ''
    valida_global: bool = True
    observacion: str = ''


def _d1(C_s: float, g_s: float, x: float) -> float:
    if C_s <= 0 or g_s < 0 or g_s > C_s:
        return 0.0
    gC = g_s / C_s
    denom = 1.0 - min(1.0, max(0.0, x)) * gC
    return 0.5 * C_s * (1.0 - gC) ** 2 / denom if denom > 0 else 0.0


def _d2(x: float, c_h: float, T_h: float,
        k: float = K_DEFAULT, I: float = I_DEFAULT) -> float:
    if c_h <= 0 or T_h <= 0 or x < 0:
        return 0.0
    cT = c_h * T_h
    interior = (x - 1.0) ** 2 + 8.0 * k * I * x / cT
    return 900.0 * T_h * ((x - 1.0) + np.sqrt(interior))


def _clasificar(x: float) -> tuple[str, bool]:
    if x <= UMBRAL_X_LEVE:
        return ('Newell (sub-saturacion)', True)
    if x <= 1.0:
        return ('Akcelik (saturacion proxima)', True)
    if x <= UMBRAL_X_GRAVE:
        return ('Akcelik (sobresaturacion moderada)', True)
    return ('Microsimulacion requerida', False)


def _analizar_banda(series: dict, mask: np.ndarray, n_carriles: float,
                    h_satur: float, cola_col: str = 'Q',
                    lost_time_s: float = 0.0,
                    factor_progresion: float = 1.0) -> BandaSaturacion | None:
    """Diagnostico Akcelik en una banda definida por la mask booleana.

    `lost_time_s`: start-up lost time por ciclo (HCM 7e ~2 s). Reduce la
        capacidad efectiva porque los primeros vehiculos arrancan lento.
        Default 0 mantiene retrocompatibilidad.
    `factor_progresion`: PF del HCM que pondera el retardo uniforme d1
        segun la calidad de la progresion (pelotones). PF<1 = onda verde
        favorable; PF>1 = pelotones que caen en rojo. Default 1 = llegadas
        aleatorias.
    """
    if not mask.any():
        return None
    C    = np.asarray(series['C'])[mask]
    V    = np.asarray(series['V'])[mask]
    Geff = np.asarray(series['Geff'])[mask]
    Q    = np.asarray(series[cola_col])[mask]
    ciclo = np.asarray(series.get('ciclo', np.full(len(C), 142.0)))[mask]

    tt = float(len(C))                              # segundos en la banda
    tv = float((Geff == 1).sum())                    # segundos en verde
    demanda = float(V.sum())                         # vehiculos
    if tt <= 0:
        return None

    ciclo_avg = float(ciclo.mean()) if len(ciclo) else 142.0
    # Start-up lost time: se pierde una vez por ciclo verde
    n_ciclos = tt / ciclo_avg if ciclo_avg > 0 else 0
    tv_efectivo = max(0.0, tv - n_ciclos * lost_time_s)

    cap_total_veh = tv_efectivo * n_carriles / h_satur
    cap_h  = cap_total_veh * 3600.0 / tt
    flujo_h = demanda * 3600.0 / tt
    x = flujo_h / cap_h if cap_h > 0 else float('inf')

    g_avg = (tv_efectivo / tt) * ciclo_avg if tt > 0 else 0.0
    T_h = tt / 3600.0

    d1 = _d1(ciclo_avg, g_avg, x) * factor_progresion
    d2 = _d2(x, cap_h, T_h)
    espera_d1 = d1 * demanda / 3600.0
    espera_d2 = d2 * demanda / 3600.0

    # Espera del motor en esta banda: integral de Q en la banda / 3600
    espera_motor = float(Q.sum()) / 3600.0

    metodo, valida = _clasificar(x)
    return BandaSaturacion(
        hora_inicio=float(C[0]) / 3600.0,
        hora_fin=float(C[-1] + 1) / 3600.0,
        demanda_veh=demanda,
        flujo_h=flujo_h, capacidad_h=cap_h,
        ciclo_s=ciclo_avg, verde_eff_s=g_avg,
        x=x, d1_s=d1, d2_s=d2,
        espera_d1_vh=espera_d1, espera_d2_vh=espera_d2,
        espera_motor_vh=espera_motor,
        cola_max=float(Q.max()), cola_final=float(Q[-1]),
        metodo=metodo, valida=valida,
    )


def analizar(resultados, n_carriles: float = 2.0, h_satur: float = 2.0,
             usar_pre: bool = False, paso_h: float = 1.0,
             lost_time_s: float = 0.0, factor_progresion: float = 1.0,
             k: float = K_DEFAULT, I: float = I_DEFAULT) -> AnalisisSaturacion:
    """Analiza saturacion por bandas horarias.

    `paso_h` = ancho de cada banda en horas (1.0 por defecto).
    `usar_pre=True` analiza la cola post-pre-vaciado (Qpre).
    `lost_time_s` = start-up lost time por ciclo (HCM 7e ~2 s).
    `factor_progresion` = PF del HCM (calidad de progresion de pelotones).
    Devuelve un AnalisisSaturacion con la lista de bandas, la banda
    critica y el agregado global.
    """
    s = resultados.series
    if not s or 'Geff' not in s:
        raise ValueError('Resultados sin series con Geff. '
                         'Use run(keep_series=True) en motor 4.x+.')
    cola_col = 'Qpre' if usar_pre else 'Q'
    C = np.asarray(s['C'])
    if len(C) == 0:
        return AnalisisSaturacion(cruce=resultados.crossing,
                                  escenario='proyecto' if usar_pre else 'actual',
                                  ventana_h=0, demanda_total=0,
                                  espera_motor_total_vh=0, espera_akcelik_total_vh=0,
                                  espera_d1_total_vh=0, espera_d2_total_vh=0,
                                  ajuste_pct=0, x_max=0, banda_critica=None)
    # Bandas horarias
    h_ini = float(C[0]) / 3600.0
    h_fin = float(C[-1] + 1) / 3600.0
    cortes = list(np.arange(np.floor(h_ini), np.ceil(h_fin) + paso_h, paso_h))
    bandas: list[BandaSaturacion] = []
    for ini_h, fin_h in zip(cortes[:-1], cortes[1:]):
        mask = (C >= ini_h * 3600) & (C < fin_h * 3600)
        b = _analizar_banda(s, mask, n_carriles, h_satur, cola_col,
                            lost_time_s=lost_time_s,
                            factor_progresion=factor_progresion)
        if b is not None and b.demanda_veh > 0:
            bandas.append(b)

    # Agregado
    demanda_total = sum(b.demanda_veh for b in bandas)
    espera_motor_total = sum(b.espera_motor_vh for b in bandas)
    espera_d1_total = sum(b.espera_d1_vh for b in bandas)
    espera_d2_total = sum(b.espera_d2_vh for b in bandas)
    espera_akcelik_total = espera_d1_total + espera_d2_total
    ajuste_pct = ((espera_akcelik_total - espera_motor_total)
                  / espera_motor_total * 100 if espera_motor_total > 0 else 0)

    if bandas:
        x_max = max(b.x for b in bandas)
        banda_crit = max(bandas, key=lambda b: b.x)
    else:
        x_max = 0.0
        banda_crit = None

    metodo, valida = _clasificar(x_max)
    if x_max <= UMBRAL_X_LEVE:
        obs = (f'Banda mas critica x={x_max:.2f} <= 0.85. Newell del motor '
               'es suficiente; no hace falta Akcelik.')
    elif x_max <= 1.0:
        obs = (f'Banda mas critica x={x_max:.2f} (proxima a saturacion). '
               'Reportar tanto motor como Akcelik en la memoria.')
    elif x_max <= UMBRAL_X_GRAVE:
        obs = (f'Banda critica x={x_max:.2f}: sobre-saturacion. Akcelik '
               'da una cota analitica; validar con microsimulacion o '
               'medicion de cola antes de postular.')
    else:
        obs = (f'Banda critica x={x_max:.2f} > 1.20: el modelo analitico '
               'no aplica. El beneficio reportado por el motor no es '
               'defendible ante el SNI sin microsimulacion.')

    return AnalisisSaturacion(
        cruce=resultados.crossing,
        escenario='proyecto' if usar_pre else 'actual',
        ventana_h=(h_fin - h_ini),
        demanda_total=demanda_total,
        espera_motor_total_vh=espera_motor_total,
        espera_akcelik_total_vh=espera_akcelik_total,
        espera_d1_total_vh=espera_d1_total,
        espera_d2_total_vh=espera_d2_total,
        ajuste_pct=ajuste_pct,
        x_max=x_max, banda_critica=banda_crit, bandas=bandas,
        metodo_recomendado=metodo, valida_global=valida, observacion=obs,
    )
