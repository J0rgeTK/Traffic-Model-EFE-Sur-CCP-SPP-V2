"""Pruebas de los validadores de integridad."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datos
from modelo_cruces import validadores as val


def main() -> int:
    con = datos.conectar()
    hs = val.validar_todo(con)
    r = val.resumen(hs)
    for h in hs:
        print(' ', h)
    print(f'errores={r["errores"]} advertencias={r["advertencias"]} ok={r["ok"]}')
    con.close()
    if not r['ok']:
        print('FALLA: hay errores de integridad en las bases.')
        return 1
    print('OK: las bases pasan todas las reglas de integridad.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
