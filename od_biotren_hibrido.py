"""
od_biotren_hibrido.py

Módulo de distribución espacial OD para Biotren integrado al modelo mensual de afluencia.

Enfoque implementado:
- El modelo mensual de afluencia estima la demanda total de Biotren.
- Este módulo distribuye esa demanda mensual por tipo de tarjeta y pares Origen-Destino usando matrices históricas mensuales.
- La distribución por línea OD usa MOD histórica atribuible para `L1`, `L2` y `L1-L2`, manteniendo `No clasificado` como control.
- El modelo gravitacional no reemplaza la matriz histórica: se usa como corrección parcial y capa de sensibilidad espacial.
- El balance final se realiza con IPF/Furness para conservar producciones y atracciones históricas escaladas.
- Las matrices exportadas preservan el orden original de estaciones del archivo OD principal.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import math
import re
import unicodedata
from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA = BASE_DIR / "data"
OUT = BASE_DIR / "outputs"
OD_INPUT = DATA / "od_biotren" / "input"
OD_PROCESSED = DATA / "od_biotren" / "processed"
TARIFAS_BIOTREN = DATA / "tarifas_biotren"
OD_OUT = OUT / "od_biotren_hibrido"
OD_OUT.mkdir(parents=True, exist_ok=True)

OD_MAIN = OD_INPUT / "0. Matrices Biotren may_2026.xlsx"
OD_MAR = OD_INPUT / "0. Matrices Biotren mar_2026.xlsx"
OD_ABR = OD_INPUT / "0. Matrices Biotren abr_2026.xlsx"
DIST_FILE = OD_INPUT / "Libro1.xlsx"
FARE_FILE = OD_INPUT / "Consolidado Tarifas EFE Sur 2026.xlsx"

PROCESSED_FILES = {
    "orden_estaciones": OD_PROCESSED / "orden_estaciones_original.csv",
    "od_historica": OD_PROCESSED / "od_historica_por_tipo_long.csv",
    "od_historica_tipo_tarjeta": OD_PROCESSED / "od_historica_tipo_tarjeta_long.csv",
    "participacion_mensual_tipo_tarjeta": OD_PROCESSED / "participacion_mensual_tipo_tarjeta.csv",
    "participacion_od_tipo_tarjeta": OD_PROCESSED / "participacion_od_tipo_tarjeta_mensual.csv",
    "mapeo_estacion_linea_biotren": OD_PROCESSED / "mapeo_estacion_linea_biotren.csv",
    "mapeo_tipo_tarjeta": OD_PROCESSED / "mapeo_tipo_tarjeta.csv",
    "base_subsidio_referencial": OD_PROCESSED / "base_subsidio_referencial_historica_long.csv",
    "tarifas": OD_PROCESSED / "tarifas_2026_por_tipo_long.csv",
    "distancias": OD_PROCESSED / "distancia_biotren_km_long.csv",
    "tarifa_estudiante_bt_sin_subsidio": TARIFAS_BIOTREN / "tarifa_estudiante_bt_sin_subsidio_long.csv",
    "parametros_subsidio_biotren": TARIFAS_BIOTREN / "parametros_subsidio_biotren.csv",
    "validacion": OD_PROCESSED / "validacion_extraccion_od.csv",
}

TIPOS_BLOQUES = {
    "Normal": "T. Monedero",
    "Estudiante": "T. Estudiante",
    "Adulto Mayor": "T. Tercera Edad",
}
BLOQUE_TOTAL = "Total Mes Tarjetas"
TIPOS = list(TIPOS_BLOQUES.keys())
TIPOS_TARJETA_ESPERADOS = [
    "monedero",
    "media_superior",
    "adulto_mayor",
    "estudiante_basica",
    "discapacitado",
    "funcionario_normal",
    "funcionario_especial",
    "convenio_colectivo",
]

LINEAS_BASE_BIOTREN_VALIDAS = {"L1", "L2", "L1_L2", "SIN_CLASIFICAR"}
CLASIFICACIONES_OD_LINEA_VALIDAS = {"L1", "L2", "L1-L2", "No clasificado"}
TARIFA_APLICABLE_A_TIPO_PASAJERO = {
    "normal_adulto": "Normal",
    "estudiante": "Estudiante",
    "adulto_mayor": "Adulto Mayor",
    "cero": None,
}

# Resultado de la calibración gravitacional previa. Se mantiene como parámetro de
# sensibilidad, no como distribuidor final puro.
ALPHA_TARIFA = 0.75
BETA_DISTANCIA = 0.25
LAMBDA = 0.05
FUNCION_IMPEDANCIA = "exponencial"
PESO_HISTORICO = {"Normal": 0.80, "Estudiante": 0.85, "Adulto Mayor": 0.85}
PESO_GRAVITACIONAL = {k: 1.0 - v for k, v in PESO_HISTORICO.items()}

MONTHS = {
    "ene": 1, "enero": 1, "feb": 2, "febrero": 2, "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4, "may": 5, "mayo": 5, "jun": 6, "junio": 6,
    "jul": 7, "julio": 7, "ago": 8, "agos": 8, "agosto": 8,
    "sep": 9, "sept": 9, "septiembre": 9, "oct": 10, "octubre": 10,
    "nov": 11, "noviembre": 11, "dic": 12, "diciembre": 12,
}


# ---------------------------------------------------------------------------
# Normalización y homologación
# ---------------------------------------------------------------------------

def strip_accents(s) -> str:
    s = "" if s is None else str(s).strip()
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def key(s) -> str:
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


MAP_ESTACIONES = {
    "hualqui": "Hualqui",
    "la leonera": "La Leonera",
    "leonera": "La Leonera",
    "valle del sol": "La Leonera",
    "manquimavida": "Manquimávida",
    "pedro medina": "Pedro Medina",
    "chiguayante": "Chiguayante",
    "concepcion": "Concepción",
    "mall": "Concepción Centro",
    "concepcion centro": "Concepción Centro",
    "lorenzo arenas": "Lorenzo Arenas",
    "utfsm": "UTFSM",
    "los condores": "Los Cóndores",
    "higueras": "Higueras",
    "arenal": "El Arenal",
    "el arenal": "El Arenal",
    "mercado": "Mercado",
    "mercado de thno": "Mercado",
    "juan pablo ii": "Juan Pablo II",
    "diagonal biobio": "Diagonal Biobío",
    "diagonal bio bio": "Diagonal Biobío",
    "alborada": "Alborada",
    "costa mar": "Costa Mar",
    "el parque": "El Parque",
    "megacentro": "El Parque",
    "lomas coloradas": "Lomas Coloradas",
    "raul silva h": "C. Raúl Silva H.",
    "c raul silva h": "C. Raúl Silva H.",
    "hito galvarino": "Hito Galvarino",
    "los canelos": "Los Canelos",
    "huinca": "Huinca",
    "cristo redentor": "Cristo Redentor",
    "laguna quinenco": "Laguna Quiñenco",
    "lag quinenco": "Laguna Quiñenco",
    "lag quiñenco": "Laguna Quiñenco",
    "lag qui nenco": "Laguna Quiñenco",
    "intermodal coronel": "Intermodal Coronel",
    "coronel": "Intermodal Coronel",
    "pasajero lota": "Pasajero Lota",
    "lota": "Pasajero Lota",
    "total": "Total",
    "estaciones": "Estaciones",
}


def canon(s) -> str:
    kk = key(s)
    return MAP_ESTACIONES.get(kk, str(s).strip() if s is not None and not pd.isna(s) else "")


def num(x) -> float:
    if pd.isna(x) or x == "":
        return 0.0
    if isinstance(x, (int, float, np.number)):
        return float(x)
    try:
        return float(str(x).replace(".", "").replace(",", "."))
    except Exception:
        return 0.0


def writable_array(obj, dtype=float) -> np.ndarray:
    """Devuelve una copia NumPy contigua y escribible.

    Streamlit y algunos backends de Pandas/Arrow pueden entregar vistas de
    arreglos no escribibles cuando se usan caches. El módulo OD modifica
    matrices intermedias, por ejemplo para amortiguar la diagonal antes del
    balance IPF; por ello se fuerza una copia editable en todos los puntos
    críticos.
    """
    arr = np.array(obj, dtype=dtype, copy=True)
    arr = np.ascontiguousarray(arr)
    if not arr.flags.writeable:
        arr = arr.copy()
    return arr


def sheet_month(name: str) -> Tuple[int, int] | None:
    kk = key(name)
    if any(bad in kk for bad in ["resumen", "hoja", "supuesto", "jun 2 0"]):
        return None
    y = re.search(r"(20\d{2})", kk)
    if not y:
        return None
    for tok, m in MONTHS.items():
        if re.search(rf"\b{tok}\b", kk):
            return int(y.group(1)), m
    return None


# ---------------------------------------------------------------------------
# Lectura de matrices OD observadas preservando orden original
# ---------------------------------------------------------------------------

def _find_block_position(values: np.ndarray, block: str) -> tuple[int, int] | None:
    target = key(block)
    for r in range(values.shape[0]):
        for c in range(min(values.shape[1], 80)):
            if pd.notna(values[r, c]) and target in key(values[r, c]):
                return r, c
    return None


def extract_od_block(df: pd.DataFrame, block: str, station_order: list[str] | None = None) -> pd.DataFrame | None:
    vals = df.values
    pos = _find_block_position(vals, block)
    if not pos:
        return None
    header_row = station_col = None
    for rr in range(pos[0] + 1, min(pos[0] + 8, vals.shape[0])):
        for cc in range(vals.shape[1]):
            if pd.notna(vals[rr, cc]) and key(vals[rr, cc]) == "estaciones":
                header_row = rr
                station_col = cc
                break
        if header_row is not None:
            break
    if header_row is None:
        return None

    dest, cols = [], []
    for c in range(station_col + 1, vals.shape[1]):
        if pd.isna(vals[header_row, c]):
            break
        cv = canon(vals[header_row, c])
        if cv == "Total":
            break
        dest.append(cv)
        cols.append(c)

    rows, data = [], []
    for r in range(header_row + 1, vals.shape[0]):
        if pd.isna(vals[r, station_col]):
            continue
        ro = canon(vals[r, station_col])
        if ro == "Total":
            break
        if ro in ["Estaciones", ""]:
            continue
        rows.append(ro)
        data.append([num(vals[r, c]) for c in cols])

    if not rows or not dest:
        return None

    M = pd.DataFrame(data, index=rows, columns=dest)
    # Se preserva el primer orden observado. Si existen duplicados luego de
    # homologar nombres, se consolidan sin reordenar alfabéticamente.
    M = M.groupby(level=0, sort=False).sum()
    M = M.T.groupby(level=0, sort=False).sum().T

    if station_order is None:
        order = []
        for x in list(rows) + list(dest):
            if x not in order and x not in ["Total", "Estaciones", ""]:
                order.append(x)
    else:
        order = list(station_order)

    M = M.reindex(index=order, columns=order, fill_value=0.0).astype(float)
    return M


def extract_original_station_order(path: Path = OD_MAIN, sheet_name: str = "Mayo 2026") -> list[str]:
    df = pd.read_excel(path, sheet_name=sheet_name, header=None, engine="openpyxl")
    M = extract_od_block(df, BLOQUE_TOTAL, station_order=None)
    if M is None:
        raise ValueError("No fue posible extraer el orden original de estaciones desde el bloque Total Mes Tarjetas.")
    return list(M.index)


def load_od_matrices(path: Path = OD_MAIN, blocks: Iterable[str] | None = None, station_order: list[str] | None = None):
    if blocks is None:
        blocks = list(TIPOS_BLOQUES.values()) + [BLOQUE_TOTAL]
    if station_order is None:
        station_order = extract_original_station_order(path)
    xls = pd.ExcelFile(path)
    mats: dict[tuple[int, int, str], pd.DataFrame] = {}
    records = []
    for sheet in xls.sheet_names:
        sm = sheet_month(sheet)
        if not sm:
            continue
        df = pd.read_excel(path, sheet_name=sheet, header=None, engine="openpyxl")
        for block in blocks:
            M = extract_od_block(df, block, station_order=station_order)
            if M is None:
                continue
            mats[(sm[0], sm[1], block)] = M
            records.append({
                "archivo": path.name,
                "hoja": sheet,
                "anio": sm[0],
                "mes": sm[1],
                "bloque": block,
                "n_estaciones": len(station_order),
                "total_viajes": float(M.to_numpy().sum()),
            })
    return mats, pd.DataFrame(records), station_order


# ---------------------------------------------------------------------------
# Lectura de insumos CSV procesados
# ---------------------------------------------------------------------------

def insumos_procesados_faltantes() -> list[Path]:
    return [path for path in PROCESSED_FILES.values() if not path.exists()]


def _error_insumos_procesados(faltantes: list[Path]) -> FileNotFoundError:
    rel = [str(p.relative_to(BASE_DIR)) for p in faltantes]
    return FileNotFoundError(
        "Faltan insumos OD Biotren procesados en CSV: "
        + ", ".join(rel)
        + ". Ejecute `python preparar_insumos_od_biotren.py` con los Excel originales "
        + "disponibles en data/od_biotren/input/. Los Excel son insumos externos "
        + "opcionales y no se versionan."
    )


def _matrix_from_long(df: pd.DataFrame, value_col: str, station_order: list[str]) -> pd.DataFrame:
    M = df.pivot_table(index="origen", columns="destino", values=value_col, aggfunc="sum", fill_value=0.0)
    return M.reindex(index=station_order, columns=station_order, fill_value=0.0).astype(float)


def load_processed_inputs():
    faltantes = insumos_procesados_faltantes()
    if faltantes:
        raise _error_insumos_procesados(faltantes)

    orden = pd.read_csv(PROCESSED_FILES["orden_estaciones"])
    orden = orden.sort_values("orden")
    station_order = orden["estacion"].astype(str).tolist()

    od_long = pd.read_csv(PROCESSED_FILES["od_historica"])
    mats: dict[tuple[int, int, str], pd.DataFrame] = {}
    for (anio, mes, bloque), g in od_long.groupby(["anio", "mes", "bloque"], sort=False):
        mats[(int(anio), int(mes), str(bloque))] = _matrix_from_long(g, "viajes", station_order)

    tarifas_long = pd.read_csv(PROCESSED_FILES["tarifas"])
    fares = {
        str(tipo): _matrix_from_long(g, "tarifa_2026", station_order)
        for tipo, g in tarifas_long.groupby("tipo_pasajero", sort=False)
    }
    missing_fares = [tipo for tipo in TIPOS if tipo not in fares]
    if missing_fares:
        raise ValueError(f"Faltan tarifas procesadas para tipos de pasajero: {missing_fares}")

    dist_long = pd.read_csv(PROCESSED_FILES["distancias"])
    dist = _matrix_from_long(dist_long, "distancia_km", station_order)
    validation = pd.read_csv(PROCESSED_FILES["validacion"])
    return mats, validation, station_order, fares, dist


def load_card_type_processed_inputs() -> dict[str, pd.DataFrame | list[str]]:
    """Carga los CSV procesados de OD Biotren por tipo de tarjeta.

    Esta función sólo expone y valida la nueva estructura granular de insumos.
    No participa aún en la distribución OD final ni modifica la proyección
    mensual total de Biotren.
    """
    required = [
        "orden_estaciones",
        "od_historica_tipo_tarjeta",
        "participacion_mensual_tipo_tarjeta",
        "participacion_od_tipo_tarjeta",
        "mapeo_tipo_tarjeta",
        "tarifas",
        "base_subsidio_referencial",
    ]
    faltantes = [PROCESSED_FILES[k] for k in required if not PROCESSED_FILES[k].exists()]
    if faltantes:
        raise _error_insumos_procesados(faltantes)

    orden = pd.read_csv(PROCESSED_FILES["orden_estaciones"]).sort_values("orden")
    station_order = orden["estacion"].astype(str).tolist()
    return {
        "station_order": station_order,
        "orden_estaciones": orden,
        "od_historica_tipo_tarjeta": pd.read_csv(PROCESSED_FILES["od_historica_tipo_tarjeta"]),
        "participacion_mensual_tipo_tarjeta": pd.read_csv(PROCESSED_FILES["participacion_mensual_tipo_tarjeta"]),
        "participacion_od_tipo_tarjeta": pd.read_csv(PROCESSED_FILES["participacion_od_tipo_tarjeta"]),
        "mapeo_tipo_tarjeta": pd.read_csv(PROCESSED_FILES["mapeo_tipo_tarjeta"]),
        "tarifas": pd.read_csv(PROCESSED_FILES["tarifas"]),
        "base_subsidio_referencial": pd.read_csv(PROCESSED_FILES["base_subsidio_referencial"]),
    }


def cargar_mapeo_estacion_linea(path: Path | None = None) -> pd.DataFrame:
    """Carga el mapeo versionado de estaciones Biotren a línea base."""
    mapeo_path = path if path is not None else PROCESSED_FILES["mapeo_estacion_linea_biotren"]
    mapeo = pd.read_csv(mapeo_path)
    required = {"estacion", "linea_base", "es_estacion_comun", "observacion"}
    faltantes = required - set(mapeo.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas en mapeo estación-línea: {sorted(faltantes)}")
    mapeo = mapeo.copy()
    mapeo["estacion"] = mapeo["estacion"].astype(str)
    mapeo["estacion_canon"] = mapeo["estacion"].map(canon)
    mapeo["linea_base"] = mapeo["linea_base"].astype(str)
    mapeo["es_estacion_comun"] = mapeo["es_estacion_comun"].astype(int)
    return mapeo


def validar_estaciones_od_en_mapeo(od: pd.DataFrame, mapeo: pd.DataFrame | None = None) -> list[str]:
    """Retorna estaciones OD sin registro en el mapeo estación-línea."""
    mapeo = cargar_mapeo_estacion_linea() if mapeo is None else mapeo.copy()
    estaciones_mapeo = set(mapeo["estacion_canon"] if "estacion_canon" in mapeo.columns else mapeo["estacion"].map(canon))
    estaciones_od = set(pd.concat([od["origen"], od["destino"]]).map(canon).astype(str))
    return sorted(estaciones_od - estaciones_mapeo)


def clasificar_par_od_linea(origen_linea: str, destino_linea: str) -> str:
    """Clasifica un par OD según la línea base de origen y destino."""
    if "SIN_CLASIFICAR" in {origen_linea, destino_linea}:
        return "No clasificado"
    if origen_linea == "L1_L2" and destino_linea == "L1_L2":
        return "No clasificado"
    if origen_linea == destino_linea:
        return origen_linea if origen_linea in {"L1", "L2"} else "No clasificado"
    if origen_linea == "L1_L2" and destino_linea in {"L1", "L2"}:
        return destino_linea
    if destino_linea == "L1_L2" and origen_linea in {"L1", "L2"}:
        return origen_linea
    if {origen_linea, destino_linea} == {"L1", "L2"}:
        return "L1-L2"
    return "No clasificado"


def clasificar_od_por_linea(od: pd.DataFrame, mapeo: pd.DataFrame | None = None) -> pd.DataFrame:
    """Agrega la clasificación L1/L2/L1-L2 a cada registro OD sin alterar viajes."""
    mapeo = cargar_mapeo_estacion_linea() if mapeo is None else mapeo.copy()
    if "estacion_canon" not in mapeo.columns:
        mapeo["estacion_canon"] = mapeo["estacion"].map(canon)
    faltantes = validar_estaciones_od_en_mapeo(od, mapeo)
    if faltantes:
        raise ValueError(f"Estaciones OD sin registro en mapeo estación-línea: {faltantes}")
    linea_por_estacion = mapeo.set_index("estacion_canon")["linea_base"].to_dict()
    out = od.copy()
    out["origen_canon"] = out["origen"].map(canon)
    out["destino_canon"] = out["destino"].map(canon)
    out["linea_origen"] = out["origen_canon"].map(linea_por_estacion).fillna("SIN_CLASIFICAR")
    out["linea_destino"] = out["destino_canon"].map(linea_por_estacion).fillna("SIN_CLASIFICAR")
    out["clasificacion_linea_od"] = [
        clasificar_par_od_linea(o, d)
        for o, d in zip(out["linea_origen"], out["linea_destino"])
    ]
    return out


def motivo_no_clasificado_od(linea_origen: str, linea_destino: str, origen: str, destino: str) -> str:
    """Identifica el motivo probable de un par OD No clasificado."""
    if "SIN_CLASIFICAR" in {linea_origen, linea_destino}:
        return "estacion_sin_clasificar"
    if linea_origen == "L1_L2" and linea_destino == "L1_L2":
        return "estacion_comun_a_estacion_comun"
    if canon(origen) == canon(destino):
        return "diagonal"
    if clasificar_par_od_linea(linea_origen, linea_destino) == "No clasificado":
        return "regla_no_definida"
    return "otro"


def resumir_od_no_clasificada(od: pd.DataFrame, mapeo: pd.DataFrame | None = None) -> pd.DataFrame:
    """Resume pares OD clasificados como No clasificado, agregados por origen-destino."""
    clasificada = clasificar_od_por_linea(od, mapeo)
    no_clasificada = clasificada[clasificada["clasificacion_linea_od"] == "No clasificado"].copy()
    total_od = float(clasificada["viajes_observados"].sum())
    total_no_clasificado = float(no_clasificada["viajes_observados"].sum())
    if no_clasificada.empty:
        return pd.DataFrame(columns=[
            "origen",
            "destino",
            "viajes_observados_totales",
            "porcentaje_sobre_total_no_clasificado",
            "porcentaje_sobre_total_od_historico",
            "motivo_probable",
        ])
    no_clasificada["motivo_probable"] = [
        motivo_no_clasificado_od(lo, ld, o, d)
        for lo, ld, o, d in zip(
            no_clasificada["linea_origen"],
            no_clasificada["linea_destino"],
            no_clasificada["origen"],
            no_clasificada["destino"],
        )
    ]
    resumen = no_clasificada.groupby(["origen", "destino", "motivo_probable"], as_index=False).agg(
        viajes_observados_totales=("viajes_observados", "sum"),
    )
    resumen["porcentaje_sobre_total_no_clasificado"] = (
        resumen["viajes_observados_totales"] / total_no_clasificado if total_no_clasificado else 0.0
    )
    resumen["porcentaje_sobre_total_od_historico"] = (
        resumen["viajes_observados_totales"] / total_od if total_od else 0.0
    )
    return resumen.sort_values("viajes_observados_totales", ascending=False).reset_index(drop=True)


def distribuir_proyeccion_biotren_por_linea_mod(serie_biotren: pd.Series | dict) -> pd.DataFrame:
    """Distribuye la proyección mensual total de Biotren por línea OD atribuible.

    El total mensual proviene del modelo temporal. La MOD histórica sólo aporta
    participaciones mensuales para las categorías estándar `L1`, `L2` y
    `L1-L2`; los viajes `No clasificado` se mantienen como control diagnóstico
    y no reciben proyección estándar.
    """
    serie = pd.Series(serie_biotren, dtype=float) if isinstance(serie_biotren, dict) else serie_biotren.astype(float).copy()
    od = pd.read_csv(PROCESSED_FILES["od_historica_tipo_tarjeta"])
    clasificada = clasificar_od_por_linea(od, cargar_mapeo_estacion_linea())
    viajes_col = "viajes_observados"

    base = clasificada.groupby(["mes", "clasificacion_linea_od"], as_index=False)[viajes_col].sum()
    atribuible = base[base["clasificacion_linea_od"].isin(["L1", "L2", "L1-L2"])].copy()
    no_clasificado = (
        base[base["clasificacion_linea_od"].eq("No clasificado")]
        .set_index("mes")[viajes_col]
        .to_dict()
    )
    total_atribuible_mes = atribuible.groupby("mes")[viajes_col].sum().rename("total_atribuible_mes")
    atribuible = atribuible.merge(total_atribuible_mes, on="mes", how="left")
    atribuible["participacion_linea_mes"] = np.where(
        atribuible["total_atribuible_mes"] > 0,
        atribuible[viajes_col] / atribuible["total_atribuible_mes"],
        0.0,
    )

    rows = []
    for periodo, total_mes in serie.items():
        mes = int(str(periodo)[-2:])
        mes_base = atribuible[atribuible["mes"].astype(int).eq(mes)].copy()
        for linea in ["L1", "L2", "L1-L2"]:
            fila = mes_base[mes_base["clasificacion_linea_od"].eq(linea)]
            participacion = float(fila["participacion_linea_mes"].sum()) if not fila.empty else 0.0
            viajes_obs = float(fila[viajes_col].sum()) if not fila.empty else 0.0
            total_atribuible = float(fila["total_atribuible_mes"].max()) if not fila.empty else 0.0
            rows.append({
                "periodo": str(periodo),
                "mes": mes,
                "linea_od": linea,
                "viajes_observados_base": viajes_obs,
                "viajes_observados_atribuibles_mes": total_atribuible,
                "viajes_observados_no_clasificados_mes": float(no_clasificado.get(mes, 0.0)),
                "participacion_linea_mes": participacion,
                "viajes_proyectados": float(total_mes) * participacion,
            })
    return pd.DataFrame(rows)


def columnas_insumos_tipo_tarjeta() -> pd.DataFrame:
    insumos = load_card_type_processed_inputs()
    rows = []
    for nombre, df in insumos.items():
        if isinstance(df, pd.DataFrame):
            rows.append({"insumo": nombre, "columnas": ", ".join(df.columns), "filas": len(df)})
    return pd.DataFrame(rows)


def validar_insumos_tipo_tarjeta(tol: float = 1e-8) -> pd.DataFrame:
    insumos = load_card_type_processed_inputs()
    station_order = list(insumos["station_order"])
    od = insumos["od_historica_tipo_tarjeta"]
    pm = insumos["participacion_mensual_tipo_tarjeta"]
    pod = insumos["participacion_od_tipo_tarjeta"]
    mapeo = insumos["mapeo_tipo_tarjeta"]
    tarifas = insumos["tarifas"]
    base_subsidio = insumos["base_subsidio_referencial"]

    def row(control: str, ok: bool, detalle: str) -> dict:
        return {"control": control, "estado": "OK" if ok else "REVISAR", "detalle": detalle}

    rows = []
    expected = set(TIPOS_TARJETA_ESPERADOS)
    tipos_por_insumo = {
        "mapeo": set(mapeo["tipo_tarjeta"].astype(str)),
        "od_historica": set(od["tipo_tarjeta"].astype(str)),
        "participacion_mensual": set(pm["tipo_tarjeta"].astype(str)),
        "participacion_od": set(pod["tipo_tarjeta"].astype(str)),
    }
    faltantes = {k: sorted(expected - v) for k, v in tipos_por_insumo.items()}
    sobrantes = {k: sorted(v - expected) for k, v in tipos_por_insumo.items()}
    tipos_ok = all(not v for v in faltantes.values()) and all(not v for v in sobrantes.values())
    rows.append(row("Tipos de tarjeta esperados", tipos_ok, f"Esperados: {len(expected)}; faltantes: {faltantes}; sobrantes: {sobrantes}"))

    meses = set(range(1, 13))
    meses_tipo = pm.groupby("tipo_tarjeta")["mes"].apply(lambda s: set(s.astype(int))).to_dict()
    meses_faltantes = {t: sorted(meses - meses_tipo.get(t, set())) for t in TIPOS_TARJETA_ESPERADOS}
    meses_extra = {t: sorted(meses_tipo.get(t, set()) - meses) for t in TIPOS_TARJETA_ESPERADOS}
    meses_ok = all(not v for v in meses_faltantes.values()) and all(not v for v in meses_extra.values()) and len(pm) == 12 * len(expected)
    rows.append(row("Doce meses por tipo de tarjeta", meses_ok, f"Filas participación mensual: {len(pm)}; faltantes: {meses_faltantes}; extra: {meses_extra}"))

    estaciones_od = list(dict.fromkeys(pd.concat([od["origen"], od["destino"]]).astype(str)))
    estaciones_ok = estaciones_od == station_order
    rows.append(row("Orden original de estaciones preservado", estaciones_ok, f"Orden CSV: {len(station_order)} estaciones; orden OD coincide: {estaciones_ok}"))

    sums_pm = pm.groupby("mes")["participacion_tipo_mes"].sum()
    max_diff_pm = float((sums_pm - 1.0).abs().max())
    rows.append(row("Participaciones mensuales por tipo suman 1", max_diff_pm <= tol, f"Diferencia máxima: {max_diff_pm:.12f}"))

    sums_pod = pod.groupby(["tipo_tarjeta", "mes"], as_index=False).agg(
        participacion=("participacion_od_tipo_mes", "sum"),
        viajes=("viajes_observados_tipo_mes", "max"),
    )
    mask_con_viajes = sums_pod["viajes"] > 0
    max_diff_pod = float((sums_pod.loc[mask_con_viajes, "participacion"] - 1.0).abs().max()) if mask_con_viajes.any() else 0.0
    sin_viajes_ok = bool((sums_pod.loc[~mask_con_viajes, "participacion"].abs() <= tol).all())
    rows.append(row("Participaciones OD por tipo/mes suman 1", max_diff_pod <= tol and sin_viajes_ok, f"Diferencia máxima con viajes: {max_diff_pod:.12f}; casos sin viajes OK: {sin_viajes_ok}"))

    required_fare_cols = {"tipo_pasajero", "origen", "destino", "tarifa_2026"}
    tarifa_cols_ok = required_fare_cols.issubset(tarifas.columns)
    tarifa_tipos = set(tarifas["tipo_pasajero"].astype(str))
    tarifa_tipos_ok = set(TIPOS).issubset(tarifa_tipos)
    tarifa_estaciones = set(pd.concat([tarifas["origen"], tarifas["destino"]]).map(canon).astype(str))
    tarifa_estaciones_ok = {canon(e) for e in station_order}.issubset(tarifa_estaciones)
    tarifa_mapeo_ok = set(mapeo["tarifa_aplicable"].dropna().astype(str)).issubset(TARIFA_APLICABLE_A_TIPO_PASAJERO)
    rows.append(row(
        "Estructura de tarifas para ingresos preliminares",
        tarifa_cols_ok and tarifa_tipos_ok and tarifa_estaciones_ok and tarifa_mapeo_ok,
        f"Columnas OK: {tarifa_cols_ok}; tipos tarifa: {sorted(tarifa_tipos)}; estaciones cubiertas: {tarifa_estaciones_ok}; mapeo tarifa OK: {tarifa_mapeo_ok}",
    ))

    required_subsidio_cols = {"mes", "mes_nombre", "grupo_subsidio_referencial", "origen", "destino", "viajes_observados_base_referencial"}
    rows.append(row(
        "Estructura de base referencial de subsidio",
        required_subsidio_cols.issubset(base_subsidio.columns),
        f"Columnas detectadas: {list(base_subsidio.columns)}",
    ))

    return pd.DataFrame(rows)



def cargar_tarifa_estudiante_bt_sin_subsidio() -> pd.DataFrame:
    """Carga la tarifa estudiante BT sin subsidio corregida en formato largo."""
    path = PROCESSED_FILES["tarifa_estudiante_bt_sin_subsidio"]
    cols = {
        "origen", "destino", "tarifa_estudiante_bt_sin_subsidio", "es_diagonal",
        "origen_en_modelo", "destino_en_modelo", "tarifa_disponible", "fuente",
    }
    if not path.exists():
        raise FileNotFoundError(f"No existe {path}")
    df = pd.read_csv(path)
    missing = cols - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en tarifa estudiante BT sin subsidio: {sorted(missing)}")
    df["tarifa_estudiante_bt_sin_subsidio"] = pd.to_numeric(df["tarifa_estudiante_bt_sin_subsidio"], errors="coerce")
    df["es_diagonal"] = df["es_diagonal"].astype(int)
    df["tarifa_disponible"] = df["tarifa_disponible"].astype(int)
    return df


def cargar_tasa_descuento_normal() -> float:
    """Carga y valida la tasa de descuento normal Biotren versionada."""
    df = pd.read_csv(PROCESSED_FILES["parametros_subsidio_biotren"])
    fila = df[df["parametro"].astype(str).eq("tasa_descuento_normal")]
    if fila.empty:
        raise ValueError("No existe el parámetro tasa_descuento_normal")
    tasa = float(fila.iloc[0]["valor"])
    if not (0.0 < tasa < 1.0):
        raise ValueError(f"tasa_descuento_normal fuera de rango (0,1): {tasa}")
    return tasa


def validar_cobertura_tarifa_estudiante(station_order: list[str], viajes_media_superior: pd.DataFrame | None = None) -> dict:
    """Valida cobertura de estaciones y pares OD para tarifa estudiante sin subsidio."""
    tarifa = cargar_tarifa_estudiante_bt_sin_subsidio()
    estaciones_modelo = {canon(e) for e in station_order}
    estaciones_tarifa = {canon(e) for e in pd.concat([tarifa["origen"], tarifa["destino"]]).dropna().astype(str)}
    sin_cobertura = sorted(estaciones_modelo - estaciones_tarifa)
    fuera_modelo = sorted(estaciones_tarifa - estaciones_modelo)
    disponibles = tarifa[tarifa["tarifa_disponible"].astype(int).eq(1)]
    estaciones_sin_tarifas = []
    for e in sorted(estaciones_tarifa):
        mov = disponibles[disponibles["origen"].map(canon).eq(e) | disponibles["destino"].map(canon).eq(e)]
        if mov.empty:
            estaciones_sin_tarifas.append(e)
    advertencias = []
    if sin_cobertura:
        advertencias.append("Estaciones del modelo sin cobertura en matriz estudiante: " + ", ".join(sin_cobertura))
    if fuera_modelo:
        advertencias.append("Estaciones de matriz estudiante fuera del modelo: " + ", ".join(fuera_modelo))
    if estaciones_sin_tarifas:
        advertencias.append("Estaciones sin tarifas disponibles: " + ", ".join(estaciones_sin_tarifas))
    pares_media_sin_tarifa = 0
    if viajes_media_superior is not None and not viajes_media_superior.empty:
        llave = tarifa.assign(_o=tarifa["origen"].map(canon), _d=tarifa["destino"].map(canon))[["_o", "_d", "tarifa_disponible"]]
        tmp = viajes_media_superior.assign(_o=viajes_media_superior["origen"].map(canon), _d=viajes_media_superior["destino"].map(canon))
        m = tmp.merge(llave, on=["_o", "_d"], how="left")
        pares_media_sin_tarifa = int(((m["viajes_proyectados"] > 1e-9) & (m["_o"] != m["_d"]) & (m["tarifa_disponible"].fillna(0).astype(int) != 1)).sum())
        if pares_media_sin_tarifa:
            advertencias.append(f"Pares OD media_superior con viajes y sin tarifa estudiante sin subsidio: {pares_media_sin_tarifa}")
    return {"estaciones_matriz": len(estaciones_tarifa), "estaciones_modelo": len(station_order), "sin_cobertura_modelo": sin_cobertura, "fuera_modelo": fuera_modelo, "estaciones_sin_tarifas": estaciones_sin_tarifas, "pares_media_superior_sin_tarifa": pares_media_sin_tarifa, "advertencias": advertencias}

def _tarifa_por_tipo_tarjeta(tipo_tarjeta: str, mapeo: pd.DataFrame) -> str | None:
    """Devuelve el tipo de tarifa aplicable para un tipo de tarjeta."""
    fila = mapeo[mapeo["tipo_tarjeta"].astype(str) == str(tipo_tarjeta)]
    if fila.empty:
        return None
    tarifa_aplicable = str(fila["tarifa_aplicable"].iloc[0])
    return TARIFA_APLICABLE_A_TIPO_PASAJERO.get(tarifa_aplicable)


def distribuir_proyeccion_biotren_por_tipo_tarjeta(serie_biotren: pd.Series | dict) -> dict[str, pd.DataFrame]:
    """Distribuye la proyección mensual Biotren por tipo de tarjeta en memoria.

    La demanda mensual se reparte con las participaciones mensuales históricas
    por tipo de tarjeta y con las participaciones OD de cada tipo/mes. El
    ingreso tarifario preliminar se calcula sólo para las tarjetas con tarifa
    directa: monedero usa tarifa Normal, media_superior usa tarifa Estudiante y
    adulto_mayor usa tarifa Adulto Mayor. El resto conserva viajes proyectados
    con ingreso cero.

    No exporta matrices ni archivos; devuelve resúmenes agregados y una base
    referencial de subsidio sólo para trazabilidad, sin cálculo de montos.
    """
    insumos = load_card_type_processed_inputs()
    station_order = list(insumos["station_order"])
    pm = insumos["participacion_mensual_tipo_tarjeta"].copy()
    pod = insumos["participacion_od_tipo_tarjeta"].copy()
    mapeo = insumos["mapeo_tipo_tarjeta"].copy()
    tarifas = insumos["tarifas"].copy()
    base_subsidio = insumos["base_subsidio_referencial"].copy()

    serie = pd.Series(serie_biotren, dtype=float) if isinstance(serie_biotren, dict) else serie_biotren.astype(float).copy()
    tarifa_mats = {
        str(tipo): _matrix_from_long(g, "tarifa_2026", station_order)
        for tipo, g in tarifas.groupby("tipo_pasajero", sort=False)
    }

    rows = []
    for periodo, total_mes in serie.items():
        mes = int(str(periodo)[-2:])
        pm_mes = pm[pm["mes"].astype(int) == mes]
        pod_mes = pod[pod["mes"].astype(int) == mes]
        for _, part_row in pm_mes.iterrows():
            tipo_tarjeta = str(part_row["tipo_tarjeta"])
            total_tipo = float(total_mes) * float(part_row["participacion_tipo_mes"])
            od_tipo = pod_mes[pod_mes["tipo_tarjeta"].astype(str) == tipo_tarjeta].copy()
            if od_tipo.empty:
                continue
            od_tipo["viajes_proyectados"] = total_tipo * od_tipo["participacion_od_tipo_mes"].astype(float)
            tipo_tarifa = _tarifa_por_tipo_tarjeta(tipo_tarjeta, mapeo)
            if tipo_tarifa is None:
                od_tipo["ingresos_tarifarios_proyectados"] = 0.0
            else:
                tarifa = tarifa_mats[tipo_tarifa]
                od_tipo["ingresos_tarifarios_proyectados"] = [
                    float(v) * float(tarifa.loc[canon(o), canon(d)])
                    if canon(o) in tarifa.index and canon(d) in tarifa.columns else 0.0
                    for o, d, v in zip(od_tipo["origen"], od_tipo["destino"], od_tipo["viajes_proyectados"])
                ]
            od_tipo.insert(0, "periodo", str(periodo))
            od_tipo["tipo_pasajero_tarifa"] = tipo_tarifa if tipo_tarifa is not None else "Sin ingreso tarifario"
            rows.append(od_tipo[[
                "periodo", "mes", "tipo_tarjeta", "nombre_visual", "origen", "destino",
                "tipo_pasajero_tarifa", "viajes_proyectados", "ingresos_tarifarios_proyectados",
            ]])

    viajes_tarjeta_long = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    resumen = viajes_tarjeta_long.groupby(
        ["periodo", "mes", "tipo_tarjeta", "nombre_visual", "tipo_pasajero_tarifa"],
        as_index=False,
    ).agg(
        viajes_proyectados=("viajes_proyectados", "sum"),
        ingresos_tarifarios_proyectados=("ingresos_tarifarios_proyectados", "sum"),
    )
    resumen["tarifa_media_proyectada"] = np.where(
        resumen["viajes_proyectados"] > 0,
        resumen["ingresos_tarifarios_proyectados"] / resumen["viajes_proyectados"],
        0.0,
    )

    subsidio_referencial = base_subsidio.groupby(
        ["mes", "grupo_subsidio_referencial"], as_index=False
    )["viajes_observados_base_referencial"].sum()

    ingresos_subsidio = calcular_ingresos_y_subsidio_biotren(viajes_tarjeta_long, station_order, tarifa_mats)

    return {
        "resumen_tipo_tarjeta": resumen,
        "viajes_tipo_tarjeta_long": viajes_tarjeta_long,
        "subsidio_referencial_base": subsidio_referencial,
        "mapeo_tipo_tarjeta": mapeo,
        "ingresos_subsidio_biotren": ingresos_subsidio,
    }



def calcular_ingresos_y_subsidio_biotren(viajes_tarjeta_long: pd.DataFrame, station_order: list[str], tarifa_mats: dict[str, pd.DataFrame] | None = None) -> dict:
    """Calcula ingresos por venta de pasajes y subsidios Biotren sin modificar viajes."""
    tasa = cargar_tasa_descuento_normal()
    if tarifa_mats is None:
        tarifas = pd.read_csv(PROCESSED_FILES["tarifas"])
        tarifa_mats = {str(t): _matrix_from_long(g, "tarifa_2026", station_order) for t, g in tarifas.groupby("tipo_pasajero", sort=False)}
    tarifa_est = cargar_tarifa_estudiante_bt_sin_subsidio()
    tarifa_est_m = _matrix_from_long(tarifa_est, "tarifa_estudiante_bt_sin_subsidio", station_order)
    tarifa_pagada_estudiante = pd.DataFrame(
        tarifa_mats["Estudiante"].loc[station_order, station_order].astype(float).to_numpy(copy=True),
        index=station_order,
        columns=station_order,
    )
    # Fórmula oficial estudiante: diferencia agregada entre ingreso teórico
    # sin subsidio (sin diagonal) y venta media_superior pagada (con diagonal).
    # La brecha OD max(0, sin_subsidio - pagada) se conserva sólo como
    # diagnóstico comparativo, no como fórmula final.
    brecha_estudiante_diagnostica = (tarifa_est_m - tarifa_pagada_estudiante).clip(lower=0.0)
    for e in station_order:
        if e in tarifa_est_m.index and e in tarifa_est_m.columns:
            tarifa_est_m.loc[e, e] = 0.0
        if e in brecha_estudiante_diagnostica.index and e in brecha_estudiante_diagnostica.columns:
            brecha_estudiante_diagnostica.loc[e, e] = 0.0
    tarifa_normal = pd.DataFrame(
        tarifa_mats["Normal"].loc[station_order, station_order].astype(float).to_numpy(copy=True),
        index=station_order,
        columns=station_order,
    )
    for e in station_order:
        tarifa_normal.loc[e, e] = 0.0

    normal_tipos = {"monedero", "estudiante_basica", "discapacitado", "funcionario_normal", "funcionario_especial", "convenio_colectivo"}
    estudiante_tipos = {"media_superior"}
    tarifa_directa_tipos = {"monedero", "media_superior", "adulto_mayor"}

    venta = float(viajes_tarjeta_long["ingresos_tarifarios_proyectados"].sum())
    normal = viajes_tarjeta_long[viajes_tarjeta_long["tipo_tarjeta"].astype(str).isin(normal_tipos)]
    media = viajes_tarjeta_long[viajes_tarjeta_long["tipo_tarjeta"].astype(str).isin(estudiante_tipos)]

    def monto(df, mat, *, incluir_diagonal=False):
        total = 0.0
        for r in df.itertuples(index=False):
            o, d = canon(getattr(r, "origen")), canon(getattr(r, "destino"))
            if not incluir_diagonal and o == d:
                continue
            if o in mat.index and d in mat.columns:
                tarifa = mat.loc[o, d]
                if pd.notna(tarifa):
                    total += float(getattr(r, "viajes_proyectados")) * float(tarifa)
        return total

    monto_normal_base = monto(normal, tarifa_normal)
    subsidio_normal = monto_normal_base / (1.0 - tasa) - monto_normal_base
    venta_media_superior = float(media["ingresos_tarifarios_proyectados"].sum())
    subsidio_estudiante_formula_anterior = monto(media, brecha_estudiante_diagnostica)
    ingreso_teorico_estudiante_sin_subsidio = monto(media, tarifa_est_m, incluir_diagonal=False)
    subsidio_estudiante = ingreso_teorico_estudiante_sin_subsidio - venta_media_superior
    ingreso_total_estudiante_corregido = venta_media_superior + subsidio_estudiante
    subsidio_total = subsidio_normal + subsidio_estudiante
    ingreso_total = venta + subsidio_total
    cobertura = validar_cobertura_tarifa_estudiante(station_order, media)
    if subsidio_estudiante < 0:
        cobertura.setdefault("advertencias", []).append("Subsidio estudiante oficial agregado negativo; se reporta sin truncar por instrucción metodológica.")
    resumen_mensual = viajes_tarjeta_long.groupby("periodo", as_index=False).agg(
        viajes_proyectados=("viajes_proyectados", "sum"),
        ingreso_venta=("ingresos_tarifarios_proyectados", "sum"),
    )
    resumen_mensual["tasa_descuento_normal"] = tasa
    resumen_mensual["monto_normal_base"] = np.nan
    resumen_mensual["subsidio_normal"] = np.nan
    resumen_mensual["subsidio_estudiante"] = np.nan
    for periodo, g in viajes_tarjeta_long.groupby("periodo"):
        n = g[g["tipo_tarjeta"].astype(str).isin(normal_tipos)]
        m = g[g["tipo_tarjeta"].astype(str).isin(estudiante_tipos)]
        mn = monto(n, tarifa_normal)
        venta_ms_mes = float(m["ingresos_tarifarios_proyectados"].sum())
        teorico_ms_mes = monto(m, tarifa_est_m, incluir_diagonal=False)
        se = teorico_ms_mes - venta_ms_mes
        idx = resumen_mensual["periodo"].eq(periodo)
        resumen_mensual.loc[idx, "monto_normal_base"] = mn
        resumen_mensual.loc[idx, "subsidio_normal"] = mn / (1.0 - tasa) - mn
        resumen_mensual.loc[idx, "subsidio_estudiante"] = se
    resumen_mensual["subsidio_total"] = resumen_mensual["subsidio_normal"] + resumen_mensual["subsidio_estudiante"]
    resumen_mensual["ingreso_total_biotren"] = resumen_mensual["ingreso_venta"] + resumen_mensual["subsidio_total"]
    diagnostico_estudiante = {
        "subsidio_estudiante_formula_anterior": subsidio_estudiante_formula_anterior,
        "subsidio_estudiante_brecha_od_diagnostica": subsidio_estudiante_formula_anterior,
        "subsidio_estudiante_recalculado": subsidio_estudiante,
        "diferencia_absoluta": subsidio_estudiante_formula_anterior - subsidio_estudiante,
        "diferencia_porcentual": ((subsidio_estudiante_formula_anterior - subsidio_estudiante) / subsidio_estudiante_formula_anterior * 100.0) if subsidio_estudiante_formula_anterior else 0.0,
        "venta_pasajes_media_superior": venta_media_superior,
        "ingreso_total_estudiante_corregido": ingreso_total_estudiante_corregido,
        "ingreso_teorico_estudiante_sin_subsidio": ingreso_teorico_estudiante_sin_subsidio,
        "diferencia_ingreso_corregido_vs_teorico": ingreso_total_estudiante_corregido - ingreso_teorico_estudiante_sin_subsidio,
        "brecha_minima_diagnostica": float(np.nanmin(brecha_estudiante_diagnostica.to_numpy(dtype=float))),
        "diagonal_brecha_diagnostica_suma": float(np.nansum(np.diag(brecha_estudiante_diagnostica.to_numpy(dtype=float)))),
        "venta_media_superior_con_diagonal": venta_media_superior,
        "ingreso_teorico_estudiante_sin_subsidio_sin_diagonal": ingreso_teorico_estudiante_sin_subsidio,
    }
    resumen_anual = {"ingreso_venta": venta, "monto_normal_base": monto_normal_base, "subsidio_normal": subsidio_normal, "subsidio_estudiante": subsidio_estudiante, "subsidio_total": subsidio_total, "ingreso_total_biotren": ingreso_total, "tasa_descuento_normal": tasa, "viajes_biotren": float(viajes_tarjeta_long["viajes_proyectados"].sum()), **diagnostico_estudiante}
    return {"resumen_anual": resumen_anual, "resumen_mensual": resumen_mensual, "cobertura_estudiante": cobertura, "diagnostico_estudiante": diagnostico_estudiante, "grupos": {"normal_base": sorted(normal_tipos), "estudiante_subsidio": sorted(estudiante_tipos), "tarifa_directa": sorted(tarifa_directa_tipos), "tarifa_estudiante_pagada": ["Estudiante"], "tarifa_estudiante_sin_subsidio_path": str(PROCESSED_FILES["tarifa_estudiante_bt_sin_subsidio"].relative_to(BASE_DIR))}}

def exportar_salidas_tipo_tarjeta(
    serie_biotren: pd.Series | dict,
    output_dir: Path | str | None = None,
    *,
    meses: list[int] | tuple[int, ...] | set[int] | None = None,
    tipos_tarjeta: list[str] | tuple[str, ...] | set[str] | None = None,
    escribir_archivos: bool = True,
) -> dict[str, pd.DataFrame | Path | dict[str, Path]]:
    """Prepara y opcionalmente exporta salidas OD Biotren por tipo de tarjeta.

    La función reutiliza el motor en memoria y no cambia los cálculos ni la
    proyección mensual total. En modo validación puede filtrar un mes/tipo y
    omitir la escritura de archivos (`escribir_archivos=False`). En modo
    exportación escribe archivos CSV long completos sólo en una carpeta local
    ignorada por Git.
    """
    resultado = distribuir_proyeccion_biotren_por_tipo_tarjeta(serie_biotren)
    viajes = resultado["viajes_tipo_tarjeta_long"].copy()
    resumen = resultado["resumen_tipo_tarjeta"].copy()
    base_subsidio_long = load_card_type_processed_inputs()["base_subsidio_referencial"].copy()

    if meses is not None:
        meses_set = {int(m) for m in meses}
        viajes = viajes[viajes["mes"].astype(int).isin(meses_set)].copy()
        resumen = resumen[resumen["mes"].astype(int).isin(meses_set)].copy()
        base_subsidio_long = base_subsidio_long[base_subsidio_long["mes"].astype(int).isin(meses_set)].copy()

    if tipos_tarjeta is not None:
        tipos_set = {str(t) for t in tipos_tarjeta}
        viajes = viajes[viajes["tipo_tarjeta"].astype(str).isin(tipos_set)].copy()
        resumen = resumen[resumen["tipo_tarjeta"].astype(str).isin(tipos_set)].copy()

    ingresos = viajes[[
        "periodo", "mes", "tipo_tarjeta", "nombre_visual", "origen", "destino",
        "tipo_pasajero_tarifa", "ingresos_tarifarios_proyectados",
    ]].copy()
    viajes = viajes[[
        "periodo", "mes", "tipo_tarjeta", "nombre_visual", "origen", "destino",
        "viajes_proyectados",
    ]].copy()

    archivos: dict[str, Path] = {}
    destino = Path(output_dir) if output_dir is not None else OUT / "od_biotren_tipo_tarjeta"
    if escribir_archivos:
        destino.mkdir(parents=True, exist_ok=True)
        archivos = {
            "viajes": destino / "od_2027_tipo_tarjeta_long.csv",
            "ingresos": destino / "ingresos_tipo_tarjeta_long.csv",
            "base_subsidio": destino / "base_subsidio_referencial_long.csv",
            "resumen": destino / "resumen_mensual_tipo_tarjeta.csv",
        }
        viajes.to_csv(archivos["viajes"], index=False)
        ingresos.to_csv(archivos["ingresos"], index=False)
        base_subsidio_long.to_csv(archivos["base_subsidio"], index=False)
        resumen.to_csv(archivos["resumen"], index=False)

    return {
        "viajes_tipo_tarjeta_long": viajes,
        "ingresos_tipo_tarjeta_long": ingresos,
        "base_subsidio_referencial_long": base_subsidio_long,
        "resumen_tipo_tarjeta": resumen,
        "output_dir": destino,
        "archivos": archivos,
    }


# ---------------------------------------------------------------------------
# Tarifas, distancias y costo generalizado
# ---------------------------------------------------------------------------

def _read_matrix_at(df: pd.DataFrame, title: str | None = None, sheet_kind: str = "fare", station_order: list[str] | None = None) -> pd.DataFrame:
    vals = df.values
    title_row = None
    if title:
        t = key(title)
        for r in range(vals.shape[0]):
            for c in range(vals.shape[1]):
                if pd.notna(vals[r, c]) and t in key(vals[r, c]):
                    title_row = r
                    break
            if title_row is not None:
                break
        if title_row is None:
            raise ValueError(f"No se encontró el bloque '{title}'.")
        search_start = title_row + 1
    else:
        search_start = 0

    header_row = station_col = None
    for r in range(search_start, vals.shape[0]):
        for c in range(vals.shape[1]):
            if pd.notna(vals[r, c]) and key(vals[r, c]) == "estaciones":
                header_row = r
                station_col = c
                break
        if header_row is not None:
            break
    if header_row is None:
        raise ValueError("No se encontró fila de encabezados 'Estaciones'.")

    heads, cols = [], []
    for c in range(station_col + 1, vals.shape[1]):
        if pd.isna(vals[header_row, c]):
            break
        cv = canon(vals[header_row, c])
        if cv == "Total":
            break
        heads.append(cv)
        cols.append(c)

    idx, rows = [], []
    for r in range(header_row + 1, vals.shape[0]):
        if pd.isna(vals[r, station_col]):
            continue
        cv = canon(vals[r, station_col])
        if cv == "Total":
            break
        if cv in ["Estaciones", ""]:
            continue
        idx.append(cv)
        rows.append([num(vals[r, c]) for c in cols])
        if len(idx) >= len(heads):
            break
    M = pd.DataFrame(rows, index=idx, columns=heads)
    M = M.groupby(level=0, sort=False).mean()
    M = M.T.groupby(level=0, sort=False).mean().T
    if station_order is not None:
        M = M.reindex(index=station_order, columns=station_order, fill_value=0.0)
    return M.astype(float)


def load_tariff_matrices(station_order: list[str]) -> dict[str, pd.DataFrame]:
    df = pd.read_excel(FARE_FILE, sheet_name="BT-26 por Estación", header=None, engine="openpyxl")
    matrices = {
        "Normal": _read_matrix_at(df, "Matriz Tarifaria Adulto", station_order=station_order),
        "Estudiante": _read_matrix_at(df, "Matriz Tarifaria Estudiante", station_order=station_order),
        "Adulto Mayor": _read_matrix_at(df, "Matriz Tarifaria Tercera Edad", station_order=station_order),
    }
    return matrices


def load_distance_matrix(station_order: list[str]) -> pd.DataFrame:
    df = pd.read_excel(DIST_FILE, sheet_name="PAX KM BT", header=None, engine="openpyxl")
    M = _read_matrix_at(df, None, station_order=station_order)
    return M.astype(float)


def generalized_cost(fare: pd.DataFrame, dist: pd.DataFrame, alpha: float = ALPHA_TARIFA, beta: float = BETA_DISTANCIA) -> pd.DataFrame:
    F = fare.astype(float).copy()
    D = dist.astype(float).copy()
    f_mean = F.replace(0, np.nan).stack().mean()
    d_mean = D.replace(0, np.nan).stack().mean()
    Fn = F / f_mean if f_mean and not np.isnan(f_mean) else F
    Dn = D / d_mean if d_mean and not np.isnan(d_mean) else D
    C = alpha * Fn + beta * Dn
    arr = writable_array(C.to_numpy(dtype=float, copy=True))
    positive = arr[np.isfinite(arr) & (arr > 0)]
    minpos = float(np.nanmin(positive)) if positive.size else 1.0
    C = C.replace(0, minpos * 0.10).fillna(minpos)
    return C


def impedance(C: pd.DataFrame, lam: float = LAMBDA, kind: str = FUNCION_IMPEDANCIA) -> pd.DataFrame:
    arr = np.maximum(writable_array(C.to_numpy(dtype=float, copy=True)), 1e-9)
    if kind == "potencial":
        out = arr ** (-lam)
    else:
        out = np.exp(-lam * arr)
    return pd.DataFrame(out, index=C.index, columns=C.columns)


def ipf(seed: pd.DataFrame | np.ndarray, row_totals, col_totals, max_iter: int = 500, tol: float = 1e-8):
    idx = seed.index if isinstance(seed, pd.DataFrame) else None
    cols = seed.columns if isinstance(seed, pd.DataFrame) else None
    M = np.maximum(writable_array(seed), 1e-12)
    row = writable_array(row_totals)
    col = writable_array(col_totals)
    if row.sum() <= 0 or col.sum() <= 0:
        Z = np.zeros_like(M)
        return (pd.DataFrame(Z, index=idx, columns=cols) if idx is not None else Z), False, 0, np.nan
    col = col * (row.sum() / max(col.sum(), 1e-12))
    for it in range(max_iter):
        rs = M.sum(axis=1)
        row_factor = np.divide(row, rs, out=np.zeros_like(row, dtype=float), where=rs > 0)
        M = (M.T * row_factor).T
        cs = M.sum(axis=0)
        col_factor = np.divide(col, cs, out=np.zeros_like(col, dtype=float), where=cs > 0)
        M = M * col_factor
        if it % 5 == 0:
            err = max(
                np.max(np.abs(M.sum(axis=1) - row) / (row + 1e-9)),
                np.max(np.abs(M.sum(axis=0) - col) / (col + 1e-9)),
            )
            if err < tol:
                break
    err = max(
        np.max(np.abs(M.sum(axis=1) - row) / (row + 1e-9)),
        np.max(np.abs(M.sum(axis=0) - col) / (col + 1e-9)),
    )
    return (pd.DataFrame(M, index=idx, columns=cols) if idx is not None else M), bool(err < tol), it + 1, float(err)


# ---------------------------------------------------------------------------
# Factores históricos por tipo y distribución OD proyectada
# ---------------------------------------------------------------------------

def year_weights_for_month(available_years: Iterable[int]) -> dict[int, float]:
    available = set(int(y) for y in available_years)
    if 2026 in available:
        raw = {2026: 0.50, 2025: 0.30, 2024: 0.15, 2023: 0.05}
    else:
        raw = {2025: 0.50, 2024: 0.35, 2023: 0.15}
    w = {y: v for y, v in raw.items() if y in available}
    s = sum(w.values())
    if s <= 0:
        return {}
    return {y: v / s for y, v in w.items()}


@lru_cache(maxsize=1)
def cargar_insumos_od():
    mats, validation, station_order, fares, dist = load_processed_inputs()
    costs = {tipo: generalized_cost(fares[tipo], dist) for tipo in TIPOS}
    return mats, validation, station_order, fares, dist, costs


def weighted_matrix_for_month(mats: dict, tipo: str, mes: int, years_allowed: Iterable[int] | None = None):
    block = TIPOS_BLOQUES[tipo]
    keys = [k for k in mats if k[1] == int(mes) and k[2] == block]
    if years_allowed is not None:
        allowed = set(int(y) for y in years_allowed)
        keys = [k for k in keys if k[0] in allowed]
    years = sorted({k[0] for k in keys})
    weights = year_weights_for_month(years)
    if not weights:
        raise ValueError(f"No hay matrices disponibles para {tipo}, mes {mes}.")
    result = None
    detalle = []
    for y, w in weights.items():
        key_ = (y, int(mes), block)
        if key_ not in mats:
            continue
        M = mats[key_].astype(float)
        result = M * w if result is None else result + M * w
        detalle.append({"tipo_pasajero": tipo, "mes": int(mes), "anio_base": int(y), "peso": float(w), "total_base": float(M.to_numpy().sum())})
    return result, pd.DataFrame(detalle)


def monthly_type_shares(mats: dict) -> pd.DataFrame:
    rows = []
    for mes in range(1, 13):
        totals = {}
        detalles = []
        for tipo in TIPOS:
            M, det = weighted_matrix_for_month(mats, tipo, mes)
            totals[tipo] = float(M.to_numpy().sum())
            detalles.append(det)
        grand = sum(totals.values())
        for tipo, total in totals.items():
            rows.append({
                "mes": mes,
                "tipo_pasajero": tipo,
                "participacion": total / grand if grand > 0 else 0.0,
                "total_historico_ponderado": total,
            })
    return pd.DataFrame(rows)


def historical_od_share(mats: dict, tipo: str, mes: int):
    M, det = weighted_matrix_for_month(mats, tipo, mes)
    total = float(M.to_numpy().sum())
    if total <= 0:
        S = M.copy() * 0.0
    else:
        S = M / total
    row_share = S.sum(axis=1)
    col_share = S.sum(axis=0)
    return S, row_share, col_share, det


def gravity_share_for_month(tipo: str, mes: int, row_share: pd.Series, col_share: pd.Series, costs: dict[str, pd.DataFrame]):
    C = costs[tipo].loc[row_share.index, row_share.index]
    seed = impedance(C)
    # La diagonal no se elimina porque existe en los datos; se reduce para evitar
    # que el bajo costo intrazonal concentre artificialmente el resultado.
    arr = writable_array(seed.to_numpy(dtype=float, copy=True))
    np.fill_diagonal(arr, np.diag(arr).copy() * 0.05)
    seed = pd.DataFrame(arr, index=seed.index, columns=seed.columns)
    G, conv, it, err = ipf(seed, row_share.to_numpy(dtype=float, copy=True), col_share.to_numpy(dtype=float, copy=True))
    total = float(G.to_numpy().sum())
    return G / total if total > 0 else G, conv, it, err


def distribuir_mes_tipo(total_mes: float, tipo: str, mes: int, mats: dict, fares: dict, costs: dict):
    shares = monthly_type_shares(mats)
    part = float(shares[(shares.mes == int(mes)) & (shares.tipo_pasajero == tipo)]["participacion"].iloc[0])
    total_tipo = float(total_mes) * part
    S, row_share, col_share, det_hist = historical_od_share(mats, tipo, mes)
    # Si una estación no posee cobertura tarifaria positiva en la matriz 2026 del
    # tipo de pasajero, se conserva en el orden de salida, pero no se le asigna
    # demanda proyectada ni ingresos. Esto evita estimar ingresos con tarifas
    # inexistentes y deja trazable la necesidad de completar la matriz tarifaria.
    tarifa_tipo = fares[tipo].loc[S.index, S.columns].astype(float)
    cobertura_estacion = ((tarifa_tipo.sum(axis=1) + tarifa_tipo.sum(axis=0)) > 0).astype(float)
    S = S.mul(cobertura_estacion, axis=0).mul(cobertura_estacion, axis=1)
    s_total = float(S.to_numpy().sum())
    if s_total > 0:
        S = S / s_total
    row_share = S.sum(axis=1)
    col_share = S.sum(axis=0)
    G, conv_g, it_g, err_g = gravity_share_for_month(tipo, mes, row_share, col_share, costs)
    w_hist = PESO_HISTORICO[tipo]
    seed = w_hist * S + (1.0 - w_hist) * G
    row_totals = total_tipo * row_share.to_numpy(dtype=float, copy=True)
    col_totals = total_tipo * col_share.to_numpy(dtype=float, copy=True)
    T, conv, it, err = ipf(seed, row_totals, col_totals)
    tarifa = fares[tipo].loc[T.index, T.columns].astype(float)
    ingresos = T * tarifa
    resumen = {
        "mes": int(mes),
        "tipo_pasajero": tipo,
        "demanda_total_biotren_mes": float(total_mes),
        "participacion_tipo": part,
        "viajes_tipo_proyectados": float(T.to_numpy().sum()),
        "ingresos_tipo_proyectados": float(ingresos.to_numpy().sum()),
        "tarifa_media_tipo": float(ingresos.to_numpy().sum() / T.to_numpy().sum()) if T.to_numpy().sum() > 0 else 0.0,
        "peso_historico": float(w_hist),
        "peso_gravitacional": float(1.0 - w_hist),
        "ipf_converge": bool(conv),
        "ipf_iteraciones": int(it),
        "ipf_error_balance": float(err),
        "gravity_converge": bool(conv_g),
        "gravity_iteraciones": int(it_g),
        "gravity_error_balance": float(err_g),
    }
    return T, ingresos, resumen, det_hist


def distribuir_proyeccion_biotren(serie_biotren: pd.Series | dict) -> dict:
    mats, validation, station_order, fares, dist, costs = cargar_insumos_od()
    if isinstance(serie_biotren, dict):
        serie = pd.Series(serie_biotren)
    else:
        serie = serie_biotren.copy()
    # índice esperado: 2027-01, 2027-02, ...
    viajes_long, ingresos_long, resumen, det_pesos, factores = [], [], [], [], []
    matrices_viajes, matrices_ingresos = {}, {}
    type_shares = monthly_type_shares(mats)
    for periodo, total_mes in serie.items():
        mes = int(str(periodo)[-2:])
        for tipo in TIPOS:
            T, R, res, det_hist = distribuir_mes_tipo(float(total_mes), tipo, mes, mats, fares, costs)
            res["periodo"] = str(periodo)
            resumen.append(res)
            det_hist = det_hist.copy()
            det_hist["periodo"] = str(periodo)
            det_pesos.append(det_hist)
            matrices_viajes[(str(periodo), tipo)] = T
            matrices_ingresos[(str(periodo), tipo)] = R
            l = T.stack().reset_index()
            l.columns = ["origen", "destino", "viajes_proyectados"]
            l.insert(0, "periodo", str(periodo))
            l.insert(1, "mes", mes)
            l.insert(2, "tipo_pasajero", tipo)
            viajes_long.append(l)
            rr = R.stack().reset_index()
            rr.columns = ["origen", "destino", "ingresos_proyectados"]
            rr.insert(0, "periodo", str(periodo))
            rr.insert(1, "mes", mes)
            rr.insert(2, "tipo_pasajero", tipo)
            ingresos_long.append(rr)
            F = (T / max(T.to_numpy().sum(), 1e-12)).stack().reset_index()
            F.columns = ["origen", "destino", "factor_od"]
            F.insert(0, "periodo", str(periodo))
            F.insert(1, "mes", mes)
            F.insert(2, "tipo_pasajero", tipo)
            factores.append(F)
    return {
        "station_order": station_order,
        "viajes_long": pd.concat(viajes_long, ignore_index=True),
        "ingresos_long": pd.concat(ingresos_long, ignore_index=True),
        "resumen": pd.DataFrame(resumen),
        "pesos_historicos": pd.concat(det_pesos, ignore_index=True),
        "factores_od": pd.concat(factores, ignore_index=True),
        "type_shares": type_shares,
        "matrices_viajes": matrices_viajes,
        "matrices_ingresos": matrices_ingresos,
        "tarifas": fares,
        "distancias": dist,
        "validacion_datos": validation,
    }


def matriz_desde_long(df: pd.DataFrame, periodo: str, tipo: str, valor: str, station_order: list[str]) -> pd.DataFrame:
    tmp = df[(df["periodo"] == periodo) & (df["tipo_pasajero"] == tipo)].copy()
    if tmp.empty:
        return pd.DataFrame(0.0, index=station_order, columns=station_order)
    M = tmp.pivot_table(index="origen", columns="destino", values=valor, aggfunc="sum", fill_value=0.0)
    return M.reindex(index=station_order, columns=station_order, fill_value=0.0)


# ---------------------------------------------------------------------------
# Validación del enfoque híbrido por tipo de pasajero
# ---------------------------------------------------------------------------

def metrics(obs: pd.DataFrame, est: pd.DataFrame) -> dict:
    o = writable_array(obs.to_numpy(dtype=float, copy=True)).ravel()
    e = writable_array(est.to_numpy(dtype=float, copy=True)).ravel()
    er = e - o
    ae = np.abs(er)
    ss = np.sum((o - o.mean()) ** 2)
    return {
        "MAE": float(ae.mean()),
        "RMSE": float(np.sqrt(np.mean(er ** 2))),
        "MAPE_pct": float(np.nanmean(np.divide(ae, o, out=np.full_like(ae, np.nan, dtype=float), where=o > 0)) * 100),
        "Correlacion": float(np.corrcoef(o, e)[0, 1]) if np.std(o) > 0 and np.std(e) > 0 else np.nan,
        "R2": float(1 - np.sum(er ** 2) / ss) if ss > 0 else np.nan,
        "CPC": float(2 * np.minimum(o, e).sum() / (o.sum() + e.sum())) if o.sum() + e.sum() > 0 else np.nan,
        "Desviacion_abs_total": float(abs(e.sum() - o.sum())),
        "Desviacion_pct_total": float((e.sum() - o.sum()) / (o.sum() + 1e-9) * 100),
    }


def validar_hibrido_2026() -> pd.DataFrame:
    mats, validation, station_order, fares, dist, costs = cargar_insumos_od()
    rows = []
    for mes in [3, 4, 5]:
        for tipo in TIPOS:
            block = TIPOS_BLOQUES[tipo]
            obs_key = (2026, mes, block)
            if obs_key not in mats:
                continue
            obs = mats[obs_key].astype(float)
            total_obs = float(obs.to_numpy().sum())
            # Línea base: sólo patrón histórico proporcional sin 2026.
            S, row_share, col_share, _ = historical_od_share_excluding_year(mats, tipo, mes, exclude_year=2026)
            tarifa_tipo = fares[tipo].loc[S.index, S.columns].astype(float)
            cobertura_estacion = ((tarifa_tipo.sum(axis=1) + tarifa_tipo.sum(axis=0)) > 0).astype(float)
            S = S.mul(cobertura_estacion, axis=0).mul(cobertura_estacion, axis=1)
            s_total = float(S.to_numpy().sum())
            if s_total > 0:
                S = S / s_total
            row_share = S.sum(axis=1)
            col_share = S.sum(axis=0)
            baseline = S * total_obs
            rows.append({"mes": mes, "tipo_pasajero": tipo, "modelo": "historico_proporcional", **metrics(obs, baseline)})
            G, _, _, _ = gravity_share_for_month(tipo, mes, row_share, col_share, costs)
            seed = PESO_HISTORICO[tipo] * S + PESO_GRAVITACIONAL[tipo] * G
            est, _, _, _ = ipf(seed, total_obs * row_share.to_numpy(dtype=float, copy=True), total_obs * col_share.to_numpy(dtype=float, copy=True))
            rows.append({"mes": mes, "tipo_pasajero": tipo, "modelo": "hibrido_historico_gravitacional", **metrics(obs, est)})
    return pd.DataFrame(rows)


def historical_od_share_excluding_year(mats: dict, tipo: str, mes: int, exclude_year: int):
    block = TIPOS_BLOQUES[tipo]
    years = sorted(k[0] for k in mats if k[1] == int(mes) and k[2] == block and k[0] != int(exclude_year))
    weights = year_weights_for_month(years)
    if not weights:
        raise ValueError(f"No hay años disponibles para validar {tipo}, mes {mes} excluyendo {exclude_year}.")
    M = None
    for y, w in weights.items():
        k_ = (y, int(mes), block)
        if k_ in mats:
            M = mats[k_].astype(float) * w if M is None else M + mats[k_].astype(float) * w
    total = float(M.to_numpy().sum())
    S = M / total if total > 0 else M * 0.0
    return S, S.sum(axis=1), S.sum(axis=0), pd.DataFrame([{"anio_base": y, "peso": w} for y, w in weights.items()])


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------

def exportar_excel_matrices(resultado: dict, path: Path):
    station_order = resultado["station_order"]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        resultado["resumen"].to_excel(writer, sheet_name="Resumen_Mensual_Tipo", index=False)
        resultado["type_shares"].to_excel(writer, sheet_name="Factores_Tipo_Pasajero", index=False)
        pd.DataFrame({"orden": range(1, len(station_order) + 1), "estacion": station_order}).to_excel(writer, sheet_name="Orden_Estaciones", index=False)
        resultado["validacion_datos"].to_excel(writer, sheet_name="Validacion_Datos", index=False)
        validar_hibrido_2026().to_excel(writer, sheet_name="Validacion_Hibrida", index=False)
        pd.DataFrame([
            {"tipo_pasajero": t, "peso_historico": PESO_HISTORICO[t], "peso_gravitacional": PESO_GRAVITACIONAL[t], "alpha_tarifa": ALPHA_TARIFA, "beta_distancia": BETA_DISTANCIA, "lambda": LAMBDA, "funcion": FUNCION_IMPEDANCIA}
            for t in TIPOS
        ]).to_excel(writer, sheet_name="Parametros_OD", index=False)
        # Matrices de viajes e ingresos por mes/tipo. Nombres cortos por límite de Excel.
        for periodo in [f"2027-{m:02d}" for m in range(1, 13)]:
            for tipo in TIPOS:
                suf = {"Normal": "Norm", "Estudiante": "Est", "Adulto Mayor": "AM"}[tipo]
                V = resultado["matrices_viajes"][(periodo, tipo)].reindex(index=station_order, columns=station_order)
                R = resultado["matrices_ingresos"][(periodo, tipo)].reindex(index=station_order, columns=station_order)
                V.to_excel(writer, sheet_name=f"{periodo[-2:]}_{suf}_Viajes")
                R.to_excel(writer, sheet_name=f"{periodo[-2:]}_{suf}_Ingresos")


def generar_salidas_od_2027(serie_biotren: pd.Series | None = None):
    if serie_biotren is None:
        proy = pd.read_csv(OUT / "proyeccion_2027_resumen_mensual_elastico.csv", index_col=0)
        serie_biotren = proy["BIOTREN"]
    resultado = distribuir_proyeccion_biotren(serie_biotren)
    OD_OUT.mkdir(parents=True, exist_ok=True)
    resultado["viajes_long"].to_csv(OD_OUT / "od_2027_viajes_por_tipo_long.csv", index=False)
    resultado["ingresos_long"].to_csv(OD_OUT / "od_2027_ingresos_por_tipo_long.csv", index=False)
    resultado["resumen"].to_csv(OD_OUT / "resumen_mensual_tipo_pasajero_ingresos.csv", index=False)
    resultado["type_shares"].to_csv(OD_OUT / "factores_tipo_pasajero_mensuales.csv", index=False)
    resultado["factores_od"].to_csv(OD_OUT / "factores_od_hibridos_mensuales.csv", index=False)
    resultado["pesos_historicos"].to_csv(OD_OUT / "pesos_historicos_utilizados.csv", index=False)
    validar_hibrido_2026().to_csv(OD_OUT / "validacion_od_hibrida_tipo_pasajero.csv", index=False)
    pd.DataFrame({"orden": range(1, len(resultado["station_order"]) + 1), "estacion": resultado["station_order"]}).to_csv(OD_OUT / "orden_estaciones_original.csv", index=False)
    # Tarifas y distancias en formato largo para auditoría.
    for tipo, M in resultado["tarifas"].items():
        M.stack().reset_index(name="tarifa_2026").rename(columns={"level_0": "origen", "level_1": "destino"}).to_csv(OD_OUT / f"tarifa_2026_{tipo.replace(' ', '_').lower()}.csv", index=False)
    resultado["distancias"].stack().reset_index(name="distancia_km").rename(columns={"level_0": "origen", "level_1": "destino"}).to_csv(OD_OUT / "distancia_biotren_km_long.csv", index=False)

    # Validación de cobertura de tarifa y distancia sobre pares OD proyectados.
    val_rows = []
    viajes_total = resultado["viajes_long"].copy()
    for tipo, tarifa in resultado["tarifas"].items():
        vtipo = viajes_total[viajes_total["tipo_pasajero"] == tipo].groupby(["origen", "destino"], as_index=False)["viajes_proyectados"].sum()
        for _, row in vtipo.iterrows():
            o, d = row["origen"], row["destino"]
            viajes = float(row["viajes_proyectados"])
            fare_val = float(tarifa.loc[o, d]) if o in tarifa.index and d in tarifa.columns else 0.0
            dist_val = float(resultado["distancias"].loc[o, d]) if o in resultado["distancias"].index and d in resultado["distancias"].columns else 0.0
            if viajes > 0 and (fare_val <= 0 or dist_val < 0):
                val_rows.append({"tipo_pasajero": tipo, "origen": o, "destino": d, "viajes_2027": viajes, "tarifa_2026": fare_val, "distancia_km": dist_val, "observacion": "Par OD con viajes proyectados y tarifa/distancia no positiva"})
    if not val_rows:
        val_rows.append({"tipo_pasajero": "Todos", "origen": "-", "destino": "-", "viajes_2027": 0, "tarifa_2026": None, "distancia_km": None, "observacion": "No se detectaron pares OD proyectados con tarifa o distancia faltante/no positiva."})
    pd.DataFrame(val_rows).to_csv(OD_OUT / "validacion_cobertura_tarifa_distancia.csv", index=False)

    exportar_excel_matrices(resultado, OD_OUT / "od_biotren_2027_hibrido_por_tipo.xlsx")
    return resultado


if __name__ == "__main__":
    res = generar_salidas_od_2027()
    print(res["resumen"].groupby("tipo_pasajero")[["viajes_tipo_proyectados", "ingresos_tipo_proyectados"]].sum().round(0).to_string())
