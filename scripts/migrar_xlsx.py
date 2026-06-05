"""
Migracion fuente de referencia -> SQLite (CLI de compatibilidad)
=================================================
Combina dos fuentes:
  1. fuente de referencia (Analisis_Cruces_L2_NOREPROG_*.xlsx): BBDD,
     aforos vehiculares, eventos HCALL, itinerario.
  2. Archivo v2 (base_programacion_actualizacion_modelo_cruces_v2.xlsx):
     versiones, planes por cruce/tipo_dia, programacion_fases,
     modelo operacional, declaracion del proyecto. Esta es la FUENTE
     DE VERDAD para todo lo relacionado a programacion semaforica.

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
