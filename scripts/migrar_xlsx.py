"""
Carga de datos a SQLite (utilidad de linea de comandos)
=======================================================
Carga los datos del corredor a las bases de datos del modelo desde los
archivos fuente de datos (.xlsx):
  1. Antecedentes, aforos vehiculares, eventos HCALL e itinerario.
  2. Programacion semaforica: versiones, planes por cruce/tipo de dia,
     programacion de fases y modelo operacional (fuente de verdad de la
     programacion semaforica).

Uso:  python scripts/migrar_xlsx.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelo_cruces.config import FuenteReferencia
from modelo_cruces.importador import importar_referencia, importar_programacion_v2

RAIZ = Path(__file__).resolve().parent.parent
FUENTES_ORIG = [
    FuenteReferencia(
        ruta=str(RAIZ / 'fuentes' /
                 'Analisis_Cruces_L2_NOREPROG_PREVACIADO_PLAN_DINAMICO_BASE_REAL.xlsx'),
        version='Base real (heredada)',
        campania='Aforos base (NOREPROG)', es_base=True),
    FuenteReferencia(
        ruta=str(RAIZ / 'fuentes' /
                 'Analisis_Cruces_L2_Reprog_Mar9_PREVACIADO_N2_PLAN_DINAMICO_REHECHO.xlsx'),
        version='Reprogramado Mar9 (heredada)',
        campania='Aforos reprog (Mar9)', es_base=False),
]
ARCHIVO_V2 = RAIZ / 'fuentes' / 'base_programacion_actualizacion_modelo_cruces_v2.xlsx'


def main():
    for f in FUENTES_ORIG:
        if not Path(f.ruta).exists():
            raise SystemExit(f'ERROR: falta {Path(f.ruta).name} en fuentes/.')
    if not ARCHIVO_V2.exists():
        raise SystemExit(f'ERROR: falta {ARCHIVO_V2.name} en fuentes/.')

    print('Construyendo bases de datos:')
    importar_referencia(FUENTES_ORIG, RAIZ / 'data', RAIZ / 'data' / 'schema')
    importar_programacion_v2(ARCHIVO_V2, RAIZ / 'data')

    # escenarios de ejemplo a partir del catalogo
    import datos
    from modelo_cruces.catalogo import catalogo_simulable
    con = datos.conectar()
    eid = 0
    for c in catalogo_simulable(con):
        for v in c.variantes:
            eid += 1
            con.execute(
                'INSERT INTO escenarios (escenario_id,nombre,cruce_id,'
                'version_prog_id,campania_id,itinerario_id,k_dem,modo,notas) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                (eid, f'{c.cruce} - {v.rol}', c.cruce_id, v.version_prog_id,
                 1, 1, 1.1, 'corrected', 'Generado desde el catalogo'))
    con.commit()
    con.close()
    print(f'  escenarios.db      : {eid} escenarios desde el catalogo')
    print('Listo. Bases generadas en data/.')


if __name__ == '__main__':
    main()
