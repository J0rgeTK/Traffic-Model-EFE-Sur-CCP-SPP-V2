"""
od_laja_talcahuano.py

Distribución matricial OD para el servicio Laja-Talcahuano.

Metodología implementada:
- La proyección mensual del modelo principal define el total de afluencia del servicio.
- Las MOD observadas 2024 distribuyen ese total por tipo de pasajero y par Origen-Destino.
- La redistribución conserva exactamente el total mensual proyectado.
- La matriz tarifaria 2026 EFESUR se aplica por tipo de pasajero y OD para estimar venta de pasajes.
- Para la categoría ida_y_vuelta, la tarifa comercial ida-vuelta se imputa al viaje transportado con factor 0,5.
- No se calculan subsidios, porque Laja-Talcahuano no usa subsidio por pasajero transportado en este modelo.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import math
import re
import unicodedata
from typing import Dict, Iterable

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA = BASE_DIR / "data"
PROCESSED = DATA / "od_laja_talcahuano" / "processed"

CAPACIDAD_TREN_LAJA_TALCAHUANO = 578.0

TIPOS_PASAJERO_LAJA = [
    "normal",
    "adulto_mayor",
    "discapacitado",
    "delegacion",
    "ida_y_vuelta",
    "estudiante_media_superior",
    "estudiante_basica",
    "funcionario",
]

PROCESSED_FILES = {
    "orden_estaciones": PROCESSED / "orden_estaciones_laja_talcahuano.csv",
    "mod_historica": PROCESSED / "mod_laja_talcahuano_2024_long.csv",
    "participacion_tipo": PROCESSED / "participacion_mensual_tipo_pasajero.csv",
    "participacion_od": PROCESSED / "participacion_od_tipo_pasajero_mensual.csv",
    "tarifas": PROCESSED / "tarifa_laja_talcahuano_2026_long.csv",
    "mapeo_tipo": PROCESSED / "mapeo_tipo_pasajero_laja.csv",
    "validacion_mod": PROCESSED / "validacion_extraccion_mod_laja.csv",
    "validacion_tarifa": PROCESSED / "validacion_cobertura_tarifa_laja.csv",
}


def strip_accents(s) -> str:
    s = "" if s is None else str(s).strip()
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def key(s) -> str:
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()



def factor_imputacion_tarifa(tipo_pasajero: str) -> float:
    """Factor para convertir tarifa comercial en tarifa imputable por viaje transportado.

    La MOD Laja-Talcahuano representa afluencia/viajes transportados. Por ello,
    una tarifa comercial ida-vuelta debe imputarse como media tarifa por viaje.
    """
    return 0.5 if str(tipo_pasajero) == "ida_y_vuelta" else 1.0

def _periodo_a_mes(periodo) -> int:
    txt = str(periodo)
    if "-" in txt and len(txt) >= 7:
        return int(txt[5:7])
    return int(periodo)


@lru_cache(maxsize=1)
def cargar_insumos_laja() -> Dict[str, pd.DataFrame]:
    faltantes = [str(p) for p in PROCESSED_FILES.values() if not p.exists()]
    if faltantes:
        raise FileNotFoundError("Faltan archivos procesados OD Laja-Talcahuano: " + "; ".join(faltantes))
    data = {
        nombre: pd.read_csv(path)
        for nombre, path in PROCESSED_FILES.items()
    }
    for col in ["viajes_observados", "participacion_tipo_mes", "participacion_od_tipo_mes", "tarifa"]:
        for df in data.values():
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return data


def estaciones_laja() -> list[str]:
    ins = cargar_insumos_laja()
    return ins["orden_estaciones"].sort_values("orden")["estacion"].astype(str).tolist()


def _participacion_tipo_mes(mes: int) -> pd.DataFrame:
    ins = cargar_insumos_laja()
    p = ins["participacion_tipo"].copy()
    d = p[p["mes"].astype(int).eq(int(mes))].copy()
    if d.empty:
        # fallback anual ponderado por tipo
        d = p.groupby(["tipo_pasajero", "nombre_visual"], as_index=False).agg(viajes_tipo_mes=("viajes_tipo_mes", "sum"))
        total = float(d["viajes_tipo_mes"].sum())
        d["total_mes"] = total
        d["participacion_tipo_mes"] = d["viajes_tipo_mes"] / total if total else 0.0
    s = float(d["participacion_tipo_mes"].sum())
    if s > 0:
        d["participacion_tipo_mes"] = d["participacion_tipo_mes"] / s
    return d[["tipo_pasajero", "nombre_visual", "participacion_tipo_mes"]]


def _participacion_od_mes_tipo(mes: int, tipo_pasajero: str) -> pd.DataFrame:
    ins = cargar_insumos_laja()
    p = ins["participacion_od"].copy()
    d = p[p["mes"].astype(int).eq(int(mes)) & p["tipo_pasajero"].eq(tipo_pasajero)].copy()
    if d.empty:
        # fallback anual por tipo
        d = p[p["tipo_pasajero"].eq(tipo_pasajero)].groupby(
            ["tipo_pasajero", "nombre_visual", "origen", "destino"], as_index=False
        ).agg(viajes_observados=("viajes_observados", "sum"))
        total = float(d["viajes_observados"].sum())
        d["participacion_od_tipo_mes"] = d["viajes_observados"] / total if total else 0.0
    total_part = float(d["participacion_od_tipo_mes"].sum())
    if total_part > 0:
        d["participacion_od_tipo_mes"] = d["participacion_od_tipo_mes"] / total_part
    return d[["tipo_pasajero", "nombre_visual", "origen", "destino", "participacion_od_tipo_mes"]]


def distribuir_laja_talcahuano_mes(periodo, afluencia_mensual: float) -> Dict[str, pd.DataFrame | dict]:
    """Distribuye una afluencia mensual proyectada por tipo de pasajero y OD.

    La suma de `viajes_proyectados` se ajusta de forma proporcional para conservar
    exactamente `afluencia_mensual` ante diferencias menores de redondeo.
    """
    mes = _periodo_a_mes(periodo)
    total_mes = float(afluencia_mensual or 0.0)
    tipo_share = _participacion_tipo_mes(mes)
    filas = []
    for _, tipo_row in tipo_share.iterrows():
        tipo = tipo_row["tipo_pasajero"]
        nombre = tipo_row["nombre_visual"]
        total_tipo = total_mes * float(tipo_row["participacion_tipo_mes"])
        od = _participacion_od_mes_tipo(mes, tipo)
        if od.empty:
            continue
        tmp = od.copy()
        tmp["periodo"] = str(periodo)
        tmp["mes"] = mes
        tmp["afluencia_mensual_proyectada"] = total_mes
        tmp["participacion_tipo_mes"] = float(tipo_row["participacion_tipo_mes"])
        tmp["viajes_tipo_proyectados"] = total_tipo
        tmp["viajes_proyectados"] = total_tipo * tmp["participacion_od_tipo_mes"].astype(float)
        tmp["nombre_visual"] = nombre
        filas.append(tmp)
    viajes = pd.concat(filas, ignore_index=True) if filas else pd.DataFrame()
    if viajes.empty:
        return {
            "viajes_od_tipo_long": viajes,
            "resumen_tipo_pasajero": pd.DataFrame(),
            "resumen_mensual": {"periodo": str(periodo), "mes": mes, "viajes_proyectados": 0.0, "ingreso_venta": 0.0, "tarifa_media": np.nan},
            "control": {"diferencia_conservacion": total_mes},
        }
    suma = float(viajes["viajes_proyectados"].sum())
    if suma > 0:
        viajes["viajes_proyectados"] = viajes["viajes_proyectados"] * (total_mes / suma)
    ins = cargar_insumos_laja()
    tarifas = ins["tarifas"][["tipo_pasajero", "origen", "destino", "tarifa", "matriz_tarifaria_aplicada"]].copy()
    viajes = viajes.merge(tarifas, on=["tipo_pasajero", "origen", "destino"], how="left")
    viajes["tarifa_comercial"] = pd.to_numeric(viajes["tarifa"], errors="coerce")
    viajes["sin_tarifa"] = viajes["tarifa_comercial"].isna()
    viajes["tarifa_comercial"] = viajes["tarifa_comercial"].fillna(0.0)
    viajes["factor_imputacion_tarifa"] = viajes["tipo_pasajero"].map(factor_imputacion_tarifa).astype(float)
    viajes["tarifa_ingreso_unitaria"] = viajes["tarifa_comercial"] * viajes["factor_imputacion_tarifa"]
    # Compatibilidad con vistas/funciones que esperaban la columna tarifa.
    viajes["tarifa"] = viajes["tarifa_ingreso_unitaria"]
    viajes["ingreso_tarifario_proyectado"] = viajes["viajes_proyectados"] * viajes["tarifa_ingreso_unitaria"]
    resumen_tipo = viajes.groupby(["periodo", "mes", "tipo_pasajero", "nombre_visual"], as_index=False).agg(
        viajes=("viajes_proyectados", "sum"),
        ingreso_venta=("ingreso_tarifario_proyectado", "sum"),
    )
    total_viajes = float(resumen_tipo["viajes"].sum())
    total_ingreso = float(resumen_tipo["ingreso_venta"].sum())
    resumen_tipo["participacion"] = resumen_tipo["viajes"] / total_viajes if total_viajes else 0.0
    resumen_tipo["tarifa_media"] = np.where(resumen_tipo["viajes"] > 0, resumen_tipo["ingreso_venta"] / resumen_tipo["viajes"], np.nan)
    resumen_mensual = {
        "periodo": str(periodo),
        "mes": mes,
        "viajes_proyectados": total_viajes,
        "ingreso_venta": total_ingreso,
        "tarifa_media": total_ingreso / total_viajes if total_viajes else np.nan,
        "od_sin_tarifa": int(viajes["sin_tarifa"].sum()),
        "factor_ida_y_vuelta": factor_imputacion_tarifa("ida_y_vuelta"),
    }
    control = {
        "periodo": str(periodo),
        "mes": mes,
        "afluencia_entrada": total_mes,
        "viajes_distribuidos": total_viajes,
        "diferencia_conservacion": total_viajes - total_mes,
        "od_sin_tarifa": int(viajes["sin_tarifa"].sum()),
    }
    return {
        "viajes_od_tipo_long": viajes,
        "resumen_tipo_pasajero": resumen_tipo,
        "resumen_mensual": resumen_mensual,
        "control": control,
    }


def calcular_resultado_laja_anual(serie_mensual) -> Dict[str, pd.DataFrame | dict]:
    serie = pd.Series(serie_mensual, dtype=float).copy()
    resultados = [distribuir_laja_talcahuano_mes(periodo, valor) for periodo, valor in serie.items()]
    viajes = pd.concat([r["viajes_od_tipo_long"] for r in resultados if not r["viajes_od_tipo_long"].empty], ignore_index=True)
    resumen_tipo = pd.concat([r["resumen_tipo_pasajero"] for r in resultados if not r["resumen_tipo_pasajero"].empty], ignore_index=True)
    control = pd.DataFrame([r["control"] for r in resultados])
    resumen_mensual = pd.DataFrame([r["resumen_mensual"] for r in resultados])
    resumen_anual_tipo = resumen_tipo.groupby(["tipo_pasajero", "nombre_visual"], as_index=False).agg(
        viajes=("viajes", "sum"),
        ingreso_venta=("ingreso_venta", "sum"),
    )
    total_viajes = float(resumen_anual_tipo["viajes"].sum())
    total_ingreso = float(resumen_anual_tipo["ingreso_venta"].sum())
    resumen_anual_tipo["participacion"] = resumen_anual_tipo["viajes"] / total_viajes if total_viajes else 0.0
    resumen_anual_tipo["tarifa_media"] = np.where(resumen_anual_tipo["viajes"] > 0, resumen_anual_tipo["ingreso_venta"] / resumen_anual_tipo["viajes"], np.nan)
    resumen_anual_tipo = resumen_anual_tipo.sort_values("viajes", ascending=False)
    resumen_anual = {
        "viajes_laja_talcahuano": total_viajes,
        "ingreso_venta": total_ingreso,
        "tarifa_media": total_ingreso / total_viajes if total_viajes else np.nan,
        "subsidio_total": 0.0,
        "ingreso_total": total_ingreso,
        "observacion_subsidio": "No aplica subsidio por pasajero transportado para Laja-Talcahuano en este modelo.",
        "observacion_tarifa_ida_y_vuelta": "La tarifa comercial ida-vuelta se imputa con factor 0,5 por tratarse de viajes transportados.",
    }
    return {
        "viajes_od_tipo_long": viajes,
        "resumen_tipo_pasajero": resumen_tipo,
        "resumen_anual_tipo_pasajero": resumen_anual_tipo,
        "resumen_mensual": resumen_mensual,
        "resumen_anual": resumen_anual,
        "control_conservacion": control,
    }


def matriz_od(viajes_long: pd.DataFrame, tipo_pasajero: str | None = None, periodo: str | None = None, valor_col: str = "viajes_proyectados") -> pd.DataFrame:
    d = viajes_long.copy()
    if tipo_pasajero:
        d = d[d["tipo_pasajero"].eq(tipo_pasajero)]
    if periodo:
        d = d[d["periodo"].astype(str).eq(str(periodo))]
    estaciones = estaciones_laja()
    if d.empty:
        return pd.DataFrame(0.0, index=estaciones, columns=estaciones)
    piv = d.pivot_table(index="origen", columns="destino", values=valor_col, aggfunc="sum", fill_value=0.0)
    return piv.reindex(index=estaciones, columns=estaciones, fill_value=0.0)


def ocupacion_laja_talcahuano_mensual(serie_mensual, servicios_mensuales) -> pd.DataFrame:
    serie = pd.Series(serie_mensual, dtype=float).copy()
    servicios = pd.Series(servicios_mensuales, dtype=float).reindex(serie.index).fillna(0.0)
    capacidad = servicios * CAPACIDAD_TREN_LAJA_TALCAHUANO
    out = pd.DataFrame({
        "periodo": serie.index.astype(str),
        "mes": [ _periodo_a_mes(p) for p in serie.index ],
        "afluencia": serie.values,
        "servicios_comerciales": servicios.values,
        "capacidad_pax": capacidad.values,
    })
    out["pax_servicio"] = np.where(out["servicios_comerciales"] > 0, out["afluencia"] / out["servicios_comerciales"], np.nan)
    out["ocupacion_pct"] = np.where(out["capacidad_pax"] > 0, out["afluencia"] / out["capacidad_pax"], np.nan)
    out["capacidad_referencia_tren"] = CAPACIDAD_TREN_LAJA_TALCAHUANO
    return out
