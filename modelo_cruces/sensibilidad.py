"""
Analisis de sensibilidad multivariable (tornado)
================================================
Para postulacion SNI / MDSF se exige reportar como cambia el VAN ante
variaciones de los parametros clave (k_dem, CAPEX, flujo principal,
headway de saturacion, tasa social, crecimiento de demanda).

El diagrama "tornado" ordena los parametros por impacto absoluto y
muestra el rango de cada uno: los parametros mas arriba son los mas
sensibles. Cuando un parametro tiene impacto > 50 % sobre el VAN,
necesita evidencia empirica solida.

Tipico para este proyecto:
  - flujo_principal es el mas sensible (sin aforos reales del principal,
    el balance neto puede invertirse).
  - k_dem es el segundo (factor sin justificacion documentada).
  - CAPEX y tasa social son moderadamente sensibles.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import Callable


@dataclass
class SensibilidadParam:
    """Sensibilidad de un parametro sobre una metrica."""
    nombre: str
    valor_base: float
    valor_min: float
    valor_max: float
    metrica_base: float
    metrica_min: float
    metrica_max: float
    impacto_absoluto: float          # |metrica_max - metrica_min|
    impacto_pct: float                # impacto / metrica_base * 100


@dataclass
class TornadoResultado:
    """Coleccion ordenada de sensibilidades."""
    metrica_nombre: str
    metrica_base: float
    parametros: list[SensibilidadParam]   # ordenados por impacto desc

    def imprimir(self) -> str:
        lineas = [f'Tornado de sensibilidad sobre {self.metrica_nombre}',
                  f'  Baseline: {self.metrica_base:,.2f}', '']
        for p in self.parametros:
            lineas.append(
                f'  {p.nombre:25s} [{p.valor_min:>10.3g} .. '
                f'{p.valor_max:>10.3g}]  impacto: '
                f'{p.impacto_absoluto:>+12,.2f} ({p.impacto_pct:+.1f}%)'
            )
        return '\n'.join(lineas)


def analisis_tornado(
        eval_fn: Callable[[dict], float],
        valores_base: dict[str, float],
        rangos: dict[str, tuple[float, float]],
        metrica_nombre: str = 'VAN') -> TornadoResultado:
    """Corre el analisis tornado: vario un parametro a la vez y mido impacto.

    Args:
        eval_fn: funcion que recibe un dict de parametros y devuelve la
            metrica (VAN, TIR, beneficio_anual, etc.).
        valores_base: valores baseline del proyecto.
        rangos: dict {param: (min, max)} con los extremos a explorar.
        metrica_nombre: solo para reporte.

    Returns:
        TornadoResultado con los parametros ordenados por impacto absoluto.
    """
    metrica_base = eval_fn(valores_base)
    parametros: list[SensibilidadParam] = []

    for nombre, (vmin, vmax) in rangos.items():
        if nombre not in valores_base:
            continue
        v_base = valores_base[nombre]
        # Corrida con valor minimo
        params_min = {**valores_base, nombre: vmin}
        m_min = eval_fn(params_min)
        # Corrida con valor maximo
        params_max = {**valores_base, nombre: vmax}
        m_max = eval_fn(params_max)
        imp_abs = abs(m_max - m_min)
        imp_pct = imp_abs / abs(metrica_base) * 100 if metrica_base else 0
        parametros.append(SensibilidadParam(
            nombre=nombre, valor_base=v_base, valor_min=vmin, valor_max=vmax,
            metrica_base=metrica_base, metrica_min=min(m_min, m_max),
            metrica_max=max(m_min, m_max),
            impacto_absoluto=imp_abs, impacto_pct=imp_pct,
        ))
    parametros.sort(key=lambda p: p.impacto_absoluto, reverse=True)
    return TornadoResultado(metrica_nombre=metrica_nombre,
                            metrica_base=metrica_base, parametros=parametros)


# ---------- Helper integrado para sensibilidad del VAN -----------------
def sensibilidad_van_cruce(con, cruce: str, valores_base: dict | None = None,
                            rangos: dict | None = None,
                            metrica: str = 'van') -> TornadoResultado:
    """Helper especifico: tornado del VAN de un cruce.

    Construye una funcion de evaluacion que combina motor + saturacion +
    movimiento principal + externalidades + horizonte. Los parametros
    que se pueden mover son los expuestos en `valores_base`.
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
    v_base_var = c.variante('base')
    v_rec = c.variante('reconfiguracion') or v_base_var

    base_defaults = {
        'k_dem': 1.10, 'flujo_principal_h': 1500, 'n_carriles_lateral': 2,
        'n_carriles_principal': 2, 'capex_clp': 300e6, 'opex_anual_clp': 15e6,
        'tasa_descuento': 0.055, 'crecimiento_demanda': 0.02,
        'horizonte': 20, 'h_saturacion': 2.0,
        'consumo_ralenti_l_h': 1.10, 'ocupacion_veh': 1.5,
    }
    valores_base = valores_base or base_defaults
    rangos_defaults = {
        'k_dem':              (0.90, 1.30),
        'flujo_principal_h':  (600, 2400),
        'n_carriles_lateral': (1, 3),
        'capex_clp':          (200e6, 600e6),
        'opex_anual_clp':     (5e6, 30e6),
        'tasa_descuento':     (0.04, 0.07),
        'crecimiento_demanda':(0.00, 0.04),
        'h_saturacion':       (1.8, 2.4),
        'ocupacion_veh':      (1.2, 2.0),
    }
    rangos = rangos or rangos_defaults

    def evaluar(params: dict) -> float:
        # Reconstruir inputs con k_dem y h_saturacion variables
        ib = datos_mod.inputs_de_variante(con, v_base_var, k_dem=params['k_dem'],
                                          hora_inicio_s=6*3600, hora_fin_s=24*3600)
        ir = datos_mod.inputs_de_variante(con, v_rec, k_dem=params['k_dem'],
                                          hora_inicio_s=6*3600, hora_fin_s=24*3600)
        rb = Simulador(ib).run(mode='corrected', keep_series=True)
        rr = Simulador(ir).run(mode='corrected', keep_series=True)
        sat_a = analizar_saturacion(rb, n_carriles=params['n_carriles_lateral'],
                                     h_satur=params['h_saturacion'], usar_pre=False)
        sat_p = analizar_saturacion(rr, n_carriles=params['n_carriles_lateral'],
                                     h_satur=params['h_saturacion'], usar_pre=True)
        pri_a = analizar_principal(rb, flujo_principal_h=params['flujo_principal_h'],
                                    carriles_principal=params['n_carriles_principal'],
                                    h_satur=params['h_saturacion'], usar_pre=False)
        pri_p = analizar_principal(rr, flujo_principal_h=params['flujo_principal_h'],
                                    carriles_principal=params['n_carriles_principal'],
                                    h_satur=params['h_saturacion'], usar_pre=True)
        bal = balance_lateral_principal(sat_a, pri_a, sat_p, pri_p)
        ben = calcular_beneficio(bal['balance_neto_vh'], ocupacion=params['ocupacion_veh'])
        ext = calcular_externalidades(
            ben.ahorro_anual_veh_h, ben.beneficio_anual_clp,
            consumo_l_h=params['consumo_ralenti_l_h'])
        total = ben.beneficio_anual_clp + ext.beneficio_externalidades_clp
        ev = evaluar_horizonte(total, capex_clp=params['capex_clp'],
                                opex_anual_clp=params['opex_anual_clp'],
                                horizonte_anios=int(params['horizonte']),
                                tasa_descuento=params['tasa_descuento'],
                                tasa_crecimiento_demanda=params['crecimiento_demanda'])
        if metrica == 'van':       return ev.van_clp
        if metrica == 'tir':       return (ev.tir or 0) * 100
        if metrica == 'b_c':       return ev.relacion_b_c
        if metrica == 'beneficio_anual': return total
        return ev.van_clp

    return analisis_tornado(evaluar, valores_base, rangos,
                            metrica_nombre={'van':'VAN [CLP]',
                                            'tir':'TIR [%]',
                                            'b_c':'B/C',
                                            'beneficio_anual':
                                            'Beneficio anual [CLP]'}[metrica])
