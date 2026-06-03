"""
Matriz de riesgos del proyecto
==============================
Inventario estructurado de riesgos tecnicos, operacionales, economicos
e institucionales del proyecto pre-vaciado N2 + reconfiguracion
semaforica. Es un elemento exigido por el SNI / MDSF en proyectos de
inversion publica.

Para cada riesgo se reporta:
  - Categoria (tecnico / operacional / economico / institucional)
  - Descripcion
  - Probabilidad (baja / media / alta)
  - Impacto (bajo / medio / alto)
  - Severidad (P * I) en escala 1-9
  - Mitigacion propuesta
  - Disparador (que indicaria que el riesgo se materializa)
  - Responsable

Categorias de severidad:
  1-2  bajo       seguimiento periodico
  3-4  medio      plan de mitigacion documentado
  5-6  alto       monitoreo activo, plan de contingencia
  7-9  critico    accion correctiva inmediata
"""
from __future__ import annotations
from dataclasses import dataclass, field


NIVEL_NUM = {'baja': 1, 'bajo': 1, 'media': 2, 'medio': 2, 'alta': 3, 'alto': 3}


@dataclass
class Riesgo:
    """Un riesgo identificado."""
    codigo:        str
    categoria:     str        # 'tecnico' | 'operacional' | 'economico' | 'institucional'
    descripcion:   str
    probabilidad:  str        # 'baja' | 'media' | 'alta'
    impacto:       str        # 'bajo' | 'medio' | 'alto'
    mitigacion:    str
    disparador:    str
    responsable:   str

    @property
    def severidad_num(self) -> int:
        return NIVEL_NUM[self.probabilidad] * NIVEL_NUM[self.impacto]

    @property
    def severidad_etiqueta(self) -> str:
        s = self.severidad_num
        if s <= 2: return 'BAJO'
        if s <= 4: return 'MEDIO'
        if s <= 6: return 'ALTO'
        return 'CRITICO'


@dataclass
class MatrizRiesgos:
    proyecto:  str
    riesgos:   list[Riesgo] = field(default_factory=list)

    @property
    def riesgos_ordenados(self) -> list[Riesgo]:
        return sorted(self.riesgos, key=lambda r: -r.severidad_num)

    @property
    def riesgos_criticos(self) -> list[Riesgo]:
        return [r for r in self.riesgos if r.severidad_num >= 7]

    @property
    def riesgos_altos(self) -> list[Riesgo]:
        return [r for r in self.riesgos if 5 <= r.severidad_num <= 6]

    def resumen(self) -> dict:
        return {
            'total':    len(self.riesgos),
            'criticos': sum(1 for r in self.riesgos if r.severidad_num >= 7),
            'altos':    sum(1 for r in self.riesgos if 5 <= r.severidad_num <= 6),
            'medios':   sum(1 for r in self.riesgos if 3 <= r.severidad_num <= 4),
            'bajos':    sum(1 for r in self.riesgos if r.severidad_num <= 2),
        }

    def imprimir(self) -> str:
        lineas = [f'Matriz de riesgos - {self.proyecto}', '']
        r = self.resumen()
        lineas.append(f'  Total: {r["total"]}  '
                       f'(criticos: {r["criticos"]}, altos: {r["altos"]}, '
                       f'medios: {r["medios"]}, bajos: {r["bajos"]})')
        lineas.append('')
        for ri in self.riesgos_ordenados:
            lineas.append(f'  [{ri.severidad_etiqueta:7s}] {ri.codigo} '
                           f'({ri.categoria}): {ri.descripcion}')
            lineas.append(f'             P={ri.probabilidad} I={ri.impacto}  '
                           f'Mitig: {ri.mitigacion}')
        return '\n'.join(lineas)


