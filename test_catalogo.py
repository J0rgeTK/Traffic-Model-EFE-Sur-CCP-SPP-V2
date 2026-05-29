"""Pruebas del catálogo de variantes por cruce.

Verifica que:
  - los 8 cruces declarados aparecen con su código de proyecto;
  - los que tienen fases v1 generan dos variantes: base (fase 1) y
    reconfiguración (salto al verde lateral post-HCALL);
  - Masisa y Escuadrón 2 aparecen declarados pero sin variantes;
  - Costa Verde (no declarado) solo tiene la variante base.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datos
from modelo_cruces.modelos import ROL_BASE, ROL_RECONFIG

DECLARADOS = {
    'Los Claveles': '3051', 'Diagonal Bio Bio': '3031', 'Michaihue': '3011',
    'Masisa': '3161', 'Lomas Coloradas': '3181', 'Portal San Pedro': '3191',
    'Conavicop': '3196', 'Escuadron 2': None,
}
SIN_FASES = {'Escuadron 2'}    # Masisa ahora tiene programacion en el archivo v2


def main() -> int:
    con = datos.conectar()
    cat = {c.cruce: c for c in datos.catalogo(con)}
    fallos = 0

    for nom, cod in DECLARADOS.items():
        c = cat.get(nom)
        if c is None or not c.en_proyecto:
            print(f'[FALLA] {nom}: no aparece declarado en el catálogo'); fallos += 1
            continue
        if cod and c.proyecto.codigo_proyecto != cod:
            print(f'[FALLA] {nom}: código {c.proyecto.codigo_proyecto} ≠ {cod}')
            fallos += 1; continue

        if nom in SIN_FASES:
            if c.variantes:
                print(f'[FALLA] {nom}: no debería tener variantes (sin fases)')
                fallos += 1
            else:
                print(f'[OK] {nom:18s} declarado sin programación (correcto)')
            continue

        # Cruces declarados con fases: dos variantes, base y reconfig.
        roles = [v.rol for v in c.variantes]
        if roles != [ROL_BASE, ROL_RECONFIG]:
            print(f'[FALLA] {nom}: variantes={roles}, esperaba [base,reconfig]')
            fallos += 1; continue
        # La variante reconfig debe tener post_hcall_lateral=True.
        if not c.variante(ROL_RECONFIG).post_hcall_lateral:
            print(f'[FALLA] {nom}: reconfig debe tener post_hcall_lateral=True')
            fallos += 1; continue
        print(f'[OK] {nom:18s} cod {cod or "—":>4}  '
              f'base→fase 1, reconfig→verde lateral')

    cv = cat.get('Costa Verde')
    if cv and (cv.en_proyecto or cv.tiene_reconfiguracion):
        print('[FALLA] Costa Verde no debería estar en el proyecto'); fallos += 1
    elif cv and len(cv.variantes) == 1 and cv.variantes[0].rol == ROL_BASE:
        print('[OK] Costa Verde solo con variante base (no declarado)')

    con.close()
    print('\nOK' if not fallos else f'\n{fallos} fallo(s)')
    return 1 if fallos else 0


if __name__ == '__main__':
    raise SystemExit(main())
