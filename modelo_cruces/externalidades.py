"""
Externalidades sociales: combustible, emisiones, accidentes
============================================================
Beneficios adicionales del ahorro de tiempo de cola que el SNI reconoce
y que no estan en la formula basica VST x tiempo. Se calculan como un
plus al beneficio social.

Componentes:
  - Combustible ahorrado en ralenti (vehiculos detenidos en cola).
  - Emisiones evitadas (CO2, MP10, NOx) por menos ralenti.
  - Costo de accidentes en cola (rear-end tipico en colas urbanas).

Las externalidades aportan tipicamente 10-25 % al beneficio total en
proyectos urbanos de gestion de trafico (ver SECTRA, Metodologia de
preparacion y evaluacion de proyectos de inversion en transporte
publico urbano, 2019).

Valores y factores:
  - Precio social combustible: MDS Precios Sociales 2026.
  - Factores de emision: SEREMITT / U. de Chile, "Inventario de
    emisiones de vehiculos motorizados" 2019.
  - Costo social de accidentes: MDSF, factor de externalidad accidentes
    urbanos.

NOTA: estos numeros son ORDENES DE MAGNITUD razonables; los valores
exactos deben tomarse de la version anual mas reciente del MDSF y los
factores locales calibrarse con la flota de Concepcion/SPP/Coronel.
"""
from __future__ import annotations
from dataclasses import dataclass


# --- Combustible (en ralenti) ----------------------------------------------
# Litro consumido por hora-vehiculo detenido (motor encendido, sin avance).
# Fuente: DOT US Idle Reduction Tech Database; SEC Chile; Min. Energia 2023.
# Mix vehicular urbano Concepcion: ~80% bencina, 20% diesel y MTM, mas
# proporcion creciente de hibrido/electrico.
CONSUMO_RALENTI_L_H = 1.10           # mezcla urbana, conservador
PRECIO_SOCIAL_COMBUSTIBLE_CLP_L = 660  # MDS PS 2026 sin impuestos

# --- Emisiones (g/hora ralenti) ---------------------------------------------
# Factores promedio flota urbana Chile 2019, ajustados a euro 3-5 mayor parte.
EMISIONES_RALENTI_G_H = {
    'CO2':  1900,    # kg/h * 1000 = 1.9 kg/h en ralenti tipico
    'NOx':  4.5,
    'MP10': 0.18,
    'COV':  3.2,
    'CO':   8.0,
}

# Costos sociales de emisiones MDS PS 2026 (CLP/kg, urbano)
COSTO_SOCIAL_EMISIONES_CLP_KG = {
    'CO2':  35,        # baja relevancia local; se incluye por completitud
    'NOx':  3200,
    'MP10': 22000,     # alto impacto sanitario en zonas urbanas
    'COV':  900,
    'CO':   400,
}

# --- Accidentes ------------------------------------------------------------
# Tasa de accidentes en cola urbana: aproximacion conservadora basada en
# Federal Highway Administration (rear-end rate in urban queues): ~1.0
# accidente leve por cada millon de veh*h de espera (1e-6 accidentes/veh-h).
TASA_ACCIDENTES_POR_VEH_H = 1.0e-6
COSTO_SOCIAL_ACCIDENTE_LEVE_CLP = 11_500_000   # MDS PS 2026 leve urbano


@dataclass
class Externalidades:
    """Beneficios externos derivados del ahorro de tiempo de cola."""
    veh_h_ahorrado_anual:   float
    # Combustible
    litros_evitados:        float
    beneficio_combustible_clp: float
    # Emisiones
    emisiones_evitadas_kg:  dict           # {'CO2': kg, 'NOx': kg, ...}
    beneficio_emisiones_clp: dict          # {'CO2': clp, ...}
    beneficio_emisiones_total_clp: float
    # Accidentes
    accidentes_evitados:    float
    beneficio_accidentes_clp: float
    # Resumen
    beneficio_externalidades_clp: float
    factor_sobre_vst:       float          # como % del beneficio VST principal

    def desglose(self) -> str:
        return (
            f'Combustible:       CLP {self.beneficio_combustible_clp:>16,.0f}\n'
            f'Emisiones (total): CLP {self.beneficio_emisiones_total_clp:>16,.0f}\n'
            f'   CO2:            CLP {self.beneficio_emisiones_clp.get("CO2",0):>16,.0f}\n'
            f'   NOx:            CLP {self.beneficio_emisiones_clp.get("NOx",0):>16,.0f}\n'
            f'   MP10:           CLP {self.beneficio_emisiones_clp.get("MP10",0):>16,.0f}\n'
            f'Accidentes:        CLP {self.beneficio_accidentes_clp:>16,.0f}\n'
            f'TOTAL:             CLP {self.beneficio_externalidades_clp:>16,.0f}'
        )


def calcular_externalidades(veh_h_ahorrado_anual: float,
                             beneficio_vst_clp: float = 0,
                             consumo_l_h: float = CONSUMO_RALENTI_L_H,
                             precio_combustible_clp_l: float = PRECIO_SOCIAL_COMBUSTIBLE_CLP_L,
                             factores_emisiones_g_h: dict | None = None,
                             costos_emisiones_clp_kg: dict | None = None,
                             tasa_accidentes_por_vh: float = TASA_ACCIDENTES_POR_VEH_H,
                             costo_accidente_clp: float = COSTO_SOCIAL_ACCIDENTE_LEVE_CLP,
                             ) -> Externalidades:
    """Calcula los beneficios externos asociados al ahorro de cola.

    `veh_h_ahorrado_anual` es el ahorro de cola en veh*h/año (output del
    motor x 250 dias laborales). Devuelve el desglose monetizado segun
    factores oficiales chilenos (modificables para sensibilidad).
    """
    factores_emisiones_g_h = factores_emisiones_g_h or EMISIONES_RALENTI_G_H
    costos_emisiones_clp_kg = costos_emisiones_clp_kg or COSTO_SOCIAL_EMISIONES_CLP_KG

    # --- Combustible ---
    litros = veh_h_ahorrado_anual * consumo_l_h
    benef_comb = litros * precio_combustible_clp_l

    # --- Emisiones ---
    emisiones_kg = {esp: veh_h_ahorrado_anual * factores_emisiones_g_h[esp] / 1000.0
                    for esp in factores_emisiones_g_h}
    benef_emis = {esp: emisiones_kg[esp] * costos_emisiones_clp_kg.get(esp, 0)
                  for esp in emisiones_kg}
    benef_emis_total = sum(benef_emis.values())

    # --- Accidentes ---
    accidentes = veh_h_ahorrado_anual * tasa_accidentes_por_vh
    benef_acc = accidentes * costo_accidente_clp

    total = benef_comb + benef_emis_total + benef_acc
    factor = (total / beneficio_vst_clp * 100) if beneficio_vst_clp > 0 else 0

    return Externalidades(
        veh_h_ahorrado_anual=veh_h_ahorrado_anual,
        litros_evitados=litros,
        beneficio_combustible_clp=benef_comb,
        emisiones_evitadas_kg=emisiones_kg,
        beneficio_emisiones_clp=benef_emis,
        beneficio_emisiones_total_clp=benef_emis_total,
        accidentes_evitados=accidentes,
        beneficio_accidentes_clp=benef_acc,
        beneficio_externalidades_clp=total,
        factor_sobre_vst=factor,
    )
