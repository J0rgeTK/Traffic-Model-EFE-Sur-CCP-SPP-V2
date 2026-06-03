"""
Beneficios sociales (evaluación SNI)
====================================
Cuantifica el ahorro anual de tiempo de espera vehicular y lo monetiza
con los precios sociales vigentes del Ministerio de Desarrollo Social y
Familia (MDSF), publicados en el reporte anual «Precios Sociales 2026»
(Resumen de Factores de Corrección y Precios Sociales Vigentes, 31 de
marzo de 2026).

Fuente oficial:
    https://sni.gob.cl/wp-content/uploads/Precios-Sociales-2026.pdf

Convención metodológica para evaluación SNI:
    horas_anuales = horas_día_laboral × DIAS_LABORALES_AÑO
    beneficio_CLP = horas_anuales × ocupación_veh × VST_urbano_pax
"""
from __future__ import annotations
from dataclasses import dataclass

# --- Constantes oficiales MDS Precios Sociales 2026 ---
VST_URBANO_VIAJE_2026   = 3338   # CLP / hora-pasajero, viaje en vehiculo
VST_URBANO_ESPERA_2026  = 6676   # CLP / hora-pasajero, espera (ponderador 2)
VST_INTERURBANO_TERR_2026 = 10047  # CLP / hora-pasajero, terrestre
TASA_SOCIAL_DESCUENTO_2026 = 0.055   # 5,5%

# Convención evaluación social: días laborales-año.
DIAS_LABORALES_AÑO = 250

# Ocupación promedio por vehículo urbano (configurable). 1,5 pax/veh es
# el orden de magnitud usado habitualmente en SECTRA/MTT para tránsito
# privado urbano; revisar contra la EOD local cuando esté disponible.
OCUPACION_VEH_DEFAULT = 1.5


@dataclass(frozen=True)
class BeneficioSocial:
    """Resultado de la cuantificación social del ahorro de espera."""
    ahorro_diario_veh_h:  float    # veh·h / día laboral
    ahorro_anual_veh_h:   float    # veh·h / año
    ahorro_anual_pax_h:   float    # pax·h / año
    ocupacion:            float    # pax / vehículo
    vst_clp_pax_h:        float    # CLP / pax·h utilizado
    beneficio_anual_clp:  float    # CLP / año
    dias_laborales:       int
    fuente_vst:           str

    @property
    def beneficio_anual_uf_aprox(self) -> float:
        """Conversión orientativa (UF al 31-dic-2025 = 39 727,96 CLP)."""
        return self.beneficio_anual_clp / 39727.96


def calcular_beneficio(
    ahorro_diario_veh_h: float,
    ocupacion: float = OCUPACION_VEH_DEFAULT,
    vst_clp_pax_h: float = VST_URBANO_VIAJE_2026,
    dias_laborales: int = DIAS_LABORALES_AÑO,
    factor_espera: float = 1.0,
    fuente_vst: str = 'MDS Precios Sociales 2026 - VST urbano viaje',
) -> BeneficioSocial:
    """Anualiza un ahorro diario de espera y lo monetiza.

    `ahorro_diario_veh_h` es el ahorro en veh·h del proyecto durante un
    día laboral típico (p.ej. espera_base − espera_pre). Debe ser
    POSITIVO para un proyecto con beneficio neto.

    `factor_espera` pondera el VST por tratarse de tiempo DETENIDO en
    cola, que se percibe como más oneroso que el tiempo en movimiento.
    La literatura sitúa este factor en 1,5–2,5; el propio MDS reconoce
    un VST de espera (6.676 CLP/pax·h) igual al doble del VST de viaje
    (3.338), lo que equivale a factor_espera = 2,0. El default 1,0
    mantiene la convención conservadora; usar 2,0 para reflejar
    correctamente que el proyecto ahorra tiempo detenido.
    """
    vst_efectivo = vst_clp_pax_h * factor_espera
    anual_veh_h = ahorro_diario_veh_h * dias_laborales
    anual_pax_h = anual_veh_h * ocupacion
    beneficio   = anual_pax_h * vst_efectivo
    fuente = fuente_vst
    if factor_espera != 1.0:
        fuente += f' x{factor_espera:g} (penalización tiempo detenido)'
    return BeneficioSocial(
        ahorro_diario_veh_h=ahorro_diario_veh_h,
        ahorro_anual_veh_h=anual_veh_h,
        ahorro_anual_pax_h=anual_pax_h,
        ocupacion=ocupacion,
        vst_clp_pax_h=vst_efectivo,
        beneficio_anual_clp=beneficio,
        dias_laborales=dias_laborales,
        fuente_vst=fuente,
    )
