"""
Test de validación del motor de simulación.
Comprueba que el motor, leyendo desde las bases de datos, reproduce las
cifras del modelo Excel original (modo faithful, k_dem = 1.1).

Ejecutar:  python tests/test_validacion.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datos
from motor_sim import Simulador

# Valores de referencia del Excel (hoja SIM, modo faithful):
REFERENCIA = {
    'Costa Verde':      {'demanda': 1371.2, 'tol_demanda': 1.0},
    'Diagonal Bio Bio': {'demanda': 4676.8, 'tol_demanda': 1.0},
}


def main() -> int:
    con = datos.conectar()
    fallos = 0
    for cruce, ref in REFERENCIA.items():
        inp = datos.construir_inputs(con, cruce, k_dem=1.1)
        res = Simulador(inp).run(mode='faithful')
        dif = abs(res.demanda - ref['demanda'])
        ok = dif <= ref['tol_demanda']
        estado = 'OK' if ok else 'FALLA'
        print(f'[{estado}] {cruce:18s} demanda = {res.demanda:9.2f} veh '
              f'(referencia {ref["demanda"]}, dif {dif:.2f})')
        if not ok:
            fallos += 1
    con.close()
    if fallos:
        print(f'\n{fallos} prueba(s) fallida(s).')
        return 1
    print('\nTodas las pruebas pasaron: el motor reproduce el modelo Excel.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
