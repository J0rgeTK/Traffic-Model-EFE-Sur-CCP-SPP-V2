"""
modelo_cruces
=============
Paquete del modelo de cruces ferroviarios de la Linea 2 Biotren.

Modulos:
  motor        motor de simulacion segundo a segundo (validado)
  modelos      dataclasses del dominio (Variante, CatalogoCruce, ...)
  config       mapeo con el Excel original (sin posiciones hardcodeadas)
  catalogo     variantes por cruce (base / reconfiguracion / pre-vaciado)
  validadores  reglas de integridad de las bases de datos
  importador   importadores modulares (Excel original; plantilla canonica)
"""
from .motor import Inputs, Resultados, PhasePlan, Simulador
from .modelos import (
    Variante, CatalogoCruce, ProyectoReconfig, ROL_BASE, ROL_RECONFIG,
)
from .beneficios import (
    BeneficioSocial, calcular_beneficio,
    VST_URBANO_VIAJE_2026, DIAS_LABORALES_AÑO, OCUPACION_VEH_DEFAULT,
)

__all__ = [
    'Inputs', 'Resultados', 'PhasePlan', 'Simulador',
    'Variante', 'CatalogoCruce', 'ProyectoReconfig',
    'ROL_BASE', 'ROL_RECONFIG',
    'BeneficioSocial', 'calcular_beneficio',
    'VST_URBANO_VIAJE_2026', 'DIAS_LABORALES_AÑO', 'OCUPACION_VEH_DEFAULT',
]
