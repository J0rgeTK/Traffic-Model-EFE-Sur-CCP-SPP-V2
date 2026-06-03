"""
Extrapolacion de beneficios a cruces sin programacion semaforica
================================================================
Algunos cruces tienen flujo medido pero NO programacion semaforica, por
lo que no se pueden simular directamente. Este modulo estima su beneficio
social por transferencia desde los cruces simulados (anclas).

PRINCIPIO METODOLOGICO CENTRAL:
  El beneficio del proyecto NO escala linealmente con el flujo. Depende
  criticamente del REGIMEN DE SATURACION del movimiento lateral:
    - x < ~0.9  (subsaturado): la reconfiguracion entrega verde al lateral
      que no lo necesita, a costa del principal -> beneficio NEGATIVO o nulo.
    - x > ~1.0  (saturado): la reconfiguracion descongestiona el lateral
      saturado -> beneficio POSITIVO creciente con x.

  Por eso la extrapolacion transfiere el beneficio UNITARIO (CLP por
  vehiculo-lateral) como funcion del grado de saturacion estimado, NO
  como un promedio plano. Un cruce subsaturado extrapolado puede (y debe)
  dar beneficio cero o negativo.

LIMITES (declarar en la memoria SNI):
  - La extrapolacion es ESTIMACION para dimensionamiento de cartera, NO
    beneficio social formal por cruce. El SNI exige medicion/simulacion
    para reclamar beneficio por cruce.
  - Todos los cruces ancla estan en San Pedro; extrapolar a Coronel asume
    transferibilidad de la dinamica operacional, no validada localmente.
  - El flujo del principal se asume; sin aforos direccionales reales el
    costo en Ruta 160 (y por tanto el balance neto) es incierto.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field


@dataclass
class AnclaSimulada:
    """Caracterizacion de un cruce simulado, usado como ancla."""
    cruce: str
    cruce_id: int
    grupo: str                    # 'SPP' | 'Coronel'
    flujo_lateral_diario: float   # veh/dia (ventana 6-24h)
    flujo_pico_h: float           # veh/h en la banda pico
    n_carriles_lateral: float
    x_max: float
    capacidad_pico_h: float       # veh/h capacidad efectiva en pico
    balance_neto_vh: float        # veh*h/dia
    beneficio_anual_clp: float
    beneficio_por_veh_lateral: float   # CLP/(veh-dia)


@dataclass
class CruceExtrapolado:
    """Estimacion de beneficio para un cruce sin programacion."""
    cruce: str
    cruce_id: int
    grupo: str
    flujo_lateral_diario: float
    flujo_pico_h: float
    n_carriles_lateral: float
    x_estimado: float
    regimen: str                  # 'subsaturado' | 'saturacion proxima' | 'saturado'
    beneficio_unitario_clp: float
    beneficio_estimado_clp: float
    beneficio_min_clp: float      # banda inferior (incertidumbre)
    beneficio_max_clp: float      # banda superior
    anclas_usadas: list[str] = field(default_factory=list)
    advertencia: str = ''


def caracterizar_anclas(anclas_raw: list[dict]) -> list[AnclaSimulada]:
    """Construye las anclas desde resultados de simulacion ya calculados.

    `anclas_raw` es una lista de dicts con las claves:
        cruce, cruce_id, grupo, flujo_lateral_diario, flujo_pico_h,
        n_carriles_lateral, x_max, capacidad_pico_h, balance_neto_vh,
        beneficio_anual_clp
    """
    anclas = []
    for a in anclas_raw:
        bpv = (a['beneficio_anual_clp'] / a['flujo_lateral_diario']
               if a['flujo_lateral_diario'] > 0 else 0)
        anclas.append(AnclaSimulada(
            cruce=a['cruce'], cruce_id=a['cruce_id'], grupo=a['grupo'],
            flujo_lateral_diario=a['flujo_lateral_diario'],
            flujo_pico_h=a['flujo_pico_h'],
            n_carriles_lateral=a['n_carriles_lateral'],
            x_max=a['x_max'], capacidad_pico_h=a['capacidad_pico_h'],
            balance_neto_vh=a['balance_neto_vh'],
            beneficio_anual_clp=a['beneficio_anual_clp'],
            beneficio_por_veh_lateral=bpv,
        ))
    return anclas


def _regimen(x: float) -> str:
    if x < 0.85:
        return 'subsaturado'
    if x < 1.0:
        return 'saturacion proxima'
    return 'saturado'


def _curva_beneficio_unitario(anclas: list[AnclaSimulada]):
    """Construye la relacion beneficio_unitario = f(x) por interpolacion.

    Ordena las anclas por x y devuelve (xs, bpv) para np.interp. Esto
    captura el cambio de signo: subsaturados (negativo) -> saturados
    (positivo).
    """
    pares = sorted(((a.x_max, a.beneficio_por_veh_lateral) for a in anclas),
                   key=lambda p: p[0])
    xs = np.array([p[0] for p in pares])
    bpv = np.array([p[1] for p in pares])
    return xs, bpv


def estimar_capacidad_pico_ref(anclas: list[AnclaSimulada]) -> float:
    """Capacidad efectiva pico por carril lateral, mediana de las anclas."""
    caps = [a.capacidad_pico_h / a.n_carriles_lateral
            for a in anclas if a.n_carriles_lateral > 0]
    return float(np.median(caps)) if caps else 900.0


def extrapolar_cruce(cruce: str, cruce_id: int, grupo: str,
                     flujo_lateral_diario: float, flujo_pico_h: float,
                     n_carriles_lateral: float,
                     anclas: list[AnclaSimulada],
                     cap_pico_por_carril: float | None = None
                     ) -> CruceExtrapolado:
    """Estima el beneficio de un cruce sin programacion por transferencia.

    1. Estima x_max ~ flujo_pico_h / (cap_pico_por_carril * n_carriles).
    2. Evalua el beneficio unitario interpolando f(x) de las anclas.
    3. Aplica banda de incertidumbre con el rango de anclas del mismo regimen.
    """
    if cap_pico_por_carril is None:
        cap_pico_por_carril = estimar_capacidad_pico_ref(anclas)
    cap_estimada = cap_pico_por_carril * n_carriles_lateral
    x_est = flujo_pico_h / cap_estimada if cap_estimada > 0 else 0.0

    xs, bpv = _curva_beneficio_unitario(anclas)
    # np.interp satura en los extremos (no extrapola fuera del rango de x).
    bpv_est = float(np.interp(x_est, xs, bpv))
    beneficio = bpv_est * flujo_lateral_diario

    reg = _regimen(x_est)
    # Banda de incertidumbre: anclas en el mismo regimen
    bpv_regimen = [a.beneficio_por_veh_lateral for a in anclas
                   if _regimen(a.x_max) == reg]
    if bpv_regimen:
        bmin = min(bpv_regimen) * flujo_lateral_diario
        bmax = max(bpv_regimen) * flujo_lateral_diario
    else:
        bmin = beneficio * 0.5
        bmax = beneficio * 1.5
    anclas_reg = [a.cruce for a in anclas if _regimen(a.x_max) == reg]

    adv = ''
    if grupo == 'Coronel':
        adv = ('Extrapolado desde anclas de San Pedro; sin cruce medido '
               'en Coronel. Transferibilidad no validada localmente.')
    if reg == 'subsaturado':
        adv += (' Cruce subsaturado: beneficio probablemente nulo o '
                'negativo (la reconfiguracion no se justifica).')

    return CruceExtrapolado(
        cruce=cruce, cruce_id=cruce_id, grupo=grupo,
        flujo_lateral_diario=flujo_lateral_diario, flujo_pico_h=flujo_pico_h,
        n_carriles_lateral=n_carriles_lateral, x_estimado=x_est, regimen=reg,
        beneficio_unitario_clp=bpv_est, beneficio_estimado_clp=beneficio,
        beneficio_min_clp=min(bmin, bmax), beneficio_max_clp=max(bmin, bmax),
        anclas_usadas=sorted(set(anclas_reg)), advertencia=adv.strip(),
    )
