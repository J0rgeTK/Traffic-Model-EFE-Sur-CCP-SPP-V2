"""Prepara insumos CSV procesados para el módulo OD híbrido de Biotren.

Los archivos Excel originales son insumos externos opcionales y no se versionan.
Cuando estén disponibles en data/od_biotren/input/, este script extrae y
homologa las matrices necesarias y genera CSV reproducibles en
 data/od_biotren/processed/ para que la app y el modelo OD puedan ejecutarse
sin depender de binarios .xlsx versionados.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

import od_biotren_hibrido as OD

BASE = Path(__file__).resolve().parent
PROCESSED = OD.OD_PROCESSED


def _stack_matrix(M: pd.DataFrame, value_name: str) -> pd.DataFrame:
    return (
        M.stack()
        .reset_index(name=value_name)
        .rename(columns={"level_0": "origen", "level_1": "destino"})
    )


def preparar_insumos_od_biotren() -> dict[str, Path]:
    """Genera los CSV procesados usados por ``od_biotren_hibrido.py``.

    Requiere los Excel externos originales en ``data/od_biotren/input/``:
    - ``0. Matrices Biotren may_2026.xlsx``
    - ``Consolidado Tarifas EFE Sur 2026.xlsx``
    - ``Libro1.xlsx``
    """
    requeridos = [OD.OD_MAIN, OD.FARE_FILE, OD.DIST_FILE]
    faltantes = [str(p.relative_to(BASE)) for p in requeridos if not p.exists()]
    if faltantes:
        raise FileNotFoundError(
            "Faltan Excel externos para preparar insumos OD Biotren: "
            + ", ".join(faltantes)
            + ". Copie los archivos originales en data/od_biotren/input/ y vuelva a ejecutar "
            + "python preparar_insumos_od_biotren.py"
        )

    PROCESSED.mkdir(parents=True, exist_ok=True)

    mats, validacion, station_order = OD.load_od_matrices(OD.OD_MAIN)
    tarifas = OD.load_tariff_matrices(station_order)
    distancias = OD.load_distance_matrix(station_order)

    orden_df = pd.DataFrame({"orden": range(1, len(station_order) + 1), "estacion": station_order})
    od_rows = []
    bloques_tipo = set(OD.TIPOS_BLOQUES.values())
    for (anio, mes, bloque), M in sorted(mats.items()):
        if bloque not in bloques_tipo:
            continue
        tmp = _stack_matrix(M, "viajes")
        tmp.insert(0, "bloque", bloque)
        tmp.insert(0, "mes", int(mes))
        tmp.insert(0, "anio", int(anio))
        od_rows.append(tmp)
    od_long = pd.concat(od_rows, ignore_index=True)

    tarifa_rows = []
    for tipo, M in tarifas.items():
        tmp = _stack_matrix(M, "tarifa_2026")
        tmp.insert(0, "tipo_pasajero", tipo)
        tarifa_rows.append(tmp)
    tarifas_long = pd.concat(tarifa_rows, ignore_index=True)

    dist_long = _stack_matrix(distancias, "distancia_km")

    archivos = {
        "orden_estaciones": PROCESSED / "orden_estaciones_original.csv",
        "od_historica": PROCESSED / "od_historica_por_tipo_long.csv",
        "tarifas": PROCESSED / "tarifas_2026_por_tipo_long.csv",
        "distancias": PROCESSED / "distancia_biotren_km_long.csv",
        "validacion": PROCESSED / "validacion_extraccion_od.csv",
    }
    orden_df.to_csv(archivos["orden_estaciones"], index=False)
    od_long.to_csv(archivos["od_historica"], index=False)
    tarifas_long.to_csv(archivos["tarifas"], index=False)
    dist_long.to_csv(archivos["distancias"], index=False)
    validacion.to_csv(archivos["validacion"], index=False)
    return archivos


if __name__ == "__main__":
    generados = preparar_insumos_od_biotren()
    print("Insumos OD Biotren procesados generados:")
    for nombre, path in generados.items():
        print(f"- {nombre}: {path.relative_to(BASE)}")
