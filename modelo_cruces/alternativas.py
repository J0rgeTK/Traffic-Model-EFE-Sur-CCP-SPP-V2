"""
Comparacion de alternativas para evaluacion SNI
================================================
Toda evaluacion social SNI exige comparar el proyecto contra
alternativas razonables. Sin esto, la postulacion no se aprueba.

Alternativas tipicas para un cruce con HCALL:

  A. Hacer nada / situacion actual sin proyecto
  B. Solo pre-vaciado (sin reconfiguracion semaforica)
  C. Solo reconfiguracion (sin pre-vaciado)         [no realista, pero ayuda como contraste]
  D. Proyecto completo (pre-vaciado + reconfiguracion)
  E. Paso a desnivel ferroviario / vehicular
  F. Mejora de itinerario ferroviario (reducir HCALL)

Para cada alternativa, se evalua VAN/TIR/B-C y se ordena por VAN.
La alternativa con mejor VAN es la "alternativa optima"; el proyecto
postulado debe poder defenderse como tal, o explicar por que se
prefiere otra.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Alternativa:
    """Una alternativa a evaluar."""
    codigo: str             # 'A'..'F'
    nombre: str
    descripcion: str
    capex_clp: float
    opex_anual_clp: float
    beneficio_anual_clp: float
    factibilidad: str       # 'alta' | 'media' | 'baja'
    horizonte_anios: int = 20
    # Calculados al evaluar:
    van_clp: float = 0.0
    tir: float | None = None
    relacion_b_c: float = 0.0
    payback_anios: float | None = None
    observacion: str = ''


@dataclass
class ComparacionAlternativas:
    cruce: str
    alternativas: list[Alternativa]
    alternativa_optima: Alternativa
    alternativa_postulada: str       # codigo
    es_postulada_optima: bool
    diferencia_van_vs_optima: float

    def imprimir(self) -> str:
        lineas = [f'Comparacion de alternativas - {self.cruce}', '']
        lineas.append(f'  {"cod":>3s} {"nombre":40s} {"CAPEX":>12s} {"VAN":>15s} {"TIR":>7s} {"B/C":>6s}')
        for a in self.alternativas:
            tir = f'{a.tir*100:.1f}%' if a.tir else ' n/a '
            lineas.append(
                f'  {a.codigo:>3s} {a.nombre[:40]:40s} {a.capex_clp/1e6:>9,.0f} M '
                f'{a.van_clp/1e6:>12,.0f} M {tir:>7s} {a.relacion_b_c:>6.2f}'
            )
        lineas.append('')
        lineas.append(f'  Alternativa optima: {self.alternativa_optima.codigo} - '
                       f'{self.alternativa_optima.nombre}')
        if self.es_postulada_optima:
            lineas.append('  Postulada = optima: justifica seleccion.')
        else:
            lineas.append(f'  Postulada {self.alternativa_postulada} difiere de la '
                          f'optima en CLP {self.diferencia_van_vs_optima/1e6:,.0f} M VAN.')
            lineas.append('  La memoria SNI debe justificar por que no se elige la optima.')
        return '\n'.join(lineas)


def evaluar_alternativas(alternativas: list[Alternativa],
                          tasa_descuento: float = 0.055,
                          crecimiento_demanda: float = 0.02,
                          codigo_postulada: str = 'D') -> ComparacionAlternativas:
    """Evalua una lista de alternativas con horizonte y tasa comunes."""
    from .horizonte import evaluar_horizonte

    for a in alternativas:
        ev = evaluar_horizonte(
            beneficio_anual_inicial=a.beneficio_anual_clp,
            capex_clp=a.capex_clp, opex_anual_clp=a.opex_anual_clp,
            horizonte_anios=a.horizonte_anios,
            tasa_descuento=tasa_descuento,
            tasa_crecimiento_demanda=crecimiento_demanda)
        a.van_clp = ev.van_clp
        a.tir = ev.tir
        a.relacion_b_c = ev.relacion_b_c
        a.payback_anios = ev.payback_anios

    optima = max(alternativas, key=lambda a: a.van_clp)
    postulada = next((a for a in alternativas if a.codigo == codigo_postulada), optima)
    return ComparacionAlternativas(
        cruce='', alternativas=alternativas, alternativa_optima=optima,
        alternativa_postulada=codigo_postulada,
        es_postulada_optima=(postulada.codigo == optima.codigo),
        diferencia_van_vs_optima=postulada.van_clp - optima.van_clp,
    )


def evaluar_alternativas_cruce(con, cruce: str, k_dem: float = 1.1,
                                flujo_principal_h: float = 1500,
                                n_carriles_lateral: float = 2.0,
                                n_carriles_principal: float = 2.0,
                                capex_proyecto: float = 200e6,
                                capex_prevaciado: float = 80e6,
                                capex_reconfig: float = 50e6,
                                capex_paso_desnivel: float = 3500e6,
                                opex_anual_proyecto: float = 15e6,
                                codigo_postulada: str = 'D',
                                ) -> ComparacionAlternativas:
    """Evalua todas las alternativas para un cruce con la cadena correcta:
    motor -> Akcelik por banda -> balance principal -> beneficio social.

    Cada alternativa pasa por el mismo pipeline para que la comparacion
    sea metodologicamente consistente.
    """
    from modelo_cruces import (
        Simulador, analizar_saturacion, analizar_principal,
        balance_lateral_principal, calcular_beneficio,
        calcular_externalidades,
    )
    from modelo_cruces.catalogo import buscar, construir_catalogo
    import datos as datos_mod

    cat = construir_catalogo(con)
    c = buscar(cat, cruce)
    v_base = c.variante('base')
    v_rec = c.variante('reconfiguracion') or v_base

    ib = datos_mod.inputs_de_variante(con, v_base, k_dem=k_dem,
                                       hora_inicio_s=6*3600, hora_fin_s=24*3600)
    ir = datos_mod.inputs_de_variante(con, v_rec, k_dem=k_dem,
                                       hora_inicio_s=6*3600, hora_fin_s=24*3600)
    rb = Simulador(ib).run(mode='corrected', keep_series=True)
    rr = Simulador(ir).run(mode='corrected', keep_series=True)

    def balance_para(escena_lateral_res, usar_pre_lateral: bool,
                     escena_principal_res, usar_pre_principal: bool) -> float:
        """Calcula beneficio anual neto para una combinacion lateral/principal."""
        sat_a = analizar_saturacion(rb, n_carriles=n_carriles_lateral, usar_pre=False)
        sat_p = analizar_saturacion(escena_lateral_res, n_carriles=n_carriles_lateral,
                                     usar_pre=usar_pre_lateral)
        pri_a = analizar_principal(rb, flujo_principal_h=flujo_principal_h,
                                    carriles_principal=n_carriles_principal,
                                    usar_pre=False)
        pri_p = analizar_principal(escena_principal_res, flujo_principal_h=flujo_principal_h,
                                    carriles_principal=n_carriles_principal,
                                    usar_pre=usar_pre_principal)
        bal = balance_lateral_principal(sat_a, pri_a, sat_p, pri_p)
        ben = calcular_beneficio(bal['balance_neto_vh'])
        ext = calcular_externalidades(ben.ahorro_anual_veh_h,
                                       ben.beneficio_anual_clp)
        return ben.beneficio_anual_clp + ext.beneficio_externalidades_clp

    # Beneficios por alternativa (anual)
    benef_solo_pre = balance_para(rb, True, rb, True)        # rb + pre, mismo Geff
    benef_solo_rec = balance_para(rr, False, rr, False)      # rr sin pre
    benef_proyecto = balance_para(rr, True, rr, True)         # rr + pre (completo)

    # Paso a desnivel: beneficio = espera ACTUAL completa (lateral + principal)
    sat_a = analizar_saturacion(rb, n_carriles=n_carriles_lateral, usar_pre=False)
    pri_a = analizar_principal(rb, flujo_principal_h=flujo_principal_h,
                                carriles_principal=n_carriles_principal, usar_pre=False)
    veh_h_total_actual = (sat_a.espera_akcelik_total_vh +
                          pri_a.espera_total_vh)
    ben_pd = calcular_beneficio(veh_h_total_actual)
    ext_pd = calcular_externalidades(ben_pd.ahorro_anual_veh_h,
                                      ben_pd.beneficio_anual_clp)
    benef_paso_desnivel = ben_pd.beneficio_anual_clp + ext_pd.beneficio_externalidades_clp

    # Mejora itinerario: aproximacion ~20% del beneficio del proyecto
    benef_itinerario = benef_proyecto * 0.20

    alts = [
        Alternativa('A', 'Hacer nada (situacion actual)',
                    'No se interviene.',
                    0, 0, 0, 'alta'),
        Alternativa('B', 'Solo pre-vaciado N2',
                    'GPS+SCATS pre-tiempo; sin reset post-HCALL.',
                    capex_prevaciado, opex_anual_proyecto * 0.6,
                    benef_solo_pre, 'alta'),
        Alternativa('C', 'Solo reconfiguracion semaforica',
                    'Reset SCATS post-HCALL; sin pre-vaciado.',
                    capex_reconfig, opex_anual_proyecto * 0.4,
                    benef_solo_rec, 'alta'),
        Alternativa('D', 'Proyecto completo (pre-vaciado + reconfig)',
                    'Combinacion B+C. Postulacion principal.',
                    capex_proyecto, opex_anual_proyecto,
                    benef_proyecto, 'alta'),
        Alternativa('E', 'Paso a desnivel ferroviario',
                    'Elimina cruce. Solucion definitiva.',
                    capex_paso_desnivel, opex_anual_proyecto * 1.5,
                    benef_paso_desnivel, 'baja'),
        Alternativa('F', 'Mejora itinerario ferroviario',
                    'Reduccion HCALL 20% por mejor senalizacion.',
                    capex_proyecto * 2, opex_anual_proyecto,
                    benef_itinerario, 'media'),
    ]
    comp = evaluar_alternativas(alts, codigo_postulada=codigo_postulada)
    comp.cruce = cruce
    return comp



def alternativas_estandar(cruce: str, beneficio_proyecto_completo: float,
                           beneficio_solo_prevaciado: float,
                           beneficio_solo_reconfig: float,
                           espera_actual_total_clp: float,
                           capex_prevaciado: float = 80e6,
                           capex_reconfig: float = 50e6,
                           capex_proyecto: float = 200e6,
                           capex_paso_desnivel: float = 3500e6,
                           opex_anual_proyecto: float = 15e6,
                           reduccion_hcall_pct: float = 0.20,
                          ) -> ComparacionAlternativas:
    """Construye y evalua las alternativas estandar para un cruce.

    Args:
        beneficio_proyecto_completo: VST anual + externalidades del proyecto
            pre-vaciado + reconfig.
        beneficio_solo_prevaciado: idem solo pre-vaciado.
        beneficio_solo_reconfig: idem solo reconfig.
        espera_actual_total_clp: costo anual equivalente de la espera
            actual SIN proyecto (proxy del beneficio de un paso a desnivel
            que elimina la cola completamente).
        capex_*: inversion inicial de cada alternativa.
        reduccion_hcall_pct: cuanto bajaria el HCALL con mejora ferroviaria
            (proxy para beneficio de alternativa F).
    """
    alts = [
        Alternativa(
            codigo='A', nombre='Hacer nada (situacion actual)',
            descripcion='No se interviene. Solo gastos de mantencion actual.',
            capex_clp=0, opex_anual_clp=0, beneficio_anual_clp=0,
            factibilidad='alta'),
        Alternativa(
            codigo='B', nombre='Solo pre-vaciado N2',
            descripcion='GPS + SCATS pre-tiempo. Sin reconfiguracion.',
            capex_clp=capex_prevaciado, opex_anual_clp=opex_anual_proyecto * 0.6,
            beneficio_anual_clp=beneficio_solo_prevaciado, factibilidad='alta'),
        Alternativa(
            codigo='C', nombre='Solo reconfiguracion semaforica',
            descripcion='Reset SCATS post-HCALL. Sin pre-vaciado.',
            capex_clp=capex_reconfig, opex_anual_clp=opex_anual_proyecto * 0.4,
            beneficio_anual_clp=beneficio_solo_reconfig, factibilidad='alta'),
        Alternativa(
            codigo='D', nombre='Proyecto completo (pre-vaciado + reconfig)',
            descripcion='Combinacion de B y C. Postulacion principal.',
            capex_clp=capex_proyecto, opex_anual_clp=opex_anual_proyecto,
            beneficio_anual_clp=beneficio_proyecto_completo, factibilidad='alta'),
        Alternativa(
            codigo='E', nombre='Paso a desnivel ferroviario',
            descripcion='Elimina cruce a nivel. Solucion definitiva.',
            capex_clp=capex_paso_desnivel, opex_anual_clp=opex_anual_proyecto * 1.5,
            beneficio_anual_clp=espera_actual_total_clp,
            factibilidad='baja'),
        Alternativa(
            codigo='F', nombre='Mejora itinerario ferroviario',
            descripcion=f'Reduccion del HCALL {reduccion_hcall_pct*100:.0f}% por '
                         'mejor senalizacion / mayor velocidad.',
            capex_clp=capex_proyecto * 2,
            opex_anual_clp=opex_anual_proyecto,
            beneficio_anual_clp=beneficio_proyecto_completo * reduccion_hcall_pct * 2,
            factibilidad='media'),
    ]
    comp = evaluar_alternativas(alts, codigo_postulada='D')
    comp.cruce = cruce
    return comp
