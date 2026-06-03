"""
Desglose modal del beneficio: VST diferenciado por modo
========================================================
El MDSF entrega valores sociales del tiempo (VST) diferenciados por
modo. Tratar todos los vehiculos como auto particular sub-valora el
beneficio social cuando hay flujo de transporte publico o carga.

Para una memoria SNI defendible:
  - Identificar la composicion modal del flujo (aforos direccionales).
  - Multiplicar el tiempo ahorrado de cada modo por su VST especifico.
  - Reportar beneficio desagregado.

Valores sociales del tiempo MDS 2026 (CLP/hora-pasajero o CLP/hora-vehiculo):
"""
from __future__ import annotations
from dataclasses import dataclass, field


# Valores sociales del tiempo MDS 2026 (urbano, viaje al trabajo / estudio)
VST_2026_CLP_H = {
    'auto':           3338,   # CLP/h-pax
    'taxi':           3338,
    'transporte_pub': 1450,   # CLP/h-pax (TP urbano, menor por elasticidad)
    'camion_liviano': 4500,   # CLP/h-veh (operacional)
    'camion_pesado':  7200,   # CLP/h-veh
    'motocicleta':    2800,   # CLP/h-pax
}

# Ocupacion tipica por modo (pax/veh) - referencia EOD GC + ajuste
OCUPACION_2026 = {
    'auto':           1.50,
    'taxi':           1.20,
    'transporte_pub': 18.0,
    'camion_liviano': 1.05,
    'camion_pesado':  1.05,
    'motocicleta':    1.10,
}

# Composicion modal tipica corredor urbano Concepcion-SPP-Coronel
# (referencia, debe sustituirse con aforos modales reales)
COMPOSICION_TIPICA_CONCEPCION = {
    'auto':           0.72,   # 72%
    'taxi':           0.06,
    'transporte_pub': 0.08,
    'camion_liviano': 0.08,
    'camion_pesado':  0.04,
    'motocicleta':    0.02,
}

# 250 dias laborales/ano (anualizacion MDS estandar)
DIAS_LABORALES_ANO = 250


@dataclass
class BeneficioModo:
    """Beneficio social atribuido a un modo."""
    modo:                  str
    pct_flujo:             float
    veh_h_anual_modo:      float    # veh*h ahorrados por este modo
    ocupacion:             float
    pax_h_anual_modo:      float    # pax*h derivados
    vst_clp_h:             float
    beneficio_anual_clp:   float


@dataclass
class DesgloseModal:
    """Beneficio social anual desagregado por modo."""
    veh_h_anual_total:     float
    composicion:           dict[str, float]
    desglose:              list[BeneficioModo] = field(default_factory=list)
    beneficio_anual_total: float = 0
    modo_mayor_aporte:     str    = ''
    pct_mayor_aporte:      float  = 0

    def imprimir(self) -> str:
        lineas = ['Desglose modal del beneficio anual', '']
        lineas.append(f'  {"modo":18s} {"%flujo":>7s} {"veh*h/a":>10s} {"pax*h/a":>11s} '
                       f'{"VST":>9s} {"benef CLP/a":>16s} {"%total":>7s}')
        for d in self.desglose:
            pct_total = (d.beneficio_anual_clp / self.beneficio_anual_total * 100
                         if self.beneficio_anual_total else 0)
            lineas.append(
                f'  {d.modo:18s} {d.pct_flujo*100:>6.1f}% {d.veh_h_anual_modo:>10,.0f} '
                f'{d.pax_h_anual_modo:>11,.0f} {d.vst_clp_h:>8,.0f} '
                f'{d.beneficio_anual_clp:>15,.0f} {pct_total:>6.1f}%'
            )
        lineas.append('  ' + '-' * 90)
        lineas.append(f'  TOTAL                                 '
                       f'         {self.beneficio_anual_total:>15,.0f}')
        lineas.append('')
        lineas.append(f'  Mayor aporte: {self.modo_mayor_aporte} '
                       f'({self.pct_mayor_aporte:.1f}% del total)')
        return '\n'.join(lineas)


def desglosar_beneficio(veh_h_anual_total: float,
                         composicion: dict[str, float] | None = None,
                         vst_clp_h: dict[str, float] | None = None,
                         ocupacion: dict[str, float] | None = None,
                         ) -> DesgloseModal:
    """Desglosa un ahorro anual total en veh*h por modo.

    Si no se entrega composicion, usa la tipica Concepcion (debe
    sustituirse con aforos modales reales antes de postular).
    """
    composicion = composicion or COMPOSICION_TIPICA_CONCEPCION
    vst_clp_h = vst_clp_h or VST_2026_CLP_H
    ocupacion = ocupacion or OCUPACION_2026

    # Verificar que la composicion suma 1 (tolerancia 1%)
    total_pct = sum(composicion.values())
    if not 0.99 <= total_pct <= 1.01:
        composicion = {k: v / total_pct for k, v in composicion.items()}

    desglose: list[BeneficioModo] = []
    for modo, pct in composicion.items():
        veh_h = veh_h_anual_total * pct
        ocup = ocupacion.get(modo, 1.5)
        vst = vst_clp_h.get(modo, 3338)
        # Para TP y autos, el VST es por pax*h
        # Para camiones, el VST ya es por veh*h (operacional)
        es_por_pax = modo in ('auto', 'taxi', 'transporte_pub', 'motocicleta')
        pax_h = veh_h * ocup if es_por_pax else veh_h
        benef = pax_h * vst
        desglose.append(BeneficioModo(
            modo=modo, pct_flujo=pct, veh_h_anual_modo=veh_h,
            ocupacion=ocup, pax_h_anual_modo=pax_h,
            vst_clp_h=vst, beneficio_anual_clp=benef,
        ))
    total = sum(d.beneficio_anual_clp for d in desglose)
    mayor = max(desglose, key=lambda d: d.beneficio_anual_clp)
    return DesgloseModal(
        veh_h_anual_total=veh_h_anual_total, composicion=composicion,
        desglose=desglose, beneficio_anual_total=total,
        modo_mayor_aporte=mayor.modo,
        pct_mayor_aporte=mayor.beneficio_anual_clp / total * 100 if total else 0,
    )
