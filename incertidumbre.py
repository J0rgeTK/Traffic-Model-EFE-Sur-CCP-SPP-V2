"""Bandas de incertidumbre diagnósticas derivadas del backtesting.

Las bandas se calculan en memoria desde la proyección base vigente y las métricas
retrospectivas del backtesting. No recalibran ni reemplazan el escenario base.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IncertidumbreResult:
    mensual: pd.DataFrame
    anual: pd.DataFrame
    advertencias: list[str]


def _metricas_por_servicio(metricas_servicio: pd.DataFrame) -> pd.DataFrame:
    required = {"servicio", "WMAPE", "sesgo"}
    missing = required - set(metricas_servicio.columns)
    if missing:
        raise ValueError(f"metricas_servicio no contiene columnas requeridas: {sorted(missing)}")
    out = metricas_servicio[["servicio", "WMAPE", "sesgo"]].copy()
    out["WMAPE"] = pd.to_numeric(out["WMAPE"], errors="coerce") / 100.0
    out["sesgo"] = pd.to_numeric(out["sesgo"], errors="coerce") / 100.0
    return out


def calcular_bandas_incertidumbre(proyeccion_base_servicios: pd.DataFrame, metricas_servicio: pd.DataFrame,
                                  contribucion_servicio: pd.DataFrame | None = None,
                                  piso_minimo: float = 0.0,
                                  umbral_wmape_alto: float = 0.25) -> IncertidumbreResult:
    """Calcula bandas diagnósticas por servicio y mes.

    Fórmulas:
    - escenario_base = proyección vigente.
    - banda_baja_wmape = max(piso, base * (1 - WMAPE_servicio)).
    - banda_alta_wmape = max(piso, base * (1 + WMAPE_servicio)).
    - escenario_ajustado_sesgo = max(piso, base * (1 - sesgo_servicio)).
    """
    base = proyeccion_base_servicios.copy()
    base.index = base.index.astype(str)
    mensual = base.reset_index(names="periodo").melt(id_vars="periodo", var_name="servicio", value_name="escenario_base")
    mensual["escenario_base"] = pd.to_numeric(mensual["escenario_base"], errors="coerce").fillna(0.0)

    metricas = _metricas_por_servicio(metricas_servicio)
    servicios_base = set(mensual["servicio"].astype(str))
    servicios_metricas = set(metricas["servicio"].astype(str))
    missing_metrics = sorted(servicios_base - servicios_metricas)
    if missing_metrics:
        raise ValueError(f"Faltan métricas de backtesting para servicios: {missing_metrics}")

    mensual = mensual.merge(metricas, on="servicio", how="left")
    mensual["banda_baja_wmape"] = (mensual["escenario_base"] * (1.0 - mensual["WMAPE"])).clip(lower=piso_minimo)
    mensual["banda_alta_wmape"] = (mensual["escenario_base"] * (1.0 + mensual["WMAPE"])).clip(lower=piso_minimo)
    mensual["escenario_ajustado_sesgo"] = (mensual["escenario_base"] * (1.0 - mensual["sesgo"])).clip(lower=piso_minimo)
    mensual["WMAPE_usado"] = mensual["WMAPE"] * 100.0
    mensual["sesgo_usado"] = mensual["sesgo"] * 100.0

    anual = (mensual.groupby("servicio", as_index=False)
             .agg(total_base=("escenario_base", "sum"),
                  total_banda_baja=("banda_baja_wmape", "sum"),
                  total_banda_alta=("banda_alta_wmape", "sum"),
                  total_ajustado_sesgo=("escenario_ajustado_sesgo", "sum"),
                  WMAPE_usado=("WMAPE_usado", "first"),
                  sesgo_usado=("sesgo_usado", "first")))

    contrib = None
    if contribucion_servicio is not None and not contribucion_servicio.empty:
        cols = ["servicio", "contribucion_error_total_sistema"]
        if set(cols).issubset(contribucion_servicio.columns):
            contrib = contribucion_servicio[cols].copy()
            anual = anual.merge(contrib, on="servicio", how="left")
    if "contribucion_error_total_sistema" not in anual.columns:
        anual["contribucion_error_total_sistema"] = np.nan

    def _advertencia(row: pd.Series) -> str:
        mensajes = ["Bandas diagnósticas derivadas de backtesting; no son intervalos estadísticos formales."]
        if row["WMAPE_usado"] >= umbral_wmape_alto * 100.0:
            mensajes.append("WMAPE histórico sobre 25%; usar banda amplia y escenarios alternativos.")
        if row["servicio"] == "TREN_ARAUCANIA" and row["sesgo_usado"] > 25.0:
            mensajes.append("Advertencia especial: alto sesgo positivo en Tren Araucanía; riesgo de sobreestimación.")
        if row["servicio"] == "BIOTREN" and pd.notna(row.get("contribucion_error_total_sistema")) and row["contribucion_error_total_sistema"] >= 0.5:
            mensajes.append("Advertencia especial: Biotren concentra alta contribución al error absoluto total del sistema.")
        return " ".join(mensajes)

    anual["advertencia_metodologica"] = anual.apply(_advertencia, axis=1)
    mensual = mensual[["periodo", "servicio", "escenario_base", "banda_baja_wmape", "banda_alta_wmape",
                       "escenario_ajustado_sesgo", "WMAPE_usado", "sesgo_usado"]]
    anual = anual.sort_values("WMAPE_usado", ascending=False).reset_index(drop=True)
    advertencias = [
        "Las bandas se derivan del backtesting retrospectivo diagnóstico no holdout.",
        "No son intervalos de confianza ni predicción estadísticos formales.",
        "No reemplazan ni recalibran el escenario base 2027 vigente.",
        "El ajuste por sesgo es sólo una referencia diagnóstica de sensibilidad.",
    ]
    return IncertidumbreResult(mensual=mensual, anual=anual, advertencias=advertencias)