def matriz_riesgos_estandar(proyecto: str = 'Pre-vaciado N2 + reconfig L2 Biotren'
                            ) -> MatrizRiesgos:
    """Matriz de riesgos identificados para este proyecto especifico."""
    riesgos = [
        # --- TECNICOS ---
        Riesgo('T-01', 'tecnico',
               'Aforos del movimiento principal de Ruta 160 difieren '
               'significativamente del flujo supuesto. Sin medicion real, '
               'el balance neto del proyecto puede invertirse de positivo '
               'a negativo en cruces subsaturados.',
               'alta', 'alto',
               'Campania de aforos direccionales en los 8 cruces RECONFIG '
               'con detector automatico 14 dias continuos antes de '
               'finalizar la formulacion.',
               'Diferencia > 20% entre flujo asumido y aforo en cualquier cruce.',
               'Equipo de aforos / contratista de mediciones'),
        Riesgo('T-02', 'tecnico',
               'Bandas saturadas (x > 1.20) en DBB hora-punta requieren '
               'microsimulacion para validar el beneficio analitico.',
               'media', 'alto',
               'Microsimulacion en SUMO open-source de DBB para la banda '
               '17-20h con calibracion contra cola medida en terreno.',
               'Microsim reporta espera total > 50% distinta de Akcelik.',
               'Equipo de modelacion'),
        Riesgo('T-03', 'tecnico',
               'Factor k_dem = 1.10 esta sin documentar; el revisor SNI '
               'puede exigir reducirlo a 1.0, lo que baja el beneficio.',
               'media', 'medio',
               'Documentar el origen historico de k_dem o eliminarlo. '
               'Si es proyeccion de demanda, modelarlo explicito por '
               'horizonte anual.',
               'Memoria SNI sin justificacion respaldada.',
               'Equipo de modelacion'),
        Riesgo('T-04', 'tecnico',
               'Headway de saturacion h asumido 2.0 s/veh; valor real en '
               'condiciones de Concepcion puede ser 1.8-2.4 s/veh y '
               'altera la capacidad efectiva.',
               'media', 'medio',
               'Medicion de h en terreno (filmacion 1 dia, 200+ vehiculos '
               'descargando cola) en al menos 2 cruces representativos.',
               'Sensibilidad muestra impacto > 25% del VAN.',
               'Equipo de aforos'),
        Riesgo('T-05', 'tecnico',
               'Modelo determinista subestima variabilidad real del flujo '
               'lateral (Poisson asumida; en realidad puede ser sub-Poisson '
               'por pelotones del semaforo aguas arriba).',
               'baja', 'medio',
               'Sensibilidad estocastica con factor I (filtrado upstream) '
               '0.5 a 1.5. Reportar P10-P90.',
               'P90 difiere > 30% del determinista.',
               'Equipo de modelacion'),
        # --- OPERACIONALES ---
        Riesgo('O-01', 'operacional',
               'Coordinacion EFE/Biotren <-> UOCT para envio de senal HCALL '
               'anticipada (pre-vaciado) no esta protocolizada.',
               'media', 'alto',
               'Convenio tripartito EFE-UOCT-GORE antes de la postulacion. '
               'Especificar latencia maxima, protocolo de comunicacion, '
               'responsabilidades.',
               'Sin convenio firmado a 3 meses de la postulacion.',
               'GORE Biobio / Jefatura de proyecto'),
        Riesgo('O-02', 'operacional',
               'Sistema de pre-vaciado depende de AVL/GPS de los trenes; '
               'fallas de comunicacion (5% del tiempo tipico) reducen '
               'beneficio.',
               'media', 'medio',
               'Definir comportamiento por defecto cuando falla la '
               'senal (revertir a operacion actual). Reportar tasa de '
               'disponibilidad esperada en la memoria.',
               'Pruebas piloto muestran > 10% de eventos sin senal.',
               'Contratista del sistema GPS/AVL'),
        Riesgo('O-03', 'operacional',
               'Operadores SCATS pueden deshabilitar pre-vaciado en '
               'planes nocturnos o ante eventos no previstos.',
               'baja', 'bajo',
               'Capacitacion al personal UOCT y procedimiento estandar '
               'de operacion documentado.',
               'Reportes UOCT muestran tiempo de deshabilitacion > 5%.',
               'UOCT / capacitacion'),
        # --- ECONOMICOS ---
        Riesgo('E-01', 'economico',
               'CAPEX puede subir 20-40% por ajustes durante implementacion '
               '(equipos GPS, integracion SCATS, obras civiles menores).',
               'media', 'medio',
               'Reserva de contingencia 15% del CAPEX en el flujo SNI. '
               'Definir alcance contractual cerrado por cruce.',
               'Cotizaciones reales > 20% del CAPEX preliminar.',
               'Equipo de costos / GORE Biobio'),
        Riesgo('E-02', 'economico',
               'Crecimiento real de la demanda vehicular en Ruta 160 puede '
               'ser menor al 2% supuesto (post-pandemia / electromobilidad / '
               'tarificacion futura).',
               'baja', 'medio',
               'Sensibilidad con crecimiento 0-4%. Memoria SNI debe '
               'reportar VAN en escenarios bajo, medio y alto.',
               'Aforos 2026 muestran flujo menor al 2024.',
               'Equipo de modelacion'),
        # --- INSTITUCIONALES ---
        Riesgo('I-01', 'institucional',
               'Devolucion del expediente SNI por aforos insuficientes o '
               'metodologia debilmente respaldada en cruces evaluados.',
               'alta', 'alto',
               'Cerrar todas las brechas tecnicas (aforos, microsimulacion, '
               'documentacion) ANTES de ingresar. Validacion con SECTRA '
               'previo al ingreso al BIP.',
               'Pre-revision SECTRA marca observaciones criticas.',
               'GORE Biobio / Jefatura de proyecto'),
        Riesgo('I-02', 'institucional',
               'Cambio de gobierno o de prioridades sectoriales puede '
               'retrasar 1-2 anos la asignacion presupuestaria.',
               'media', 'medio',
               'Alinear con Plan Maestro de Transporte de Concepcion. '
               'Buscar respaldo de actores locales (municipios, gremios).',
               'Cambio de prioridades en el sector explicitamente.',
               'GORE Biobio'),
        Riesgo('I-03', 'institucional',
               'Cruces con balance neto marginal (Conavicop, Portal SP) '
               'pueden ser observados por el MDSF como sin justificacion '
               'social. El proyecto puede aprobarse parcialmente.',
               'alta', 'medio',
               'Estructurar el proyecto en Fase 1 (cruces con beneficio '
               'claro, ej. solo DBB) y Fase 2 (resto, condicionada a '
               'aforos del principal positivos).',
               'Pre-revision MDSF observa beneficio insuficiente en > 2 cruces.',
               'GORE Biobio / Jefatura de proyecto'),
    ]
    return MatrizRiesgos(proyecto=proyecto, riesgos=riesgos)
