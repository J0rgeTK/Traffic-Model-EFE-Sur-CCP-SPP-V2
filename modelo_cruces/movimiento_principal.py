"""
Movimiento principal (tipicamente Ruta 160 norte-sur)
=====================================================
El motor evalua SOLO el movimiento lateral. La Ruta 160 (principal) tiene
flujos mucho mayores y experimenta rojo en:
  - HCALL (forzoso)
  - Verde lateral (programado por SCATS)
  - Entreverdes

Si el proyecto aporta verde lateral extra (pre-vaciado, reconfig), el
principal pierde verde y su espera aumenta. Ignorarlo es metodologicamente
asimetrico y puede llevar a sobreestimar el beneficio neto.

NOTA IMPORTANTE: el levantamiento de aforos del Excel original solo
cubre el lateral. Este modulo trabaja con un FLUJO PARAMETRICO del
principal (configurable por cruce), tipicamente derivado de:
  - DOT Chile, MTT, Plan Maestro Vial Concepcion
  - EOD Gran Concepcion (factor de actualizacion)
  - Sensores SCATS del propio controlador (cuando disponibles)

Sin aforos reales del principal, los numeros aqui son APROXIMACIONES;
deben validarse con conteo direccional en terreno antes de postular.

Metodologia:
  Para cada banda horaria:
    rojo_principal_s = HCALL_s + verde_lateral_s + entreverde_s
    verde_principal_s = ventana_s - rojo_principal_s
    cap_principal_h  = verde_principal_s * carriles_principal / h
    x_principal     = flujo_principal_h / cap_principal_h
    espera (Webster + Akcelik d2)
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field

from .saturacion import _d1, _d2, _clasificar, UMBRAL_X_LEVE, UMBRAL_X_GRAVE


@dataclass
class BandaPrincipal:
    """Diagnostico del movimiento principal en una banda horaria."""
    hora_inicio:    float
    hora_fin:       float
    flujo_h:        float       # V_principal (veh/h, parametrico)
    capacidad_h:    float       # c_principal (veh/h)
    rojo_total_s:   float       # rojo absorbido por principal en la banda
    verde_eff_s:    float       # verde efectivo para principal
    x:              float
    d1_s:           float
    d2_s:           float
    espera_vh:      float
    metodo:         str
    valida:         bool


@dataclass
class AnalisisPrincipal:
    """Diagnostico global del movimiento principal."""
    cruce: str
    escenario: str               # 'actual' o 'proyecto'
    flujo_h_supuesto: float
    carriles_principal: float
    x_max: float
    espera_total_vh: float
    bandas: list[BandaPrincipal] = field(default_factory=list)
    aviso: str = ''


def _rojo_principal_por_banda(series: dict, mask: np.ndarray) -> tuple[float, float]:
    """Calcula (segundos en rojo del principal, segundos en verde principal).

    Principal en rojo cuando:
      - HCALL activo (G=1)         -> barrera baja, no puede haber verde principal
      - Verde lateral activo (Geff=1) -> el lateral tiene paso
    En otros instantes el principal puede tener verde (asumiendo que el
    semaforo tiene solo dos movimientos: principal y lateral).
    """
    if not mask.any():
        return 0.0, 0.0
    hcall = np.asarray(series['G'])[mask]
    geff  = np.asarray(series['Geff'])[mask]
    tt = float(len(hcall))
    rojo_principal_s = float(((hcall == 1) | (geff == 1)).sum())
    verde_principal_s = tt - rojo_principal_s
    return rojo_principal_s, verde_principal_s


def analizar(resultados, flujo_principal_h: float = 1500.0,
             carriles_principal: float = 2.0, h_satur: float = 2.0,
             usar_pre: bool = False, paso_h: float = 1.0) -> AnalisisPrincipal:
    """Evalua espera del movimiento principal a partir de las series del motor.

    Args:
        resultados: salida de Simulador.run(keep_series=True).
        flujo_principal_h: flujo medio supuesto del principal (veh/h).
            Tipico para Ruta 160 en zona urbana: 1200-2500. Por defecto 1500.
        carriles_principal: numero de carriles del principal por sentido.
        h_satur: headway de saturacion (s/veh).
        usar_pre: si True, usa el escenario con pre-vaciado (cambia el
            patron temporal del verde lateral).
        paso_h: ancho de banda en horas.
    """
    s = resultados.series
    if not s or 'Geff' not in s:
        raise ValueError('Resultados sin series con Geff.')

    # Si usar_pre=True, asumimos que Geff del motor representa el patron de
    # verde lateral DEL escenario corrido. El motor entrega Geff aplicable.
    C = np.asarray(s['C'])
    if len(C) == 0:
        return AnalisisPrincipal(cruce=resultados.crossing,
                                 escenario='proyecto' if usar_pre else 'actual',
                                 flujo_h_supuesto=flujo_principal_h,
                                 carriles_principal=carriles_principal,
                                 x_max=0, espera_total_vh=0)

    h_ini = float(C[0]) / 3600.0
    h_fin = float(C[-1] + 1) / 3600.0
    cortes = list(np.arange(np.floor(h_ini), np.ceil(h_fin) + paso_h, paso_h))

    ciclo_series = np.asarray(s.get('ciclo', np.full(len(C), 142.0)))
    bandas: list[BandaPrincipal] = []

    for ini_h, fin_h in zip(cortes[:-1], cortes[1:]):
        mask = (C >= ini_h * 3600) & (C < fin_h * 3600)
        if not mask.any():
            continue
        rojo_s, verde_s = _rojo_principal_por_banda(s, mask)
        tt = float(mask.sum())
        if tt == 0:
            continue
        # Capacidad del principal
        cap_total_veh = verde_s * carriles_principal / h_satur
        cap_h = cap_total_veh * 3600.0 / tt
        demanda = flujo_principal_h * tt / 3600.0
        x = flujo_principal_h / cap_h if cap_h > 0 else float('inf')

        ciclo_avg = float(ciclo_series[mask].mean())
        g_avg = (verde_s / tt) * ciclo_avg
        T_h = tt / 3600.0
        d1 = _d1(ciclo_avg, g_avg, x)
        d2 = _d2(x, cap_h, T_h)
        espera_vh = (d1 + d2) * demanda / 3600.0
        metodo, valida = _clasificar(x)
        bandas.append(BandaPrincipal(
            hora_inicio=ini_h, hora_fin=fin_h, flujo_h=flujo_principal_h,
            capacidad_h=cap_h, rojo_total_s=rojo_s, verde_eff_s=g_avg,
            x=x, d1_s=d1, d2_s=d2, espera_vh=espera_vh,
            metodo=metodo, valida=valida,
        ))

    espera_total = sum(b.espera_vh for b in bandas)
    x_max = max((b.x for b in bandas), default=0.0)
    aviso = ('Flujo del principal asumido = {:.0f} veh/h. Validar con '
             'aforos direccionales de Ruta 160 antes de usar en '
             'evaluacion SNI.').format(flujo_principal_h)

    return AnalisisPrincipal(
        cruce=resultados.crossing,
        escenario='proyecto' if usar_pre else 'actual',
        flujo_h_supuesto=flujo_principal_h,
        carriles_principal=carriles_principal,
        x_max=x_max, espera_total_vh=espera_total, bandas=bandas,
        aviso=aviso,
    )


def balance_lateral_principal(
        analisis_sat_actual, analisis_principal_actual,
        analisis_sat_proyecto, analisis_principal_proyecto) -> dict:
    """Compara beneficio en lateral vs costo en principal.

    Devuelve dict con:
      - delta_lateral_vh   (lateral espera baja)
      - delta_principal_vh (principal espera sube/baja)
      - balance_neto_vh
      - razon_lateral_principal
      - es_neto_positivo
    """
    delta_lat = (analisis_sat_actual.espera_akcelik_total_vh
                 - analisis_sat_proyecto.espera_akcelik_total_vh)
    delta_pri = (analisis_principal_proyecto.espera_total_vh
                 - analisis_principal_actual.espera_total_vh)
    balance = delta_lat - delta_pri
    razon = (delta_lat / delta_pri) if delta_pri > 0 else float('inf')
    return {
        'delta_lateral_vh': delta_lat,
        'delta_principal_vh': delta_pri,
        'balance_neto_vh': balance,
        'razon_lateral_principal': razon,
        'es_neto_positivo': balance > 0,
    }
