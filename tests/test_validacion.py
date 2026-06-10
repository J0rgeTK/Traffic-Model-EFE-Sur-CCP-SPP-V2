"""
Test de consistencia del motor de simulacion.
Verifica que el motor, leyendo desde las bases de datos, procese la
demanda de los cruces de control y se mantenga dentro de tolerancia,
protegiendo contra regresiones del modelo.

Ejecutar:  python tests/test_validacion.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datos
from motor_sim import Simulador

# Valores de control esperados para los cruces de verificacion:
CONTROL = {
    'Costa Verde':      {'demanda': 1246.5, 'tol_demanda': 1.0},
    'Diagonal Bio Bio': {'demanda': 4251.6, 'tol_demanda': 1.0},
}


def main() -> int:
    con = datos.conectar()
    fallos = 0
    for cruce, ref in CONTROL.items():
        inp = datos.construir_inputs(con, cruce, campania_id=3, k_dem=1.0)
        res = Simulador(inp).run(mode='corrected')
        dif = abs(res.demanda - ref['demanda'])
        ok = dif <= ref['tol_demanda']
        estado = 'OK' if ok else 'FALLA'
        print(f'[{estado}] {cruce:18s} demanda = {res.demanda:9.2f} veh '
              f'(esperado {ref["demanda"]}, dif {dif:.2f})')
        if not ok:
            fallos += 1
    con.close()
    if fallos:
        print(f'\n{fallos} prueba(s) fallida(s).')
        return 1
    print('\nTodas las pruebas pasaron: el motor mantiene la consistencia esperada.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
