"""Distribución OD e ingresos/subsidios para Tren Araucanía.

El módulo replica la lógica conservativa usada en Biotren/Laja:
la proyección mensual del modelo fija el total de pasajeros y la MOD histórica
solo distribuye ese total por tipo de pasajero y par OD.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Mapping

import pandas as pd

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data", "od_tren_araucania", "processed")
TASA_DESCUENTO_NORMAL = 0.127

TIPOS_PASAJERO_ESPERADOS = [
    "normal",
    "adulto_mayor",
    "estudiante",
    "claret",
    "delegacion",
    "discapacitado",
    "estudiante_basica",
    "funcionario",
    "sindicato",
]


@lru_cache(maxsize=1)
def cargar_participacion_tipo() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, "participacion_mensual_tipo_pasajero_tren_araucania.csv"))


@lru_cache(maxsize=1)
def cargar_participacion_od() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, "participacion_od_tipo_pasajero_mensual_tren_araucania.csv"))


@lru_cache(maxsize=1)
def cargar_tarifas() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, "tarifa_tren_araucania_2026_long.csv"))


@lru_cache(maxsize=1)
def cargar_mapeo_tipo_pasajero() -> pd.DataFrame:
    return pd.read_csv(os.path.join(DATA_DIR, "mapeo_tipo_pasajero_tren_araucania.csv"))


@lru_cache(maxsize=1)
def cargar_orden_estaciones() -> list[str]:
    df = pd.read_csv(os.path.join(DATA_DIR, "orden_estaciones_tren_araucania.csv"))
    return df.sort_values("orden")["estacion"].astype(str).tolist()


def _periodo_a_mes(periodo) -> int:
    s = str(periodo)
    if len(s) >= 7 and s[4] == "-":
        return int(s[5:7])
    return int(periodo)


def distribuir_mes(periodo, afluencia_mes: float) -> dict[str, pd.DataFrame | dict]:
    """Distribuye un mes proyectado por tipo de pasajero y OD.

    Retorna detalle OD con venta, subsidio normal, subsidio estudiante e ingreso total.
    """
    mes = _periodo_a_mes(periodo)
    afluencia_mes = float(afluencia_mes)
    tipo = cargar_participacion_tipo()
    od = cargar_participacion_od()
    reglas = cargar_mapeo_tipo_pasajero()
    tarifas = cargar_tarifas()

    tipo_m = tipo[tipo["mes"].astype(int).eq(mes)].copy()
    od_m = od[od["mes"].astype(int).eq(mes)].copy()
    if tipo_m.empty or od_m.empty:
        raise ValueError(f"No hay MOD base para mes {mes}")

    # Total por tipo proyectado.
    tipo_m["afluencia_mes_proyectada"] = afluencia_mes
    tipo_m["viajes_tipo_proyectados"] = afluencia_mes * tipo_m["participacion_tipo_mes"].astype(float)

    detalle = od_m.merge(
        tipo_m[["mes", "tipo_pasajero", "viajes_tipo_proyectados", "participacion_tipo_mes"]],
        on=["mes", "tipo_pasajero"],
        how="left",
    )
    detalle["periodo"] = str(periodo)
    detalle["viajes_proyectados"] = (
        detalle["viajes_tipo_proyectados"].astype(float)
        * detalle["participacion_od_tipo_mes"].astype(float)
    )

    detalle = detalle.merge(reglas, on=["tipo_pasajero", "tipo_pasajero_visual"], how="left")

    # Tarifa de venta según regla de tipo pasajero.
    tarifa_venta = tarifas.rename(
        columns={"tipo_tarifa": "tipo_tarifa_venta", "tarifa": "tarifa_venta_base"}
    )
    detalle = detalle.merge(
        tarifa_venta,
        on=["tipo_tarifa_venta", "origen", "destino"],
        how="left",
    )

    # Tarifa normal para base de subsidio normal.
    # Esta base puede diferir de la venta: Delegación paga 70% en venta,
    # mientras el subsidio normal se calcula sobre tarifa normal completa;
    # Discapacitado, Funcionario y Sindicato no generan venta, pero sí integran
    # la base normal de subsidio por instrucción metodológica.
    tarifa_normal_subsidio = tarifas[tarifas["tipo_tarifa"].eq("normal")].copy()
    tarifa_normal_subsidio = tarifa_normal_subsidio.rename(columns={"tarifa": "tarifa_normal_subsidio_base"})
    tarifa_normal_subsidio = tarifa_normal_subsidio.drop(columns=["tipo_tarifa"])
    detalle = detalle.merge(tarifa_normal_subsidio, on=["origen", "destino"], how="left")

    # Tarifas estudiante para base de subsidio estudiantil.
    # La base de subsidio se calcula con matrices propias, no con la venta directa.
    # Esto permite que Estudiante Básica pueda no generar venta, pero sí formar parte
    # de la base estudiante con subsidio y sin subsidio.
    tarifa_est_con = tarifas[tarifas["tipo_tarifa"].eq("estudiante")].copy()
    tarifa_est_con = tarifa_est_con.rename(columns={"tarifa": "tarifa_estudiante_con_subsidio"})
    tarifa_est_con = tarifa_est_con.drop(columns=["tipo_tarifa"])
    detalle = detalle.merge(tarifa_est_con, on=["origen", "destino"], how="left")

    tarifa_sin = tarifas[tarifas["tipo_tarifa"].eq("estudiante_sin_subsidio")].copy()
    tarifa_sin = tarifa_sin.rename(columns={"tarifa": "tarifa_estudiante_sin_subsidio"})
    tarifa_sin = tarifa_sin.drop(columns=["tipo_tarifa"])
    detalle = detalle.merge(tarifa_sin, on=["origen", "destino"], how="left")

    for col in ["factor_venta", "paga_tarifa", "aplica_subsidio_normal", "aplica_subsidio_estudiante"]:
        detalle[col] = detalle[col].fillna(0).astype(float)
    detalle["tarifa_venta_base"] = detalle["tarifa_venta_base"].fillna(0).astype(float)
    detalle["tarifa_normal_subsidio_base"] = detalle["tarifa_normal_subsidio_base"].fillna(0).astype(float)
    detalle["tarifa_estudiante_con_subsidio"] = detalle["tarifa_estudiante_con_subsidio"].fillna(0).astype(float)
    detalle["tarifa_estudiante_sin_subsidio"] = detalle["tarifa_estudiante_sin_subsidio"].fillna(0).astype(float)

    detalle["tarifa_pagada"] = detalle["tarifa_venta_base"] * detalle["factor_venta"]
    detalle.loc[detalle["paga_tarifa"].eq(0), "tarifa_pagada"] = 0.0
    detalle["ingreso_venta"] = detalle["viajes_proyectados"] * detalle["tarifa_pagada"]

    # Subsidio normal: misma lógica de Biotren, pero con tasa 12,7%.
    # El grupo normal de subsidio incluye normal, discapacitado, funcionario, sindicato y delegación.
    detalle["monto_base_subsidio_normal"] = (
        detalle["viajes_proyectados"]
        * detalle["tarifa_normal_subsidio_base"]
        * detalle["aplica_subsidio_normal"]
    )
    detalle["subsidio_normal"] = (
        detalle["monto_base_subsidio_normal"] / (1.0 - TASA_DESCUENTO_NORMAL)
        - detalle["monto_base_subsidio_normal"]
    )

    # Subsidio estudiante: Estudiante, Claret y Estudiante Básica.
    # La base de subsidio no es necesariamente igual a la venta de pasajes.
    # Se calcula como diferencia entre matriz estudiante sin subsidio y matriz estudiante con subsidio,
    # aplicada sobre la matriz de viajes del grupo estudiantil de subsidio.
    detalle["ingreso_teorico_estudiante_sin_subsidio"] = (
        detalle["viajes_proyectados"]
        * detalle["tarifa_estudiante_sin_subsidio"]
        * detalle["aplica_subsidio_estudiante"]
    )
    detalle["base_estudiante_con_subsidio"] = (
        detalle["viajes_proyectados"]
        * detalle["tarifa_estudiante_con_subsidio"]
        * detalle["aplica_subsidio_estudiante"]
    )
    detalle["venta_base_estudiante_subsidio"] = detalle["base_estudiante_con_subsidio"]
    detalle["subsidio_estudiante"] = (
        detalle["ingreso_teorico_estudiante_sin_subsidio"]
        - detalle["base_estudiante_con_subsidio"]
    )

    detalle["subsidio_total"] = detalle["subsidio_normal"] + detalle["subsidio_estudiante"]
    detalle["ingreso_total"] = detalle["ingreso_venta"] + detalle["subsidio_total"]

    resumen_tipo = (
        detalle.groupby(["tipo_pasajero", "tipo_pasajero_visual"], as_index=False)
        .agg(
            viajes=("viajes_proyectados", "sum"),
            ingreso_venta=("ingreso_venta", "sum"),
            monto_base_subsidio_normal=("monto_base_subsidio_normal", "sum"),
            ingreso_teorico_estudiante_sin_subsidio=("ingreso_teorico_estudiante_sin_subsidio", "sum"),
            venta_base_estudiante_subsidio=("venta_base_estudiante_subsidio", "sum"),
            subsidio_normal=("subsidio_normal", "sum"),
            subsidio_estudiante=("subsidio_estudiante", "sum"),
            subsidio_total=("subsidio_total", "sum"),
            ingreso_total=("ingreso_total", "sum"),
        )
    )
    resumen_tipo["participacion"] = resumen_tipo["viajes"] / max(float(resumen_tipo["viajes"].sum()), 1.0)

    resumen = {
        "periodo": str(periodo),
        "mes": mes,
        "viajes_tren_araucania": float(detalle["viajes_proyectados"].sum()),
        "ingreso_venta": float(detalle["ingreso_venta"].sum()),
        "monto_base_subsidio_normal": float(detalle["monto_base_subsidio_normal"].sum()),
        "viajes_base_subsidio_normal": float(detalle.loc[detalle["aplica_subsidio_normal"].eq(1), "viajes_proyectados"].sum()),
        "ingreso_teorico_estudiante_sin_subsidio": float(detalle["ingreso_teorico_estudiante_sin_subsidio"].sum()),
        "venta_base_estudiante_subsidio": float(detalle["venta_base_estudiante_subsidio"].sum()),
        "viajes_base_subsidio_estudiante": float(detalle.loc[detalle["aplica_subsidio_estudiante"].eq(1), "viajes_proyectados"].sum()),
        "subsidio_normal": float(detalle["subsidio_normal"].sum()),
        "subsidio_estudiante": float(detalle["subsidio_estudiante"].sum()),
        "subsidio_total": float(detalle["subsidio_total"].sum()),
        "ingreso_total_tren_araucania": float(detalle["ingreso_total"].sum()),
        "tarifa_media_venta": float(detalle["ingreso_venta"].sum() / max(detalle["viajes_proyectados"].sum(), 1.0)),
        "tarifa_media_total": float(detalle["ingreso_total"].sum() / max(detalle["viajes_proyectados"].sum(), 1.0)),
        "diferencia_conservacion": float(detalle["viajes_proyectados"].sum() - afluencia_mes),
    }
    return {
        "viajes_long": detalle,
        "resumen_tipo_pasajero": resumen_tipo,
        "resumen_mes": resumen,
    }


def calcular_resultado_anual(serie_mensual: Mapping[str, float] | pd.Series) -> dict[str, pd.DataFrame | dict]:
    if isinstance(serie_mensual, pd.Series):
        items = serie_mensual.astype(float).to_dict().items()
    else:
        items = {str(k): float(v) for k, v in serie_mensual.items()}.items()

    detalles = []
    resumenes = []
    resumenes_tipo = []
    for periodo, valor in items:
        res = distribuir_mes(periodo, valor)
        detalles.append(res["viajes_long"])
        resumenes.append(res["resumen_mes"])
        tmp = res["resumen_tipo_pasajero"].copy()
        tmp["periodo"] = str(periodo)
        resumenes_tipo.append(tmp)

    viajes = pd.concat(detalles, ignore_index=True) if detalles else pd.DataFrame()
    resumen_mensual = pd.DataFrame(resumenes)
    resumen_tipo_mensual = pd.concat(resumenes_tipo, ignore_index=True) if resumenes_tipo else pd.DataFrame()
    resumen_tipo = (
        viajes.groupby(["tipo_pasajero", "tipo_pasajero_visual"], as_index=False)
        .agg(
            viajes=("viajes_proyectados", "sum"),
            ingreso_venta=("ingreso_venta", "sum"),
            monto_base_subsidio_normal=("monto_base_subsidio_normal", "sum"),
            ingreso_teorico_estudiante_sin_subsidio=("ingreso_teorico_estudiante_sin_subsidio", "sum"),
            venta_base_estudiante_subsidio=("venta_base_estudiante_subsidio", "sum"),
            subsidio_normal=("subsidio_normal", "sum"),
            subsidio_estudiante=("subsidio_estudiante", "sum"),
            subsidio_total=("subsidio_total", "sum"),
            ingreso_total=("ingreso_total", "sum"),
        )
        .sort_values("viajes", ascending=False)
    )
    resumen_tipo["participacion"] = resumen_tipo["viajes"] / max(float(resumen_tipo["viajes"].sum()), 1.0)

    resumen_anual = {
        "viajes_tren_araucania": float(viajes["viajes_proyectados"].sum()),
        "ingreso_venta": float(viajes["ingreso_venta"].sum()),
        "monto_base_subsidio_normal": float(viajes["monto_base_subsidio_normal"].sum()),
        "viajes_base_subsidio_normal": float(viajes.loc[viajes["aplica_subsidio_normal"].eq(1), "viajes_proyectados"].sum()),
        "ingreso_teorico_estudiante_sin_subsidio": float(viajes["ingreso_teorico_estudiante_sin_subsidio"].sum()),
        "venta_base_estudiante_subsidio": float(viajes["venta_base_estudiante_subsidio"].sum()),
        "viajes_base_subsidio_estudiante": float(viajes.loc[viajes["aplica_subsidio_estudiante"].eq(1), "viajes_proyectados"].sum()),
        "subsidio_normal": float(viajes["subsidio_normal"].sum()),
        "subsidio_estudiante": float(viajes["subsidio_estudiante"].sum()),
        "subsidio_total": float(viajes["subsidio_total"].sum()),
        "ingreso_total_tren_araucania": float(viajes["ingreso_total"].sum()),
        "tarifa_media_venta": float(viajes["ingreso_venta"].sum() / max(viajes["viajes_proyectados"].sum(), 1.0)),
        "tarifa_media_total": float(viajes["ingreso_total"].sum() / max(viajes["viajes_proyectados"].sum(), 1.0)),
        "max_diferencia_conservacion_mensual": float(resumen_mensual["diferencia_conservacion"].abs().max()) if not resumen_mensual.empty else 0.0,
    }
    return {
        "viajes_long": viajes,
        "resumen_mensual": resumen_mensual,
        "resumen_tipo_pasajero_mensual": resumen_tipo_mensual,
        "resumen_tipo_pasajero": resumen_tipo,
        "resumen_anual": resumen_anual,
    }


def matriz_tipo(viajes_long: pd.DataFrame, tipo_pasajero: str, campo: str = "viajes_proyectados") -> pd.DataFrame:
    estaciones = cargar_orden_estaciones()
    df = viajes_long[viajes_long["tipo_pasajero"].eq(tipo_pasajero)]
    if df.empty:
        return pd.DataFrame(0.0, index=estaciones, columns=estaciones)
    mat = df.pivot_table(index="origen", columns="destino", values=campo, aggfunc="sum", fill_value=0.0)
    return mat.reindex(index=estaciones, columns=estaciones, fill_value=0.0)
