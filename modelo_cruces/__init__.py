"""
modelo_cruces
=============
Paquete del modelo de cruces ferroviarios de la Linea 2 Biotren.

Modulos:
  motor        motor de simulacion segundo a segundo (validado)
  modelos      dataclasses del dominio (Variante, CatalogoCruce, ...)
  config       mapeo con el fuente de referencia (sin posiciones hardcodeadas)
  catalogo     variantes por cruce (base / reconfiguracion / pre-vaciado)
  validadores  reglas de integridad de las bases de datos
  importador   importadores modulares (fuente de referencia; plantilla canonica)
"""
from .motor import Inputs, Resultados, PhasePlan, Simulador
from .modelos import (
    Variante, CatalogoCruce, ProyectoReconfig, ROL_BASE, ROL_RECONFIG,
)
from .beneficios import (
    BeneficioSocial, calcular_beneficio,
    VST_URBANO_VIAJE_2026, VST_URBANO_ESPERA_2026,
    DIAS_LABORALES_AÑO, OCUPACION_VEH_DEFAULT,
)
from .saturacion import analizar as analizar_saturacion
from .movimiento_principal import (
    analizar as analizar_principal, balance_lateral_principal,
)
from .externalidades import (
    calcular_externalidades, Externalidades,
    CONSUMO_RALENTI_L_H, PRECIO_SOCIAL_COMBUSTIBLE_CLP_L,
)
from .horizonte import (
    evaluar_horizonte, EvaluacionHorizonte, correr_jitter_hcall, JitterHCALL,
    TASA_SOCIAL_DESCUENTO_2026, HORIZONTE_SNI_DEFAULT,
    TASA_CRECIMIENTO_DEMANDA_DEFAULT,
)
from .microsim import (
    microsim_banda, microsim_desde_resultados, ResultadoMicrosim,
)
from .sensibilidad import (
    analisis_tornado, sensibilidad_van_cruce,
    TornadoResultado, SensibilidadParam,
)
from .alternativas import (
    Alternativa, ComparacionAlternativas,
    evaluar_alternativas, alternativas_estandar, evaluar_alternativas_cruce,
)
from .desglose_modal import (
    desglosar_beneficio, DesgloseModal, BeneficioModo,
    VST_2026_CLP_H, OCUPACION_2026, COMPOSICION_TIPICA_CONCEPCION,
)
from .riesgos import (
    Riesgo, MatrizRiesgos, matriz_riesgos_estandar,
)
from .extrapolacion import (
    AnclaSimulada, CruceExtrapolado, caracterizar_anclas,
    extrapolar_cruce, estimar_capacidad_pico_ref,
)
from .composicion import ocupacion_efectiva_cruce, OCUPACION_BUS_DEFAULT
from .proyecto_incremental import (
    EvaluacionIncremental, EjeBeneficio, evaluar_incremental,
    construir_ejes_beneficio, beneficio_valorizable_total,
)
from .tipologia import (
    ClasificacionCruce, clasificar, clasificar_catalogo, resumen_tipologico,
    TIPOLOGIAS, MODELO_POR_TIPOLOGIA, TIPOLOGIAS_CON_BENEFICIO_PROYECTO,
)
from .cartera import (
    ItemCartera, CorteTemporal, ResultadoCartera, evaluar_cartera, UF_CLP,
)
from .incertidumbre import (
    ParamIncierto, monte_carlo_van, sobol_van, break_even,
    valor_informacion_perfecta, construir_eval_van,
    ResultadoMonteCarlo, ResultadoSobol, BreakEven, ValorInformacion,
)

__all__ = [
    'Inputs', 'Resultados', 'PhasePlan', 'Simulador',
    'Variante', 'CatalogoCruce', 'ProyectoReconfig',
    'ROL_BASE', 'ROL_RECONFIG',
    'BeneficioSocial', 'calcular_beneficio',
    'VST_URBANO_VIAJE_2026', 'VST_URBANO_ESPERA_2026',
    'DIAS_LABORALES_AÑO', 'OCUPACION_VEH_DEFAULT',
    'analizar_saturacion', 'analizar_principal', 'balance_lateral_principal',
    'calcular_externalidades', 'Externalidades',
    'CONSUMO_RALENTI_L_H', 'PRECIO_SOCIAL_COMBUSTIBLE_CLP_L',
    'evaluar_horizonte', 'EvaluacionHorizonte',
    'correr_jitter_hcall', 'JitterHCALL',
    'TASA_SOCIAL_DESCUENTO_2026', 'HORIZONTE_SNI_DEFAULT',
    'TASA_CRECIMIENTO_DEMANDA_DEFAULT',
    'microsim_banda', 'microsim_desde_resultados', 'ResultadoMicrosim',
    'analisis_tornado', 'sensibilidad_van_cruce',
    'TornadoResultado', 'SensibilidadParam',
    'Alternativa', 'ComparacionAlternativas',
    'evaluar_alternativas', 'alternativas_estandar', 'evaluar_alternativas_cruce',
    'desglosar_beneficio', 'DesgloseModal', 'BeneficioModo',
    'VST_2026_CLP_H', 'OCUPACION_2026', 'COMPOSICION_TIPICA_CONCEPCION',
    'Riesgo', 'MatrizRiesgos', 'matriz_riesgos_estandar',
    'ParamIncierto', 'monte_carlo_van', 'sobol_van', 'break_even',
    'valor_informacion_perfecta', 'construir_eval_van',
    'ResultadoMonteCarlo', 'ResultadoSobol', 'BreakEven', 'ValorInformacion',
    'AnclaSimulada', 'CruceExtrapolado', 'caracterizar_anclas',
    'extrapolar_cruce', 'estimar_capacidad_pico_ref',
    'ItemCartera', 'CorteTemporal', 'ResultadoCartera', 'evaluar_cartera', 'UF_CLP',
    'ClasificacionCruce', 'clasificar', 'clasificar_catalogo', 'resumen_tipologico',
    'TIPOLOGIAS', 'MODELO_POR_TIPOLOGIA', 'TIPOLOGIAS_CON_BENEFICIO_PROYECTO',
    'EvaluacionIncremental', 'EjeBeneficio', 'evaluar_incremental',
    'construir_ejes_beneficio', 'beneficio_valorizable_total',
    'ocupacion_efectiva_cruce', 'OCUPACION_BUS_DEFAULT',
]
