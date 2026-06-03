"""
Variabilidad estocastica del HCALL + horizonte de evaluacion SNI
================================================================
Dos modulos pequenos que cierran brechas del analisis critico:

1. variabilidad_hcall: el motor original asume HCALL determinista
   (mismo segundo cada dia). En operacion real hay jitter de +/- 2 min
   por desviaciones del itinerario ferroviario, GPS, condiciones de via.
   Esto evalua sensibilidad operacional del proyecto.

2. evaluar_horizonte: VAN/TIR/B-C a 15 anos con tasa social MDS 2026
   (5.5 %) sobre un beneficio anual creciente segun tasa de demanda.

Estos son los dos modulos finales que cierran las brechas del informe
critico tras saturacion, movimiento principal y externalidades.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass


# ============================================================
#  Variabilidad estocastica del HCALL
# ============================================================
@dataclass
class JitterHCALL:
    """Replica del motor con jitter en hcall_in/out (varianza operacional)."""
    n_rep: int
    sigma_s: float                    # desviacion del jitter (segundos)
    espera_media_vh: float
    espera_p10_vh: float
    espera_p90_vh: float
    espera_max_vh: float
    perdida_pct_vs_ideal: float       # cuanto se pierde del beneficio "ideal"


def correr_jitter_hcall(simulador, inp, n_rep: int = 30,
                        sigma_s: float = 90.0, seed: int = 42,
                        usar_pre: bool = True) -> JitterHCALL:
    """Corre n_rep replicaciones con jitter gaussiano sobre HCALL.

    `sigma_s = 90` modela ±90 s (±1,5 min) tipico de operacion ferroviaria
    suburbana sin AVL preciso. Para sistemas con AVL bien calibrado usar
    sigma_s = 30 (±30 s).
    """
    from modelo_cruces import Inputs

    rng = np.random.default_rng(seed)
    base_in  = np.array(inp.hcall_in,  dtype=float)
    base_out = np.array(inp.hcall_out, dtype=float)
    n_eventos = len(base_in)
    esperas: list[float] = []

    for _ in range(n_rep):
        # Aplica el mismo jitter al par (in, out) para preservar la duracion
        jitter = rng.normal(0.0, sigma_s, n_eventos)
        new_in  = np.clip(base_in  + jitter, 0, 86399).astype(int).tolist()
        new_out = np.clip(base_out + jitter, 0, 86400).astype(int).tolist()
        new_in.sort(); new_out.sort()

        inp_perturbed = Inputs(
            crossing=inp.crossing, start_s=inp.start_s, end_s=inp.end_s,
            h=inp.h, n_carriles=inp.n_carriles, buffer=inp.buffer,
            k_dem=inp.k_dem, prog_fases=inp.prog_fases, plan=inp.plan,
            llegadas=inp.llegadas, hcall_in=new_in, hcall_out=new_out,
            post_hcall_lateral=inp.post_hcall_lateral,
        )
        from modelo_cruces import Simulador
        r = Simulador(inp_perturbed).run(mode='corrected')
        esperas.append(r.espera_pre_vh if usar_pre else r.espera_vh)

    arr = np.array(esperas)
    res_ideal = simulador.run(mode='corrected')
    ideal = res_ideal.espera_pre_vh if usar_pre else res_ideal.espera_vh
    perdida = ((arr.mean() - ideal) / ideal * 100) if ideal > 0 else 0
    return JitterHCALL(
        n_rep=n_rep, sigma_s=sigma_s,
        espera_media_vh=float(arr.mean()),
        espera_p10_vh=float(np.percentile(arr, 10)),
        espera_p90_vh=float(np.percentile(arr, 90)),
        espera_max_vh=float(arr.max()),
        perdida_pct_vs_ideal=perdida,
    )


# ============================================================
#  Evaluacion social — horizonte 15 anos
# ============================================================
TASA_SOCIAL_DESCUENTO_2026 = 0.055    # 5,5 % anual (MDS 2026)
HORIZONTE_SNI_DEFAULT = 15            # anos
TASA_CRECIMIENTO_DEMANDA_DEFAULT = 0.02   # 2 % anual urbano Concepcion


@dataclass
class EvaluacionHorizonte:
    """Valor actual del beneficio sobre el horizonte SNI."""
    horizonte_anios: int
    tasa_descuento: float
    tasa_crecimiento_demanda: float
    beneficio_anual_inicial: float
    capex_clp: float
    opex_anual_clp: float
    van_clp: float                    # Valor Actual Neto
    tir: float | None                 # Tasa Interna de Retorno (None si no converge)
    relacion_b_c: float               # B/C descontado
    payback_anios: float | None
    detalle_flujos: list[dict]


def _calcular_tir(flujos: list[float], precision: float = 1e-5,
                  max_iter: int = 100) -> float | None:
    """TIR por biseccion."""
    if sum(flujos) <= 0:
        return None
    lo, hi = -0.99, 5.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        van = sum(f / (1 + mid) ** i for i, f in enumerate(flujos))
        if abs(van) < precision:
            return mid
        if van > 0:
            lo = mid
        else:
            hi = mid
    return mid if abs(van) < 0.01 * abs(flujos[0]) else None


def evaluar_horizonte(beneficio_anual_inicial: float, capex_clp: float,
                       opex_anual_clp: float = 0,
                       horizonte_anios: int = HORIZONTE_SNI_DEFAULT,
                       tasa_descuento: float = TASA_SOCIAL_DESCUENTO_2026,
                       tasa_crecimiento_demanda: float = TASA_CRECIMIENTO_DEMANDA_DEFAULT,
                       ) -> EvaluacionHorizonte:
    """Calcula VAN/TIR/B/C del proyecto sobre el horizonte SNI."""
    flujos: list[float] = []
    detalle: list[dict] = []
    # Ano 0: inversion
    flujos.append(-capex_clp)
    detalle.append({'anio': 0, 'beneficio': 0, 'opex': 0,
                    'flujo_neto': -capex_clp,
                    'valor_actual': -capex_clp})
    acumulado_va = -capex_clp
    payback = None
    for t in range(1, horizonte_anios + 1):
        # Beneficio crece con demanda
        beneficio_t = beneficio_anual_inicial * (1 + tasa_crecimiento_demanda) ** (t - 1)
        flujo_neto = beneficio_t - opex_anual_clp
        va = flujo_neto / (1 + tasa_descuento) ** t
        flujos.append(flujo_neto)
        acumulado_va += va
        if payback is None and acumulado_va >= 0:
            payback = float(t)
        detalle.append({'anio': t, 'beneficio': beneficio_t,
                        'opex': opex_anual_clp, 'flujo_neto': flujo_neto,
                        'valor_actual': va})
    van = sum(f / (1 + tasa_descuento) ** i for i, f in enumerate(flujos))
    tir = _calcular_tir(flujos)
    # B/C descontado
    beneficios_va = sum(d['valor_actual'] for d in detalle if d['anio'] > 0
                        and d['beneficio'] > 0)
    costos_va = capex_clp + sum(opex_anual_clp / (1 + tasa_descuento) ** t
                                  for t in range(1, horizonte_anios + 1))
    b_c = beneficios_va / costos_va if costos_va > 0 else 0
    return EvaluacionHorizonte(
        horizonte_anios=horizonte_anios,
        tasa_descuento=tasa_descuento,
        tasa_crecimiento_demanda=tasa_crecimiento_demanda,
        beneficio_anual_inicial=beneficio_anual_inicial,
        capex_clp=capex_clp, opex_anual_clp=opex_anual_clp,
        van_clp=van, tir=tir, relacion_b_c=b_c,
        payback_anios=payback, detalle_flujos=detalle,
    )
