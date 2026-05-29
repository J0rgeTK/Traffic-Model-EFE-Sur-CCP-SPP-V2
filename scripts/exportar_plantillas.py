"""
Exporta las bases a la plantilla tabular canónica (CSV planos).
============================================================
La plantilla NO depende de celdas fijas ni fórmulas: son CSV con
encabezados semánticos, validables antes de cargar. Sirve como (a)
formato de carga para nuevas programaciones/campañas y (b) export de
auditoría. Reconstruir las bases desde la plantilla es el importador
canónico (etapa siguiente del plan).

Uso:  python scripts/exportar_plantillas.py
"""
import csv
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datos

RAIZ = Path(__file__).resolve().parent.parent
DEST = RAIZ / 'plantillas'

CONSULTAS = {
    'programaciones': 'SELECT version_prog_id, nombre, fecha, tipo_version, '
                      'fuente, descripcion FROM infra.versiones_programacion',
    'planes_horarios_cruce': 'SELECT version_prog_id, cruce_id, tipo_dia, '
                             'hora_inicio_s, hora_fin_s, plan_id, fuente '
                             'FROM infra.planes_horarios_cruce',
    'fases': 'SELECT version_prog_id, cruce_id, plan_id, fase_id, duracion_s, '
             'entreverde_s, cum_inicio_s, cum_fin_s, es_verde_lateral, '
             'ciclo_s, fase_origen, fuente FROM infra.programacion_fases',
    'modelo_operacional_cruce': 'SELECT cruce_id, tipo_modelo, '
                                'usa_reconfiguracion, version_prog_id, '
                                'descripcion FROM infra.modelo_operacional_cruce',
    'flujos': 'SELECT campania_id, cruce_id, tipo_dia, t_inicio_s, t_fin_s, '
              'flujo_veh_h FROM dem.llegadas_vehiculares',
    'eventos_hcall': 'SELECT itinerario_id, cruce_id, sentido, instante_paso_s, '
                     'hcall_in_s, hcall_out_s FROM dem.eventos_barrera',
    'cruces': 'SELECT cruce_id, nombre, comuna, latitud, longitud, '
              'num_pistas_total, tiene_semaforo, sentido_afectacion '
              'FROM infra.cruces',
    'cruces_reconfiguracion': 'SELECT cruce_id, via_principal, '
                              'codigo_proyecto, comuna_referencia, '
                              'estado_carga, confianza, fuente '
                              'FROM infra.cruces_reconfiguracion',
    'escenarios': 'SELECT escenario_id, nombre, cruce_id, version_prog_id, '
                  'campania_id, itinerario_id, k_dem, modo FROM escenarios',
}


def main():
    DEST.mkdir(exist_ok=True)
    con = datos.conectar()
    for nombre, sql in CONSULTAS.items():
        rows = con.execute(sql).fetchall()
        ruta = DEST / f'{nombre}.csv'
        with ruta.open('w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            if rows:
                w.writerow(rows[0].keys())
                w.writerows(tuple(r) for r in rows)
            else:
                w.writerow(['(sin datos)'])
        print(f'  {ruta.relative_to(RAIZ)}  ({len(rows)} filas)')
    con.close()
    print('Plantillas exportadas en plantillas/.')


if __name__ == '__main__':
    main()
