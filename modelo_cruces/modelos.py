"""
Modelos tipados del dominio
===========================
Dataclasses que reemplazan los diccionarios sueltos y los nombres
heredados de columnas tabulares por estructuras con nombres semanticos.

Reconfiguracion (segun aclaracion del proyecto):
  - Para TODOS los cruces del proyecto el modelo es:
    Pre-vaciado + HCALL + "Base a fase 1" (reset del ciclo post-HCALL,
    ya implementado en motor.py via las columnas M/AF).
  - Para Diagonal Bio Bio existe ADEMAS una programacion v2 distinta
    de v1: es la unica variante extra de "reconfiguracion" simulable.
  - Para los otros 6 cruces declarados el beneficio del proyecto es la
    diferencia base vs pre-vaciado en una unica corrida con fases v1.
"""
from __future__ import annotations
from dataclasses import dataclass, field

ROL_BASE = 'base'
ROL_RECONFIG = 'reconfiguracion'       # solo aplica donde hay v2 distinta


@dataclass(frozen=True)
class ProyectoReconfig:
    """Declaracion operacional: el cruce esta en el alcance del proyecto."""
    via_principal: str | None
    codigo_proyecto: str | None
    comuna_referencia: str | None
    fuente: str | None = None


@dataclass(frozen=True)
class Variante:
    """Una programacion semaforica aplicable a un cruce."""
    cruce: str
    cruce_id: int
    version_prog_id: int
    version_nombre: str
    rol: str                            # ROL_BASE | ROL_RECONFIG
    tiene_prevaciado: bool
    # Comportamiento post-HCALL:
    #   False -> salta a posición 0 del ciclo (Base a fase 1)
    #   True  -> salta a green_start (Reconfiguración: verde lateral)
    post_hcall_lateral: bool = False

    @property
    def etiqueta(self) -> str:
        base = 'Base' if self.rol == ROL_BASE else 'Reconfiguración'
        return f'{base} + pre-vaciado' if self.tiene_prevaciado else base


@dataclass
class CatalogoCruce:
    """Que escenarios/modelos corresponden a un cruce."""
    cruce: str
    cruce_id: int
    comuna: str | None
    simulable: bool
    variantes: list[Variante] = field(default_factory=list)
    proyecto: ProyectoReconfig | None = None

    @property
    def en_proyecto(self) -> bool:
        return self.proyecto is not None

    @property
    def tiene_reconfiguracion(self) -> bool:
        return any(v.rol == ROL_RECONFIG for v in self.variantes)

    @property
    def etiqueta_modelo(self) -> str:
        """Resumen legible del modelo aplicable."""
        if not self.variantes:
            return 'declarado (sin programación cargada)'
        partes = ['base']
        if self.tiene_reconfiguracion:
            partes.append('reconfiguración')
        if any(v.tiene_prevaciado for v in self.variantes):
            partes.append('pre-vaciado')
        return ' + '.join(partes)

    def variante(self, rol: str) -> Variante | None:
        for v in self.variantes:
            if v.rol == rol:
                return v
        return None


# --------------------------------------------------------------------- #
#  Insumos canonicos (para la plantilla tabular independiente de la fuente)
# --------------------------------------------------------------------- #
@dataclass
class FaseCanonica:
    cruce: str
    version: str
    tipo_dia: str
    plan_id: int
    fase_id: int
    duracion_s: int
    entreverde_s: int
    cum_inicio_s: int
    cum_fin_s: int
    es_verde_lateral: bool
    ciclo_s: int


@dataclass
class FlujoCanonico:
    cruce: str
    campania: str
    movimiento: str
    tipo_dia: str
    t_inicio_s: int
    t_fin_s: int
    flujo_veh_h: float
    fuente: str | None = None
    calidad: str | None = None


@dataclass
class EventoBarreraCanonico:
    cruce: str
    itinerario: str
    servicio: str | None
    sentido: str | None
    hcall_in_s: int
    hcall_out_s: int
    fuente: str | None = None
    metodo: str | None = None
    confianza: str | None = None
