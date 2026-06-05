"""
Evaluacion incremental SBO vs proyecto GPS-SCATS
================================================
Estructura la evaluacion en el marco metodologico correcto del SNI, tal
como lo define el ITE del proyecto:

  Situacion actual         : semaforo reinicia en Fase A (verde al
                             principal que no acumulo cola). Es el estado
                             previo, NO la base de comparacion.

  Situacion Sin Proyecto   : reconfiguracion semaforica ya implementada
  (SBO, Alternativa 0)       (Iniciativa 1): verde inmediato a laterales
                             tras el paso del tren. Bajo costo (~500 UF),
                             sin inversion del presente proyecto.

  Situacion Con Proyecto   : reconfiguracion + integracion GPS-SCATS
                             (SCATS Priority Engine + AVL + pre-vaciado
                             predictivo).

El BENEFICIO ATRIBUIBLE AL PROYECTO es el INCREMENTAL de la situacion con
proyecto sobre la SBO, NO sobre la situacion actual. Atribuirle al
proyecto el beneficio de la reconfiguracion (que es SBO y gratis) lo
sobreestima groseramente; el propio ITE lo advierte y deja ese calculo
pendiente. Este modulo lo realiza.

CORRECCION METODOLOGICA IMPORTANTE respecto a versiones previas del
modelo: el "costo en el movimiento principal" (Ruta 160) NO se imputa al
proyecto incremental. Razon: el reparto de verde del principal lo
modifica la reconfiguracion (SBO), no el GPS. Ademas, el verde del
principal esta sobre-asignado en la configuracion actual (el principal no
acumula cola durante el paso del tren), de modo que reasignar parte de
ese verde excedente al lateral no genera un costo real significativo. El
proyecto GPS solo anticipa el pre-vaciado y elimina segundos muertos de
sincronizacion; no recorta verde necesario del principal.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class EjeBeneficio:
    """Un eje de beneficio del proyecto, valorizable o cualitativo."""
    nombre: str
    tipo: str                 # 'directo' | 'indirecto' | 'cualitativo'
    valorizable: bool
    beneficio_anual_clp: float
    descripcion: str
    confianza: str            # 'alta' | 'media' | 'baja'


@dataclass
class EvaluacionIncremental:
    """Descomposicion del beneficio en el marco SBO/proyecto."""
    cruce: str
    # Esperas (veh*h/dia)
    espera_actual: float          # situacion previa (Fase A)
    espera_sbo: float             # reconfiguracion (Iniciativa 1)
    espera_proyecto: float        # reconfiguracion + GPS
    # Ahorros
    ahorro_reconfiguracion: float # actual - sbo  (atribuible a Iniciativa 1, gratis)
    ahorro_gps_incremental: float # sbo - proyecto (atribuible al proyecto)
    # Proporcion
    fraccion_gps: float           # ahorro_gps / (ahorro_reconfig + ahorro_gps)

    @property
    def es_marco_correcto(self) -> bool:
        """El beneficio del proyecto es solo el incremental GPS."""
        return True


def evaluar_incremental(espera_actual: float, espera_sbo: float,
                        espera_proyecto: float, cruce: str = '') -> EvaluacionIncremental:
    """Descompone el beneficio entre reconfiguracion (SBO) y GPS (proyecto).

    Args:
        espera_actual: veh*h/dia con el semaforo reiniciando en Fase A.
        espera_sbo: veh*h/dia con reconfiguracion (verde inmediato lateral).
        espera_proyecto: veh*h/dia con reconfiguracion + pre-vaciado GPS.
    """
    ahorro_reconfig = espera_actual - espera_sbo
    ahorro_gps = espera_sbo - espera_proyecto
    total = ahorro_reconfig + ahorro_gps
    frac = ahorro_gps / total if total > 0 else 0.0
    return EvaluacionIncremental(
        cruce=cruce, espera_actual=espera_actual, espera_sbo=espera_sbo,
        espera_proyecto=espera_proyecto,
        ahorro_reconfiguracion=ahorro_reconfig,
        ahorro_gps_incremental=ahorro_gps, fraccion_gps=frac,
    )


# ----------------------------------------------------------------------
#  Ejes de beneficio del proyecto reformulado
# ----------------------------------------------------------------------
def construir_ejes_beneficio(
        ahorro_gps_anual_clp: float,
        beneficio_seguridad_anual_clp: float = 0,
        beneficio_logistica_anual_clp: float = 0,
        beneficio_confiabilidad_anual_clp: float = 0,
        ) -> list[EjeBeneficio]:
    """Arma los ejes de beneficio del proyecto en el marco reformulado.

    El proyecto NO debe sostenerse solo en el ahorro de tiempo incremental
    (que es modesto frente a la reconfiguracion). Su caso se construye
    sobre varios ejes, varios de ellos de alto valor estrategico aunque no
    todos plenamente valorizables a nivel de perfil.
    """
    ejes = [
        EjeBeneficio(
            'Ahorro de tiempo incremental (pre-vaciado GPS)', 'directo', True,
            ahorro_gps_anual_clp,
            'Reduccion adicional de espera sobre la reconfiguracion: '
            'anticipacion del despeje y eliminacion de segundos muertos de '
            'sincronizacion. Valorizado con VST de espera (MDS).', 'media'),
        EjeBeneficio(
            'Seguridad operacional (Zero Density)', 'indirecto',
            beneficio_seguridad_anual_clp > 0, beneficio_seguridad_anual_clp,
            'Pre-vaciado evacua la zona de peligro antes del descenso de '
            'barrera. Reduce colisiones vehiculo-barrera (costo recuperable '
            'EFE) y el riesgo de colision vehiculo-tren. Valorizable '
            'parcialmente con costos de reposicion y precio social de '
            'accidentes.', 'media'),
        EjeBeneficio(
            'Confiabilidad y regularidad del transporte publico', 'indirecto',
            beneficio_confiabilidad_anual_clp > 0,
            beneficio_confiabilidad_anual_clp,
            'La operacion predictiva reduce la variabilidad del tiempo de '
            'viaje. Beneficia especialmente a buses y taxibuses (alta '
            'ocupacion). Valorizable con penalizacion de variabilidad.',
            'baja'),
        EjeBeneficio(
            'Optimizacion logistica de carga', 'indirecto',
            beneficio_logistica_anual_clp > 0, beneficio_logistica_anual_clp,
            'Coordinacion de ventanas para la flota de carga hacia los '
            'puertos de Coronel, San Vicente y Lirquen. Reduce costos '
            'operacionales de exportacion.', 'baja'),
        EjeBeneficio(
            'Habilitador de mayor frecuencia ferroviaria', 'cualitativo',
            False, 0,
            'BENEFICIO ESTRATEGICO CENTRAL. Sin integracion, aumentar la '
            'frecuencia del Biotren (objetivo EFE, habilitado por el Nuevo '
            'Puente Biobio) multiplicaria las interrupciones y la '
            'resistencia social. Con integracion, el aumento de frecuencia '
            'es absorbible sin degradar la vialidad. El proyecto es la '
            'condicion habilitante para escalar el servicio ferroviario.',
            'alta'),
        EjeBeneficio(
            'Tunel verde / coordinacion de corredor', 'cualitativo',
            False, 0,
            'El tren con GPS (ETA predecible) actua como metering natural '
            'que ordena el flujo del corredor. El escenario "acoplado" del '
            'SPE coordina cruces consecutivos (<150 m), generando olas '
            'verdes sincronizadas con el paso del tren. Beneficio de red '
            'que emerge a escala.', 'media'),
        EjeBeneficio(
            'Integracion institucional Biotren-ciudad', 'cualitativo',
            False, 0,
            'Primer canal de comunicacion en tiempo real entre el operador '
            'ferroviario (EFE) y la gestion semaforica (UOCT). Sienta las '
            'bases de una planificacion multimodal integrada. Alineado con '
            'la ERD Biobio (ciudades inteligentes, multimodalidad).', 'alta'),
    ]
    return ejes


def beneficio_valorizable_total(ejes: list[EjeBeneficio]) -> float:
    return sum(e.beneficio_anual_clp for e in ejes if e.valorizable)
