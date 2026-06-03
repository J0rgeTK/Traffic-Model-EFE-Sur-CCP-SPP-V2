"""
Tratamiento riguroso de la incertidumbre
========================================
Eleva el analisis de un punto estimado a una caracterizacion completa de
la incertidumbre, como exige una evaluacion social creible:

  1. Monte Carlo multivariable: propaga la incertidumbre CONJUNTA de los
     parametros (no uno a la vez) y entrega la DISTRIBUCION del VAN con
     intervalos de confianza y P(VAN > 0).

  2. Indices de Sobol (sensibilidad global): descompone la varianza del
     VAN en contribuciones de cada parametro Y sus interacciones. Supera
     al tornado OAT, que ignora interacciones.

  3. Break-even: para cada parametro, el valor que hace VAN = 0 (umbral
     de viabilidad).

  4. Valor de la informacion (EVPI): cuanto vale en CLP reducir la
     incertidumbre de un parametro antes de decidir. Justifica
     cuantitativamente la inversion en mediciones (aforos del principal).

Referencias:
  Saltelli et al. (2008) Global Sensitivity Analysis: The Primer.
  Sobol, I.M. (2001) Math. Comput. Simul. 55(1-3).
  Raiffa & Schlaifer (1961) Applied Statistical Decision Theory (VOI).
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Callable


# ============================================================
#  Distribuciones de los parametros inciertos
# ============================================================
@dataclass
class ParamIncierto:
    """Un parametro con su distribucion de incertidumbre."""
    nombre: str
    dist: str                  # 'uniforme' | 'triangular' | 'normal' | 'lognormal'
    p1: float                  # uniforme:min, triang:min, normal:media, lognorm:media_log
    p2: float                  # uniforme:max, triang:moda, normal:sigma, lognorm:sigma_log
    p3: float = 0.0            # triang:max (solo triangular)

    def muestrear(self, n: int, rng: np.random.Generator) -> np.ndarray:
        if self.dist == 'uniforme':
            return rng.uniform(self.p1, self.p2, n)
        if self.dist == 'triangular':
            return rng.triangular(self.p1, self.p2, self.p3, n)
        if self.dist == 'normal':
            return rng.normal(self.p1, self.p2, n)
        if self.dist == 'lognormal':
            return rng.lognormal(self.p1, self.p2, n)
        raise ValueError(f'Distribucion desconocida: {self.dist}')

    @property
    def rango_salib(self) -> list[float]:
        """Bounds para SALib (Sobol usa muestreo uniforme en el rango)."""
        if self.dist == 'uniforme':
            return [self.p1, self.p2]
        if self.dist == 'triangular':
            return [self.p1, self.p3]
        if self.dist == 'normal':
            return [self.p1 - 3 * self.p2, self.p1 + 3 * self.p2]
        if self.dist == 'lognormal':
            m = np.exp(self.p1)
            return [m * 0.3, m * 3.0]
        return [self.p1, self.p2]


# ============================================================
#  1. Monte Carlo multivariable
# ============================================================
@dataclass
class ResultadoMonteCarlo:
    n_muestras: int
    van_media: float
    van_mediana: float
    van_p05: float
    van_p10: float
    van_p90: float
    van_p95: float
    van_std: float
    prob_van_positivo: float          # P(VAN > 0)
    prob_van_mayor_umbral: float      # P(VAN > umbral)
    umbral: float
    muestras_van: np.ndarray = field(repr=False, default=None)

    def resumen(self) -> str:
        return (
            f'Monte Carlo (n={self.n_muestras})\n'
            f'  VAN media:   CLP {self.van_media:,.0f}\n'
            f'  VAN mediana: CLP {self.van_mediana:,.0f}\n'
            f'  IC 90%:      [CLP {self.van_p05:,.0f} .. CLP {self.van_p95:,.0f}]\n'
            f'  P(VAN > 0):  {self.prob_van_positivo*100:.1f} %\n'
            f'  P(VAN > umbral): {self.prob_van_mayor_umbral*100:.1f} %'
        )


def monte_carlo_van(eval_fn: Callable[[dict], float],
                    params_inciertos: list[ParamIncierto],
                    valores_fijos: dict | None = None,
                    n_muestras: int = 500, semilla: int = 1,
                    umbral: float = 0.0) -> ResultadoMonteCarlo:
    """Propaga la incertidumbre conjunta y entrega la distribucion del VAN."""
    rng = np.random.default_rng(semilla)
    valores_fijos = valores_fijos or {}
    # Muestrear cada parametro
    muestras = {p.nombre: p.muestrear(n_muestras, rng) for p in params_inciertos}
    vans = np.empty(n_muestras)
    for i in range(n_muestras):
        params = {**valores_fijos}
        for nombre in muestras:
            params[nombre] = muestras[nombre][i]
        vans[i] = eval_fn(params)
    return ResultadoMonteCarlo(
        n_muestras=n_muestras,
        van_media=float(np.mean(vans)),
        van_mediana=float(np.median(vans)),
        van_p05=float(np.percentile(vans, 5)),
        van_p10=float(np.percentile(vans, 10)),
        van_p90=float(np.percentile(vans, 90)),
        van_p95=float(np.percentile(vans, 95)),
        van_std=float(np.std(vans)),
        prob_van_positivo=float(np.mean(vans > 0)),
        prob_van_mayor_umbral=float(np.mean(vans > umbral)),
        umbral=umbral, muestras_van=vans,
    )


# ============================================================
#  2. Indices de Sobol (sensibilidad global)
# ============================================================
@dataclass
class ResultadoSobol:
    nombres: list[str]
    S1: dict[str, float]              # indice de primer orden
    ST: dict[str, float]              # indice total (incluye interacciones)
    S1_conf: dict[str, float]
    ST_conf: dict[str, float]

    def resumen(self) -> str:
        lineas = ['Indices de Sobol (sensibilidad global)', '',
                  f'  {"parametro":25s} {"S1":>8s} {"ST":>8s} {"interaccion":>12s}']
        orden = sorted(self.nombres, key=lambda n: -self.ST[n])
        for n in orden:
            interaccion = self.ST[n] - self.S1[n]
            lineas.append(f'  {n:25s} {self.S1[n]:>8.3f} {self.ST[n]:>8.3f} '
                          f'{interaccion:>12.3f}')
        lineas.append('')
        lineas.append('  S1 = efecto directo del parametro.')
        lineas.append('  ST = efecto total (directo + interacciones).')
        lineas.append('  ST >> S1 indica que el parametro actua por interaccion.')
        return '\n'.join(lineas)


def sobol_van(eval_fn: Callable[[dict], float],
              params_inciertos: list[ParamIncierto],
              valores_fijos: dict | None = None,
              n_base: int = 256) -> ResultadoSobol:
    """Indices de Sobol del VAN usando SALib (muestreo Saltelli)."""
    from SALib.sample import sobol as sobol_sample
    from SALib.analyze import sobol as sobol_analyze

    valores_fijos = valores_fijos or {}
    nombres = [p.nombre for p in params_inciertos]
    problem = {
        'num_vars': len(params_inciertos),
        'names': nombres,
        'bounds': [p.rango_salib for p in params_inciertos],
    }
    X = sobol_sample.sample(problem, n_base, calc_second_order=False)
    Y = np.empty(X.shape[0])
    for i, fila in enumerate(X):
        params = {**valores_fijos}
        for j, nombre in enumerate(nombres):
            params[nombre] = fila[j]
        Y[i] = eval_fn(params)
    Si = sobol_analyze.analyze(problem, Y, calc_second_order=False,
                               print_to_console=False)
    return ResultadoSobol(
        nombres=nombres,
        S1={n: float(Si['S1'][i]) for i, n in enumerate(nombres)},
        ST={n: float(Si['ST'][i]) for i, n in enumerate(nombres)},
        S1_conf={n: float(Si['S1_conf'][i]) for i, n in enumerate(nombres)},
        ST_conf={n: float(Si['ST_conf'][i]) for i, n in enumerate(nombres)},
    )


# ============================================================
#  3. Break-even (umbral de viabilidad)
# ============================================================
@dataclass
class BreakEven:
    parametro: str
    valor_base: float
    valor_break_even: float | None    # None si no cruza cero en el rango
    direccion: str                    # 'aumenta' | 'disminuye' viabilidad
    margen_pct: float | None          # distancia relativa del base al break-even


def break_even(eval_fn: Callable[[dict], float], valores_base: dict,
               parametro: str, rango: tuple[float, float],
               n_puntos: int = 40) -> BreakEven:
    """Encuentra el valor del parametro que hace VAN = 0."""
    vmin, vmax = rango
    grilla = np.linspace(vmin, vmax, n_puntos)
    vans = []
    for v in grilla:
        params = {**valores_base, parametro: v}
        vans.append(eval_fn(params))
    vans = np.array(vans)
    # Buscar cruce por cero
    be = None
    for i in range(len(grilla) - 1):
        if vans[i] == 0 or (vans[i] > 0) != (vans[i + 1] > 0):
            # interpolacion lineal
            x0, x1 = grilla[i], grilla[i + 1]
            y0, y1 = vans[i], vans[i + 1]
            be = x0 - y0 * (x1 - x0) / (y1 - y0) if y1 != y0 else x0
            break
    direccion = 'aumenta' if vans[-1] > vans[0] else 'disminuye'
    margen = None
    if be is not None and valores_base.get(parametro):
        margen = (be - valores_base[parametro]) / valores_base[parametro] * 100
    return BreakEven(parametro=parametro,
                     valor_base=valores_base.get(parametro, 0),
                     valor_break_even=be, direccion=direccion,
                     margen_pct=margen)


# ============================================================
#  4. Valor de la informacion (EVPI)
# ============================================================
@dataclass
class ValorInformacion:
    parametro: str
    van_esperado_sin_info: float      # decision con valor esperado
    van_esperado_con_info: float      # decision optima por estado
    evpi: float                       # diferencia = valor de la informacion
    evpi_interpretacion: str


def valor_informacion_perfecta(
        eval_fn: Callable[[dict], float], valores_base: dict,
        parametro: str, dist: ParamIncierto,
        n_estados: int = 200, semilla: int = 1) -> ValorInformacion:
    """Calcula el EVPI sobre un parametro incierto.

    EVPI = E[max(0, VAN|estado)] - max(0, E[VAN])

    Mide cuanto vale conocer el parametro ANTES de decidir si invertir.
    Si EVPI es alto, conviene medir antes de decidir (justifica aforos).
    """
    rng = np.random.default_rng(semilla)
    estados = dist.muestrear(n_estados, rng)
    vans_por_estado = np.array([
        eval_fn({**valores_base, parametro: float(s)}) for s in estados
    ])
    # Sin informacion: decido con el VAN del valor esperado del parametro
    van_esperado = float(np.mean(vans_por_estado))
    decision_sin_info = max(0.0, van_esperado)   # 0 = no hacer el proyecto
    # Con informacion perfecta: por cada estado decido optimamente
    decision_con_info = float(np.mean(np.maximum(0.0, vans_por_estado)))
    evpi = decision_con_info - decision_sin_info
    if evpi <= 0:
        interp = ('EVPI = 0: la decision optima no cambia con la '
                  'informacion. Medir no altera la decision.')
    elif evpi < 0.05 * abs(van_esperado) if van_esperado else evpi < 1e6:
        interp = ('EVPI bajo: la informacion tiene poco valor de decision. '
                  'La medicion confirma pero no cambia el rumbo.')
    else:
        interp = (f'EVPI alto (CLP {evpi:,.0f}): conviene MEDIR antes de '
                  'decidir. El gasto en aforos se justifica si cuesta '
                  'menos que el EVPI.')
    return ValorInformacion(
        parametro=parametro,
        van_esperado_sin_info=decision_sin_info,
        van_esperado_con_info=decision_con_info,
        evpi=evpi, evpi_interpretacion=interp,
    )


# ============================================================
#  Helper integrado: construye eval_fn de VAN para un cruce
# ============================================================
def construir_eval_van(con, cruce: str):
    """Devuelve una funcion eval_fn(params)->VAN para usar en MC/Sobol/VOI.

    Parametros que acepta el dict: k_dem, flujo_principal_h, h_saturacion,
    n_carriles_lateral, n_carriles_principal, capex_clp, opex_anual_clp,
    tasa_descuento, crecimiento_demanda, ocupacion_veh, consumo_ralenti_l_h.
    """
    from modelo_cruces import (
        Simulador, analizar_saturacion, analizar_principal,
        balance_lateral_principal, calcular_beneficio,
        calcular_externalidades, evaluar_horizonte,
    )
    from modelo_cruces.catalogo import buscar, construir_catalogo
    import datos as datos_mod

    cat = construir_catalogo(con)
    c = buscar(cat, cruce)
    v_base = c.variante('base')
    v_rec = c.variante('reconfiguracion') or v_base

    # Cache de corridas del motor por k_dem (lo costoso)
    _cache: dict = {}

    def _corridas(k_dem: float):
        key = round(k_dem, 3)
        if key not in _cache:
            ib = datos_mod.inputs_de_variante(con, v_base, k_dem=k_dem,
                                               hora_inicio_s=6*3600, hora_fin_s=24*3600)
            ir = datos_mod.inputs_de_variante(con, v_rec, k_dem=k_dem,
                                               hora_inicio_s=6*3600, hora_fin_s=24*3600)
            rb = Simulador(ib).run(mode='corrected', keep_series=True)
            rr = Simulador(ir).run(mode='corrected', keep_series=True)
            _cache[key] = (rb, rr)
        return _cache[key]

    def eval_fn(params: dict) -> float:
        d = {
            'k_dem': 1.10, 'flujo_principal_h': 1500, 'h_saturacion': 2.0,
            'n_carriles_lateral': 2, 'n_carriles_principal': 2,
            'capex_clp': 300e6, 'opex_anual_clp': 15e6,
            'tasa_descuento': 0.055, 'crecimiento_demanda': 0.02,
            'ocupacion_veh': 1.5, 'consumo_ralenti_l_h': 1.10,
        }
        d.update(params)
        rb, rr = _corridas(d['k_dem'])
        sat_a = analizar_saturacion(rb, n_carriles=d['n_carriles_lateral'],
                                     h_satur=d['h_saturacion'], usar_pre=False)
        sat_p = analizar_saturacion(rr, n_carriles=d['n_carriles_lateral'],
                                     h_satur=d['h_saturacion'], usar_pre=True)
        pri_a = analizar_principal(rb, flujo_principal_h=d['flujo_principal_h'],
                                    carriles_principal=d['n_carriles_principal'],
                                    h_satur=d['h_saturacion'], usar_pre=False)
        pri_p = analizar_principal(rr, flujo_principal_h=d['flujo_principal_h'],
                                    carriles_principal=d['n_carriles_principal'],
                                    h_satur=d['h_saturacion'], usar_pre=True)
        bal = balance_lateral_principal(sat_a, pri_a, sat_p, pri_p)
        ben = calcular_beneficio(bal['balance_neto_vh'], ocupacion=d['ocupacion_veh'])
        ext = calcular_externalidades(ben.ahorro_anual_veh_h,
                                       ben.beneficio_anual_clp,
                                       consumo_l_h=d['consumo_ralenti_l_h'])
        total = ben.beneficio_anual_clp + ext.beneficio_externalidades_clp
        ev = evaluar_horizonte(total, capex_clp=d['capex_clp'],
                                opex_anual_clp=d['opex_anual_clp'],
                                tasa_descuento=d['tasa_descuento'],
                                tasa_crecimiento_demanda=d['crecimiento_demanda'])
        return ev.van_clp

    return eval_fn
