"""
Evaluacion de cartera del proyecto completo
===========================================
Agrega los beneficios de todos los cruces (simulados + extrapolados),
los separa por grupo de presentacion, aplica el costo total del proyecto
y calcula los indicadores SNI (VAN, TIR) en tres cortes temporales.

Convenciones de esta evaluacion (segun definicion del proyecto):
  - Costo total del proyecto ~ 15.000 UF, con el MANTENIMIENTO INCLUIDO
    en la inversion inicial (no hay OPEX anual separado). Esto es
    conservador: concentrar el mantenimiento de todo el horizonte en el
    ano 0 sobreestima el costo en valor presente respecto a distribuirlo.
  - Tres cortes temporales: Ano 0, Ano 10, Ano 20, con la demanda (y por
    tanto el beneficio) creciendo a una tasa anual configurable.
  - Tasa social de descuento MDS 2026 = 5,5 %.

Grupos de presentacion:
  - 'SPP'     : cruces colindantes con PAC / Ruta 160 (San Pedro de la Paz).
  - 'Coronel' : cruces en Coronel (excluyendo San Francisco a Lo Rojas,
                que tienen logica de interseccion clasica y no se presentan).
"""
from __future__ import annotations
from dataclasses import dataclass, field

UF_CLP = 40695.38                  # UF al 05-06-2026
TASA_SOCIAL = 0.055
CORTES_DEFAULT = (0, 10, 20)


@dataclass
class ItemCartera:
    """Un cruce dentro de la cartera (simulado o extrapolado)."""
    cruce: str
    grupo: str                     # 'SPP' | 'Coronel'
    origen: str                    # 'simulado' | 'extrapolado'
    beneficio_anual_clp: float
    x: float
    incluir_en_beneficio: bool = True   # False = se interviene pero no aporta


@dataclass
class CorteTemporal:
    anio: int
    beneficio_anual_clp: float     # beneficio en ese ano (con crecimiento)


@dataclass
class ResultadoCartera:
    nombre_escenario: str
    items: list[ItemCartera]
    costo_total_uf: float
    costo_total_clp: float
    tasa_descuento: float
    crecimiento_demanda: float
    horizonte_anios: int
    # Beneficios
    beneficio_anual_inicial_clp: float
    cortes: list[CorteTemporal]
    # Indicadores
    van_clp: float
    tir: float | None
    relacion_b_c: float
    payback_anios: float | None
    # Desglose por grupo
    beneficio_por_grupo: dict
    beneficio_por_origen: dict

    def imprimir(self) -> str:
        L = [f'Cartera: {self.nombre_escenario}', '']
        L.append(f'  Costo total: {self.costo_total_uf:,.0f} UF '
                 f'(CLP {self.costo_total_clp:,.0f}), mantenimiento incluido.')
        L.append(f'  Beneficio anual inicial (ano 0): CLP '
                 f'{self.beneficio_anual_inicial_clp:,.0f}')
        L.append('')
        L.append('  Beneficio por grupo:')
        for g, v in self.beneficio_por_grupo.items():
            L.append(f'    {g:10s}: CLP {v:,.0f}/ano')
        L.append('  Beneficio por origen:')
        for o, v in self.beneficio_por_origen.items():
            L.append(f'    {o:12s}: CLP {v:,.0f}/ano')
        L.append('')
        L.append('  Cortes temporales (beneficio anual proyectado):')
        for c in self.cortes:
            L.append(f'    Ano {c.anio:>2d}: CLP {c.beneficio_anual_clp:,.0f}')
        L.append('')
        tir = f'{self.tir*100:.1f} %' if self.tir is not None else 'no converge / negativa'
        L.append(f'  VAN ({self.horizonte_anios} anos): CLP {self.van_clp:,.0f}')
        L.append(f'  TIR: {tir}')
        L.append(f'  B/C: {self.relacion_b_c:.2f}')
        L.append(f'  Payback: {self.payback_anios} anos'
                 if self.payback_anios else '  Payback: > horizonte')
        return '\n'.join(L)


def _tir(flujos: list[float]) -> float | None:
    if sum(flujos) <= 0:
        return None
    lo, hi = -0.99, 5.0
    mid = 0.0
    for _ in range(200):
        mid = (lo + hi) / 2
        van = sum(f / (1 + mid) ** i for i, f in enumerate(flujos))
        if abs(van) < 1.0:
            return mid
        if van > 0:
            lo = mid
        else:
            hi = mid
    return mid


def evaluar_cartera(items: list[ItemCartera], costo_total_uf: float = 15000,
                    nombre_escenario: str = 'Proyecto completo',
                    tasa_descuento: float = TASA_SOCIAL,
                    crecimiento_demanda: float = 0.02,
                    horizonte_anios: int = 20,
                    cortes: tuple = CORTES_DEFAULT,
                    solo_positivos: bool = False) -> ResultadoCartera:
    """Evalua la cartera de cruces con costo total e indicadores SNI.

    `solo_positivos=True` cuenta el beneficio solo de cruces con aporte
    positivo (escenario de alcance optimizado), pero mantiene el costo
    total (los cruces negativos igual se intervienen fisicamente). Para
    excluir tambien su costo, filtrar los items antes de llamar.
    """
    costo_clp = costo_total_uf * UF_CLP

    # Beneficio anual inicial
    def aporta(it: ItemCartera) -> bool:
        if not it.incluir_en_beneficio:
            return False
        if solo_positivos and it.beneficio_anual_clp <= 0:
            return False
        return True

    beneficio_inicial = sum(it.beneficio_anual_clp for it in items if aporta(it))

    # Desgloses
    por_grupo: dict = {}
    por_origen: dict = {}
    for it in items:
        if not aporta(it):
            continue
        por_grupo[it.grupo] = por_grupo.get(it.grupo, 0) + it.beneficio_anual_clp
        por_origen[it.origen] = por_origen.get(it.origen, 0) + it.beneficio_anual_clp

    # Flujo de caja: ano 0 = -costo (mantenimiento incluido), anos 1..H beneficio creciente
    flujos = [-costo_clp]
    acumulado_va = -costo_clp
    payback = None
    for t in range(1, horizonte_anios + 1):
        b = beneficio_inicial * (1 + crecimiento_demanda) ** (t - 1)
        flujos.append(b)
        acumulado_va += b / (1 + tasa_descuento) ** t
        if payback is None and acumulado_va >= 0:
            payback = t
    van = sum(f / (1 + tasa_descuento) ** i for i, f in enumerate(flujos))
    tir = _tir(flujos)
    beneficios_va = sum(flujos[t] / (1 + tasa_descuento) ** t
                        for t in range(1, horizonte_anios + 1))
    b_c = beneficios_va / costo_clp if costo_clp > 0 else 0

    cortes_res = [CorteTemporal(
        anio=a,
        beneficio_anual_clp=beneficio_inicial * (1 + crecimiento_demanda) ** a)
        for a in cortes]

    return ResultadoCartera(
        nombre_escenario=nombre_escenario, items=items,
        costo_total_uf=costo_total_uf, costo_total_clp=costo_clp,
        tasa_descuento=tasa_descuento, crecimiento_demanda=crecimiento_demanda,
        horizonte_anios=horizonte_anios,
        beneficio_anual_inicial_clp=beneficio_inicial, cortes=cortes_res,
        van_clp=van, tir=tir, relacion_b_c=b_c, payback_anios=payback,
        beneficio_por_grupo=por_grupo, beneficio_por_origen=por_origen,
    )
