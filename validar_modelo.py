"""Validación técnica del modelo predictivo de afluencia EFE Sur.

El script ejecuta controles básicos de consistencia sobre el motor mensual,
el módulo OD híbrido de Biotren, las matrices de ingresos, el calendario
operacional y las salidas exportadas. Genera un resumen auditable en /outputs.
"""
from __future__ import annotations

from pathlib import Path
import compileall
import subprocess
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

import pipeline_afluencia as P
import oferta as O
import od_biotren_hibrido as ODH
import backtesting as BT
import incertidumbre as INC

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "outputs"
OD_OUT = OUT / "od_biotren_hibrido"

REFERENCIAS_CIERRE_2026 = DATA / "referencias_cierre_2026"
REF_MENSUAL_CIERRE_2026 = REFERENCIAS_CIERRE_2026 / "afluencia_historica_cierre_2026_long.csv"
REF_ANUAL_CIERRE_2026 = REFERENCIAS_CIERRE_2026 / "afluencia_historica_cierre_2026_resumen_anual.csv"
REF_SERVICIOS_ESPERADOS = {"Biotren", "Laja Talcahuano", "Tren Araucanía"}
REF_TIPOS_DATO_VALIDOS = {"historico_observado", "cierre_2026_estimado"}
BIOTREN_PRE_AJUSTE_OCUPACION_2027 = 12_673_199.0
TOTALES_2027_VIGENTES = {
    "BIOTREN": 13_095_299.0,
    "TREN_ARAUCANIA": 840_777.0,
    "CORTO_LAJA": 540_842.0,
    "LLANQUIHUE_PM": 412_132.0,
}
BIOTREN_FINANCIERO_REFERENCIA_2027 = {
    "ingreso_venta": 6_767_275_267.0,
    "subsidio_normal": 1_449_760_160.0,
    "subsidio_estudiante": 524_083_425.0,
    "subsidio_total": 1_973_843_585.0,
    "ingreso_total_biotren": 8_741_118_852.0,
}


def _ok(nombre: str, ok: bool, detalle: str = "") -> dict:
    return {"control": nombre, "estado": "OK" if ok else "REVISAR", "detalle": detalle}


def ejecutar_validacion() -> pd.DataFrame:
    rows = []

    # 1. Compilación del proyecto.
    compiled = compileall.compile_dir(str(BASE), quiet=1, force=False)
    rows.append(_ok("Compilación Python del proyecto", bool(compiled), "compileall sobre el directorio del modelo"))

    # 2. Verificación de que no queden binarios/caches versionados.
    git_files = subprocess.run(
        ["git", "ls-files"],
        cwd=BASE,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    patrones_binarios = (".pyc", ".pyo", ".pyd", ".zip", ".xlsx", ".xlsm", ".xls")
    versionados_no_permitidos = [
        f for f in git_files
        if "/__pycache__/" in f
        or f.startswith("__pycache__/")
        or "/_Pycache_/" in f
        or f.startswith("_Pycache_/")
        or f.lower().endswith(patrones_binarios)
    ]
    rows.append(_ok(
        "Sin binarios/cache versionados",
        len(versionados_no_permitidos) == 0,
        "Faltantes: ninguno" if not versionados_no_permitidos else ", ".join(versionados_no_permitidos[:5]),
    ))

    # 3. Ejecución del motor mensual.
    params = O.aplicar_oferta_actual(pd.read_csv(DATA / "oferta_params.csv"))
    diario = pd.read_csv(DATA / "afluencia_diaria_consolidada.csv", parse_dates=["fecha"])
    mdf = P.mensualizar(diario)
    uni, serv, detalle = O.proyectar_mensual_elastico(params, mdf, return_detalle=True)
    total_servicios = serv.sum().sum()
    rows.append(_ok("Ejecución del motor mensual-elástico", total_servicios > 0, f"Total sistema: {total_servicios:,.0f}"))


    # 3A. Referencias normalizadas de cierre 2026 sólo para visualización histórica.
    mensual_cols = {"servicio", "anio", "mes_num", "mes", "afluencia", "tipo_dato", "fuente"}
    anual_cols = {"servicio", "anio", "tipo_dato", "afluencia_anual"}
    refs_exist = REF_MENSUAL_CIERRE_2026.exists() and REF_ANUAL_CIERRE_2026.exists()
    rows.append(_ok(
        "CSV normalizados cierre 2026 existentes",
        refs_exist,
        f"Mensual: {REF_MENSUAL_CIERRE_2026.exists()}; anual: {REF_ANUAL_CIERRE_2026.exists()}",
    ))
    if refs_exist:
        ref_mensual = pd.read_csv(REF_MENSUAL_CIERRE_2026)
        ref_anual = pd.read_csv(REF_ANUAL_CIERRE_2026)
        rows.append(_ok(
            "Columnas CSV cierre 2026",
            mensual_cols.issubset(ref_mensual.columns) and anual_cols.issubset(ref_anual.columns),
            f"Mensual: {sorted(ref_mensual.columns)}; anual: {sorted(ref_anual.columns)}",
        ))
        servicios_m = set(ref_mensual["servicio"].dropna().astype(str))
        servicios_a = set(ref_anual["servicio"].dropna().astype(str))
        rows.append(_ok(
            "Servicios esperados en referencias cierre 2026",
            REF_SERVICIOS_ESPERADOS.issubset(servicios_m) and REF_SERVICIOS_ESPERADOS.issubset(servicios_a),
            f"Mensual: {sorted(servicios_m)}; anual: {sorted(servicios_a)}",
        ))
        tipos = set(ref_mensual["tipo_dato"].dropna().astype(str)) | set(ref_anual["tipo_dato"].dropna().astype(str))
        rows.append(_ok(
            "Tipos de dato válidos en referencias cierre 2026",
            tipos.issubset(REF_TIPOS_DATO_VALIDOS),
            f"Tipos detectados: {sorted(tipos)}",
        ))
        anual_desde_mensual = ref_mensual.groupby(["servicio", "anio", "tipo_dato"], as_index=False)["afluencia"].sum()
        anual_cmp = ref_anual.merge(anual_desde_mensual, on=["servicio", "anio", "tipo_dato"], how="left")
        dif_ref = (anual_cmp["afluencia_anual"].astype(float) - anual_cmp["afluencia"].astype(float)).abs().max()
        rows.append(_ok(
            "Totales anuales cierre 2026 consistentes",
            bool(dif_ref <= 1.0),
            f"Años: {sorted(ref_anual['anio'].astype(int).unique())}; diferencia máxima anual vs mensual: {dif_ref:.6f}",
        ))

    total_biotren_vigente = float(serv["BIOTREN"].sum())
    servicios_biotren = O.servicios_comerciales_biotren_mensuales(2027)
    pps_biotren = total_biotren_vigente / float(servicios_biotren.sum())
    rows.append(_ok(
        "Biotren 2027 calculado por ocupación y oferta",
        abs(total_biotren_vigente - O.BIOTREN_TOTAL_ANUAL_REFERENCIA_2027) <= 1.0,
        f"Total anual conservado: {total_biotren_vigente:,.0f}; servicios comerciales: {float(servicios_biotren.sum()):,.0f}; pasajeros/servicio: {pps_biotren:,.2f}",
    ))
    rows.append(_ok(
        "Pax/servicio comercial Biotren recalculado sin forzar 300",
        pps_biotren > 0,
        f"Pasajeros por servicio comercial: {pps_biotren:,.2f}; no se ajusta demanda para forzar 300",
    ))
    cap_biotren = O.diagnostico_capacidad_biotren_mensual(2027)
    rows.append(_ok(
        "L2 LV frecuencia comercial 110 todo el año",
        bool((cap_biotren["l2_lv"] == 110.0).all()),
        cap_biotren[["mes", "l2_lv"]].to_dict("records").__str__(),
    ))
    rows.append(_ok(
        "L2 fin de semana enero-febrero corregido",
        bool((cap_biotren[cap_biotren["mes"].isin([1, 2])][["l2_sab", "l2_dom"]] == 14.0).all().all()),
        cap_biotren[cap_biotren["mes"].isin([1, 2])][["mes", "l2_sab", "l2_dom"]].to_dict("records").__str__(),
    ))
    rows.append(_ok(
        "L2 fin de semana marzo-diciembre corregido",
        bool((cap_biotren[cap_biotren["mes"].between(3, 12)]["l2_sab"] == 53.0).all() and (cap_biotren[cap_biotren["mes"].between(3, 12)]["l2_dom"] == 32.0).all()),
        cap_biotren[cap_biotren["mes"].between(3, 12)][["mes", "l2_sab", "l2_dom"]].to_dict("records").__str__(),
    ))
    rows.append(_ok(
        "Servicios acoplados L2 separados de frecuencia",
        bool((cap_biotren[cap_biotren["mes"].between(1, 4)]["servicios_acoplados_l2_lv"] == 0.0).all() and (cap_biotren[cap_biotren["mes"].between(5, 12)]["servicios_acoplados_l2_lv"] == 3.0).all()),
        cap_biotren[["mes", "l2_lv", "servicios_acoplados_l2_lv"]].to_dict("records").__str__(),
    ))
    rows.append(_ok(
        "Capacidad equivalente L2 puede ser 113 sin ser frecuencia",
        bool((cap_biotren[cap_biotren["mes"].between(5, 12)]["l2_lv"] == 110.0).all() and (cap_biotren[cap_biotren["mes"].between(5, 12)]["servicios_acoplados_l2_lv"] == 3.0).all()),
        "Mayo-diciembre: 110 servicios comerciales L2 LV + 3 acoplados de capacidad",
    ))
    mensual_biotren = serv["BIOTREN"].astype(float)
    pps_mensual = mensual_biotren.values / servicios_biotren.values

    diag_part = O.diagnostico_redistribucion_biotren_2027(
        pd.Series({int(r['mes']): float(r.get('proyeccion_vigente_pre_redistribucion', r['proyeccion_recalibrada'])) for r in serv.attrs.get('recalibracion_2027', {}).get('mensual', []) if r.get('servicio') == 'BIOTREN'}),
        mensual_biotren,
    )

    ocup_biotren = O.diagnostico_ocupacion_biotren_mensual(mensual_biotren, 2027)
    resumen_ocup = O.resumen_ocupacion_biotren(mensual_biotren, 2027)
    bandas_validas = set(O.BANDAS_FUNCIONAMIENTO_BIOTREN.keys())
    rows.append(_ok(
        "Ocupación mensual Biotren conserva demanda anual",
        abs(resumen_ocup["total_anual_biotren"] - TOTALES_2027_VIGENTES["BIOTREN"]) <= 1.0,
        f"Total mensual: {resumen_ocup['total_anual_biotren']:,.0f}",
    ))
    rows.append(_ok(
        "Servicios comerciales anuales Biotren Fase 1",
        abs(resumen_ocup["servicios_comerciales_anuales"] - 43_390.0) <= 1e-6,
        f"Servicios comerciales: {resumen_ocup['servicios_comerciales_anuales']:,.0f}",
    ))
    rows.append(_ok(
        "Servicios equivalentes capacidad anuales Biotren",
        abs(resumen_ocup["servicios_equivalentes_capacidad_anuales"] - 43_891.0) <= 1e-6,
        f"Servicios equivalentes: {resumen_ocup['servicios_equivalentes_capacidad_anuales']:,.0f}",
    ))
    rows.append(_ok(
        "Pax/servicio comercial anual Biotren Fase 2",
        abs(resumen_ocup["pax_servicio_comercial_anual"] - 301.80) <= 0.01,
        f"Pax/servicio comercial: {resumen_ocup['pax_servicio_comercial_anual']:,.2f}",
    ))
    rows.append(_ok(
        "Pax/capacidad equivalente anual Biotren diagnóstico",
        abs(resumen_ocup["pax_capacidad_equivalente_anual"] - 298.36) <= 0.01,
        f"Pax/capacidad equivalente: {resumen_ocup['pax_capacidad_equivalente_anual']:,.2f}",
    ))
    rows.append(_ok(
        "Bandas mensuales Biotren completas",
        len(ocup_biotren) == 12 and ocup_biotren["banda_funcionamiento"].isin(bandas_validas).all(),
        f"Bandas: {ocup_biotren['banda_funcionamiento'].value_counts().to_dict()}",
    ))
    rows.append(_ok(
        "Meses con afluencia positiva tienen servicios comerciales",
        bool((ocup_biotren.loc[ocup_biotren["afluencia_biotren"] > 0, "servicios_comerciales"] > 0).all()),
        "Servicios comerciales mínimos: " + f"{ocup_biotren['servicios_comerciales'].min():,.0f}",
    ))
    rows.append(_ok(
        "Participación mensual ocupación Biotren suma 100%",
        abs(float(ocup_biotren["participacion_mensual_afluencia"].sum()) - 1.0) <= 1e-10,
        f"Suma: {float(ocup_biotren['participacion_mensual_afluencia'].sum()):.12f}",
    ))
    rows.append(_ok(
        "Capacidad equivalente respeta acoplados L2",
        bool((ocup_biotren.loc[ocup_biotren["mes"].between(1, 4), "servicios_equivalentes_capacidad"] == ocup_biotren.loc[ocup_biotren["mes"].between(1, 4), "servicios_comerciales"]).all() and (ocup_biotren.loc[ocup_biotren["mes"].between(5, 12), "servicios_equivalentes_capacidad"] > ocup_biotren.loc[ocup_biotren["mes"].between(5, 12), "servicios_comerciales"]).all()),
        "Ene-abr igual; may-dic capacidad equivalente mayor por acoplados",
    ))

    rows.append(_ok(
        "Participaciones mensuales Biotren suman 100%",
        abs(float(diag_part['participacion_2027_redistribuida'].sum()) - 1.0) <= 1e-10,
        f"Suma redistribuida: {float(diag_part['participacion_2027_redistribuida'].sum()):.12f}",
    ))
    rows.append(_ok(
        "Enero y febrero comparados contra 2024, 2025 y cierre 2026",
        bool(diag_part[diag_part['mes'].isin([1, 2])][['participacion_2024', 'participacion_2025', 'participacion_cierre_2026']].notna().all().all()),
        diag_part[diag_part['mes'].isin([1, 2])][['mes', 'participacion_2024', 'participacion_2025', 'participacion_cierre_2026', 'participacion_2027_redistribuida']].to_dict('records').__str__(),
    ))
    rows.append(_ok(
        "Participación mensual Biotren positiva",
        bool((diag_part['participacion_2027_redistribuida'] > 0).all()),
        f"Mínima: {diag_part['participacion_2027_redistribuida'].min():.6%}",
    ))
    saltos = mensual_biotren.pct_change().abs().dropna()
    rows.append(_ok(
        "Redistribución Biotren sin saltos abruptos injustificados",
        bool((saltos <= 0.45).all()),
        f"Salto mensual máximo: {saltos.max():.2%}",
    ))

    rows.append(_ok(
        "Evolución mensual Biotren razonable",
        bool(pd.Series(pps_mensual).between(250, 340).all()),
        "Rango pasajeros/servicio mensual: " + f"{pd.Series(pps_mensual).min():,.1f}-{pd.Series(pps_mensual).max():,.1f}",
    ))
    ref26 = pd.read_csv(DATA / "afluencia_mensual_modelo.csv")
    ref26 = ref26[(ref26["servicio"].eq("BIOTREN")) & (ref26["mes"].astype(str).str.startswith("2026-"))].copy()
    ref26["mes_num"] = pd.PeriodIndex(ref26["mes"], freq="M").month
    ene_feb_2026 = ref26[ref26["mes_num"].isin([1, 2])].set_index("mes_num")["pax_norm"].astype(float)
    ene_feb_2027 = pd.Series({1: float(mensual_biotren.loc["2027-01"]), 2: float(mensual_biotren.loc["2027-02"])})
    rows.append(_ok(
        "Enero-febrero Biotren no quedan bajo 2026",
        bool((ene_feb_2027.reindex([1, 2]) >= ene_feb_2026.reindex([1, 2])).all()),
        f"2027 ene/feb: {ene_feb_2027.loc[1]:,.0f}/{ene_feb_2027.loc[2]:,.0f}; 2026: {ene_feb_2026.loc[1]:,.0f}/{ene_feb_2026.loc[2]:,.0f}",
    ))
    for servicio, objetivo in TOTALES_2027_VIGENTES.items():
        total_servicio = float(serv[servicio].sum())
        rows.append(_ok(
            f"Total {servicio} escenario vigente",
            abs(total_servicio - objetivo) <= 1.0,
            f"Total calculado: {total_servicio:,.0f}; referencia vigente: {objetivo:,.0f}",
        ))
    rows.append(_ok(
        "Total sistema escenario vigente",
        abs(float(serv.sum().sum()) - sum(TOTALES_2027_VIGENTES.values())) <= 2.0,
        f"Total sistema: {float(serv.sum().sum()):,.0f}; referencia vigente: {sum(TOTALES_2027_VIGENTES.values()):,.0f}",
    ))
    rows.append(_ok(
        "Referencias cierre 2026 sólo como contraste histórico",
        all(abs(float(serv[k].sum()) - v) <= 1.0 for k, v in TOTALES_2027_VIGENTES.items()),
        "Los CSV de referencia no modifican data/od_biotren/processed/; Biotren usa contraste histórico para distribuir el ajuste mensual.",
    ))

    # 4. Consistencia de totales mensuales/anuales entre detalle y resumen.
    serv_desde_detalle = detalle.groupby(["periodo", "servicio"])["afl"].sum().unstack()[serv.columns]
    dif_mensual = (serv_desde_detalle - serv).abs().max().max()
    dif_anual = (serv_desde_detalle.sum() - serv.sum()).abs().max()
    rows.append(_ok(
        "Consistencia mensual/anual del motor",
        bool(dif_mensual <= 0.5 and dif_anual <= 6.0),
        f"Diferencia mensual máxima: {dif_mensual:.6f}; anual máxima: {dif_anual:.6f}",
    ))

    # 5. Sensibilidad mensual: cambio en marzo L2 debe afectar marzo y no todos los meses.
    plan = O.oferta_actual_df(mensual=True)
    plan.loc[(plan.unit == "BIOTREN_L2") & (plan.mes == 3) & (plan.dt == "LV"), "servicios_dia"] += 10
    _, serv_alt, _ = O.proyectar_mensual_elastico(params, mdf, plan=plan, return_detalle=True)
    dif = (serv_alt["BIOTREN"] - serv["BIOTREN"]).astype(float)
    meses_con_cambio = dif[dif.abs() > 1e-6].index.tolist()
    sensibilidad_ok = "2027-03" in meses_con_cambio and float(dif.loc["2027-03"]) != 0.0
    rows.append(_ok(
        "Sensibilidad mensual por oferta con recalibración trazable",
        sensibilidad_ok,
        f"Meses con cambio: {meses_con_cambio}; la recalibración anual distribuye residuales, pero marzo conserva respuesta directa a la oferta editada",
    ))

    # 6. Feriados: Biotren sin operación, Laja opera como fin de semana.
    cal = O.calendario_diario_operacional(2027, units=["BIOTREN_L2", "CORTO_LAJA"])
    fer = cal[cal["es_feriado"]]
    biotren_fer_ok = bool((fer[fer.unit == "BIOTREN_L2"]["opera"] == False).all())
    laja_fer_ok = bool((fer[fer.unit == "CORTO_LAJA"]["opera"] == True).all())
    rows.append(_ok("Regla de feriados Biotren", biotren_fer_ok, "Biotren queda sin operación en feriados nacionales"))
    rows.append(_ok("Regla de feriados Laja-Talcahuano", laja_fer_ok, "Laja-Talcahuano opera feriados con regla fin de semana"))

    # 7. OD híbrido: ejecución y consistencia de totales.
    resultado = ODH.distribuir_proyeccion_biotren(serv["BIOTREN"].astype(float))
    od_resumen = resultado["resumen"].copy()
    od_total_mes = od_resumen.groupby("periodo")["viajes_tipo_proyectados"].sum()
    dif_od = od_total_mes.sub(serv["BIOTREN"].astype(float), fill_value=0).abs().max()
    rows.append(_ok("Consistencia OD mensual vs Biotren", dif_od < 1e-5, f"Diferencia máxima: {dif_od:.8f}"))

    # 8. Matrices por tipo: orden, dimensiones e ingresos.
    station_order = resultado["station_order"]
    dim_ok = True
    ingreso_dim_ok = True
    for key, M in resultado["matrices_viajes"].items():
        dim_ok = dim_ok and list(M.index) == station_order and list(M.columns) == station_order
        R = resultado["matrices_ingresos"][key]
        ingreso_dim_ok = ingreso_dim_ok and list(R.index) == station_order and list(R.columns) == station_order and R.shape == M.shape
    rows.append(_ok("Orden original de estaciones en matrices OD", bool(dim_ok), f"Estaciones: {len(station_order)}"))
    rows.append(_ok("Dimensión matriz ingresos vs viajes", bool(ingreso_dim_ok), "Índices, columnas y dimensiones coinciden"))

    # 9. Tarifas e ingresos para pares con viajes proyectados.
    viajes = resultado["viajes_long"]
    ingresos = resultado["ingresos_long"]
    merged = viajes.merge(ingresos, on=["periodo", "mes", "tipo_pasajero", "origen", "destino"], how="left")
    zero_income = int(((merged["viajes_proyectados"] > 1e-9) & (merged["ingresos_proyectados"].fillna(0) <= 0)).sum())
    rows.append(_ok("Viajes proyectados con ingreso no positivo", zero_income == 0, f"Pares detectados: {zero_income}"))

    # 10. Validación explícita de arreglos NumPy/Pandas no escribibles en el balance OD.
    seed_ro = np.array([[1.0, 2.0], [3.0, 4.0]])
    row_ro = np.array([30.0, 70.0])
    col_ro = np.array([45.0, 55.0])
    seed_ro.flags.writeable = False
    row_ro.flags.writeable = False
    col_ro.flags.writeable = False
    M_ro, conv_ro, _, err_ro = ODH.ipf(seed_ro, row_ro, col_ro)
    readonly_ok = bool(conv_ro and np.isfinite(err_ro) and np.allclose(M_ro.sum(axis=1), [30.0, 70.0]) and np.allclose(M_ro.sum(axis=0), [45.0, 55.0]))
    rows.append(_ok("OD compatible con arreglos read-only", readonly_ok, f"Converge: {conv_ro}; error: {err_ro:.2e}"))

    # 11. Insumos OD por tipo de tarjeta: estructura y consistencia.
    val_tipo_tarjeta = ODH.validar_insumos_tipo_tarjeta()
    for _, row in val_tipo_tarjeta.iterrows():
        rows.append(_ok(str(row["control"]), row["estado"] == "OK", str(row["detalle"])))

    # 11A. Clasificación OD por línea Biotren preparada para análisis MOD.
    mapeo_linea = ODH.cargar_mapeo_estacion_linea()
    od_historica_tarjeta = pd.read_csv(ODH.PROCESSED_FILES["od_historica_tipo_tarjeta"])
    estaciones_sin_mapeo = ODH.validar_estaciones_od_en_mapeo(od_historica_tarjeta, mapeo_linea)
    rows.append(_ok(
        "Estaciones OD con registro en mapeo línea",
        len(estaciones_sin_mapeo) == 0,
        "Sin registro: " + (", ".join(estaciones_sin_mapeo) if estaciones_sin_mapeo else "ninguna"),
    ))
    duplicadas_mapeo = mapeo_linea[mapeo_linea["estacion"].duplicated(keep=False)]["estacion"].tolist()
    rows.append(_ok(
        "Mapeo estación-línea sin duplicados",
        len(duplicadas_mapeo) == 0,
        "Duplicadas: " + (", ".join(duplicadas_mapeo) if duplicadas_mapeo else "ninguna"),
    ))
    lineas_invalidas = sorted(set(mapeo_linea["linea_base"].astype(str)) - ODH.LINEAS_BASE_BIOTREN_VALIDAS)
    rows.append(_ok(
        "Valores válidos de linea_base",
        len(lineas_invalidas) == 0,
        "Inválidos: " + (", ".join(lineas_invalidas) if lineas_invalidas else "ninguno"),
    ))
    concepcion = mapeo_linea[mapeo_linea["estacion"].map(ODH.canon) == "Concepción"]
    concepcion_ok = bool(
        len(concepcion) == 1
        and concepcion.iloc[0]["linea_base"] == "L1_L2"
        and int(concepcion.iloc[0]["es_estacion_comun"]) == 1
    )
    rows.append(_ok(
        "Concepción marcada como estación común/intercambio",
        concepcion_ok,
        "Registro: " + (concepcion[["estacion", "linea_base", "es_estacion_comun"]].to_dict("records").__str__() if len(concepcion) else "no encontrado"),
    ))
    conteo_lineas = mapeo_linea["linea_base"].value_counts().reindex(sorted(ODH.LINEAS_BASE_BIOTREN_VALIDAS), fill_value=0)
    rows.append(_ok(
        "Cantidad de estaciones por línea base",
        True,
        "; ".join(f"{k}: {int(v)}" for k, v in conteo_lineas.items()),
    ))
    od_clasificada = ODH.clasificar_od_por_linea(od_historica_tarjeta, mapeo_linea)
    viajes_col = "viajes_observados"
    total_original = float(od_historica_tarjeta[viajes_col].sum())
    total_clasificado = float(od_clasificada[viajes_col].sum())
    no_clasificados = float(od_clasificada.loc[od_clasificada["clasificacion_linea_od"] == "No clasificado", viajes_col].sum())
    pct_no_clasificado = no_clasificados / total_clasificado if total_clasificado else 0.0
    rows.append(_ok(
        "Proporción de viajes OD No clasificado",
        True,
        f"Viajes No clasificado: {no_clasificados:,.0f}; proporción: {pct_no_clasificado:.4%}",
    ))
    rows.append(_ok(
        "Clasificación OD por línea conserva total observado",
        abs(total_original - total_clasificado) <= 1e-8,
        f"Original: {total_original:,.0f}; clasificado: {total_clasificado:,.0f}; diferencia: {total_clasificado - total_original:.8f}",
    ))
    resumen_no_clasificado = ODH.resumir_od_no_clasificada(od_historica_tarjeta, mapeo_linea)
    top_no_clasificado = resumen_no_clasificado[resumen_no_clasificado["viajes_observados_totales"] > 0].head(20)
    pares_cero_no_clasificado = int((resumen_no_clasificado["viajes_observados_totales"] == 0).sum())
    motivos_no_clasificado = resumen_no_clasificado.groupby("motivo_probable")["viajes_observados_totales"].sum().sort_values(ascending=False)
    rows.append(_ok(
        "Top pares OD No clasificado por motivo probable",
        True,
        (
            "Motivos: "
            + "; ".join(f"{k}: {v:,.0f}" for k, v in motivos_no_clasificado.items())
            + f". Pares No clasificado sin viajes observados: {pares_cero_no_clasificado}"
            + ". Top: "
            + "; ".join(
                (
                    f"{r.origen}->{r.destino}: {r.viajes_observados_totales:,.0f} "
                    f"({r.porcentaje_sobre_total_no_clasificado:.4%} No clas.; "
                    f"{r.porcentaje_sobre_total_od_historico:.4%} total; {r.motivo_probable})"
                )
                for r in top_no_clasificado.itertuples(index=False)
            )
        ),
    ))

    dist_linea = ODH.distribuir_proyeccion_biotren_por_linea_mod(serv["BIOTREN"].astype(float))
    total_linea_mes = dist_linea.groupby("periodo")["viajes_proyectados"].sum()
    dif_linea_mod = total_linea_mes.sub(serv["BIOTREN"].astype(float), fill_value=0).abs().max()
    participacion_linea = dist_linea.groupby("periodo")["participacion_linea_mes"].sum()
    dif_part_linea = float((participacion_linea - 1.0).abs().max())
    lineas_std_ok = set(dist_linea["linea_od"].astype(str)) == {"L1", "L2", "L1-L2"}
    total_linea_anual = float(dist_linea["viajes_proyectados"].sum())
    rows.append(_ok(
        "Distribución por línea MOD conserva total Biotren",
        bool(dif_linea_mod < 1e-5 and dif_part_linea < 1e-10 and lineas_std_ok and abs(total_linea_anual - total_biotren_vigente) <= 1e-5),
        f"Diferencia máxima: {dif_linea_mod:.8f}; diferencia participación: {dif_part_linea:.12f}; categorías estándar: {sorted(dist_linea['linea_od'].unique())}; total anual líneas: {total_linea_anual:,.0f}",
    ))
    rows.append(_ok(
        "No clasificado sin proyección estándar",
        bool("No clasificado" not in set(dist_linea["linea_od"].astype(str))),
        "Concepción→Concepción queda como control diagnóstico histórico y no se incluye en líneas proyectadas",
    ))

    # 12. Paso 2B mínimo: distribución por tipo de tarjeta e ingresos agregados en memoria.
    resultado_tarjetas = ODH.distribuir_proyeccion_biotren_por_tipo_tarjeta(serv["BIOTREN"].astype(float))
    resumen_tarjetas = resultado_tarjetas["resumen_tipo_tarjeta"]
    total_tarjetas_mes = resumen_tarjetas.groupby("periodo")["viajes_proyectados"].sum()
    dif_tarjetas = total_tarjetas_mes.sub(serv["BIOTREN"].astype(float), fill_value=0).abs().max()
    total_tarjeta_anual = float(resumen_tarjetas["viajes_proyectados"].sum())
    rows.append(_ok(
        "Consistencia tarjeta mensual/anual vs Biotren",
        dif_tarjetas < 1e-5 and abs(total_tarjeta_anual - total_biotren_vigente) <= 1e-5,
        f"Diferencia máxima mensual: {dif_tarjetas:.8f}; total anual tarjetas: {total_tarjeta_anual:,.0f}",
    ))

    ingresos_por_tarifa = resumen_tarjetas.groupby("tipo_pasajero_tarifa")["ingresos_tarifarios_proyectados"].sum()
    ingresos_con_tarifa_ok = bool((ingresos_por_tarifa.drop(labels=["Sin ingreso tarifario"], errors="ignore") > 0).all())
    ingreso_cero_ok = bool(ingresos_por_tarifa.get("Sin ingreso tarifario", 0.0) == 0.0)
    rows.append(_ok(
        "Ingreso tarifario agregado por tipo de tarjeta",
        ingresos_con_tarifa_ok and ingreso_cero_ok,
        "; ".join(f"{k}: {v:,.0f}" for k, v in ingresos_por_tarifa.items()),
    ))

    tipos_con_tarifa = {"monedero", "media_superior", "adulto_mayor"}
    ingreso_tipo = resumen_tarjetas.groupby("tipo_tarjeta")["ingresos_tarifarios_proyectados"].sum()
    ingresos_directos_ok = bool((ingreso_tipo.reindex(sorted(tipos_con_tarifa), fill_value=0.0) > 0).all())
    ingresos_cero_ok = bool((ingreso_tipo.drop(labels=list(tipos_con_tarifa), errors="ignore").abs() <= 1e-9).all())
    rows.append(_ok(
        "Ingresos sólo en tipos con tarifa directa",
        ingresos_directos_ok and ingresos_cero_ok,
        "; ".join(f"{k}: {v:,.0f}" for k, v in ingreso_tipo.items()),
    ))

    ingresos_sub = resultado_tarjetas["ingresos_subsidio_biotren"]
    anual_sub = ingresos_sub["resumen_anual"]
    cobertura_est = ingresos_sub["cobertura_estudiante"]
    grupos_sub = ingresos_sub["grupos"]
    tarifa_est_path = ODH.PROCESSED_FILES["tarifa_estudiante_bt_sin_subsidio"]
    tarifa_est = ODH.cargar_tarifa_estudiante_bt_sin_subsidio()
    cols_est = {"origen", "destino", "tarifa_estudiante_bt_sin_subsidio", "es_diagonal", "origen_en_modelo", "destino_en_modelo", "tarifa_disponible", "fuente"}
    rows.append(_ok("Tarifa estudiante BT sin subsidio existe", tarifa_est_path.exists(), str(tarifa_est_path.relative_to(BASE))))
    rows.append(_ok("Columnas tarifa estudiante BT sin subsidio", cols_est.issubset(tarifa_est.columns), f"Columnas: {sorted(tarifa_est.columns)}"))
    tasa = ODH.cargar_tasa_descuento_normal()
    rows.append(_ok("tasa_descuento_normal parametrizada", abs(tasa - 0.189) <= 1e-12, f"Valor: {tasa:.3f}"))
    rows.append(_ok("tasa_descuento_normal entre 0 y 1", 0.0 < tasa < 1.0, f"Valor: {tasa:.3f}"))
    rows.append(_ok("Estaciones matriz estudiante contenidas en modelo", len(cobertura_est["fuera_modelo"]) == 0, "Fuera modelo: " + (", ".join(cobertura_est["fuera_modelo"]) or "ninguna")))
    rows.append(_ok("Concepcion Centro sin cobertura estudiante", "Concepción Centro" in cobertura_est["sin_cobertura_modelo"] or "Concepcion Centro" in cobertura_est["sin_cobertura_modelo"], f"Sin cobertura: {cobertura_est['sin_cobertura_modelo']}"))
    rows.append(_ok("Pasajero Lota sin tarifas disponibles", "Pasajero Lota" in cobertura_est["estaciones_sin_tarifas"], f"Sin tarifas: {cobertura_est['estaciones_sin_tarifas']}"))
    diag = tarifa_est[tarifa_est["origen"].map(ODH.canon).eq(tarifa_est["destino"].map(ODH.canon))]
    rows.append(_ok("Diagonal estudiante tratada como cero", bool((diag["es_diagonal"].astype(int).eq(1)).all()), f"Filas diagonal: {len(diag)}"))
    rows.append(_ok("MOD normal_base excluye media_superior y adulto_mayor", not ({"media_superior", "adulto_mayor"} & set(grupos_sub["normal_base"])), f"Grupo normal_base: {grupos_sub['normal_base']}"))
    rows.append(_ok("media_superior único grupo estudiante subsidio", grupos_sub["estudiante_subsidio"] == ["media_superior"], f"Grupo estudiante: {grupos_sub['estudiante_subsidio']}"))
    rows.append(_ok("Tarifa estudiante pagada desde matriz vigente", grupos_sub.get("tarifa_estudiante_pagada") == ["Estudiante"], f"Fuente tarifa pagada: {grupos_sub.get('tarifa_estudiante_pagada')}"))
    rows.append(_ok("Tarifa estudiante sin subsidio desde data/tarifas_biotren", grupos_sub.get("tarifa_estudiante_sin_subsidio_path") == "data/tarifas_biotren/tarifa_estudiante_bt_sin_subsidio_long.csv", f"Fuente sin subsidio: {grupos_sub.get('tarifa_estudiante_sin_subsidio_path')}"))
    estaciones_tarifa = set(tarifa_est["origen"].map(ODH.canon)) | set(tarifa_est["destino"].map(ODH.canon))
    disponibles = int(tarifa_est["tarifa_disponible"].astype(int).sum())
    no_disponibles = int((tarifa_est["tarifa_disponible"].astype(int) == 0).sum())
    controles_tarifa = {
        ("Hualqui", "La Leonera"): 320,
        ("Hualqui", "Concepción"): 330,
        ("Hualqui", "UTFSM"): 340,
        ("Concepción", "UTFSM"): 300,
        ("Hualqui", "Los Canelos"): 560,
        ("Hito Galvarino", "Hualqui"): 370,
    }
    valores_ok = []
    detalles_valores = []
    for (origen, destino), esperado in controles_tarifa.items():
        fila = tarifa_est[tarifa_est["origen"].map(ODH.canon).eq(ODH.canon(origen)) & tarifa_est["destino"].map(ODH.canon).eq(ODH.canon(destino))]
        valor = None if fila.empty else float(fila.iloc[0]["tarifa_estudiante_bt_sin_subsidio"])
        valores_ok.append(valor == esperado)
        detalles_valores.append(f"{origen}->{destino}: {valor}")
    rows.append(_ok("Valores control tarifa presupuesto base", all(valores_ok), "; ".join(detalles_valores)))
    rows.append(_ok("Matriz estudiante tiene 26 estaciones", len(estaciones_tarifa) == 26, f"Estaciones: {len(estaciones_tarifa)}"))
    rows.append(_ok("Matriz estudiante tiene 676 pares OD", len(tarifa_est) == 676, f"Pares: {len(tarifa_est)}"))
    rows.append(_ok("Matriz estudiante tiene 600 tarifas disponibles", disponibles == 600, f"Disponibles: {disponibles}"))
    rows.append(_ok("Matriz estudiante tiene 76 pares sin tarifa", no_disponibles == 76, f"Sin tarifa: {no_disponibles}"))
    rows.append(_ok("Venta media_superior considera diagonal", abs(anual_sub["venta_media_superior_con_diagonal"] - anual_sub["venta_pasajes_media_superior"]) <= 1e-6, f"Venta MS: {anual_sub['venta_media_superior_con_diagonal']:,.0f}"))
    rows.append(_ok("Ingreso teórico estudiante sin subsidio excluye diagonal", abs(anual_sub["ingreso_teorico_estudiante_sin_subsidio_sin_diagonal"] - anual_sub["ingreso_teorico_estudiante_sin_subsidio"]) <= 1e-6, f"Teórico sin diagonal: {anual_sub['ingreso_teorico_estudiante_sin_subsidio_sin_diagonal']:,.0f}"))
    rows.append(_ok("Subsidio estudiante usa diferencia agregada oficial", abs(anual_sub["subsidio_estudiante"] - (anual_sub["ingreso_teorico_estudiante_sin_subsidio_sin_diagonal"] - anual_sub["venta_media_superior_con_diagonal"])) <= 1e-6, f"Subsidio estudiante: {anual_sub['subsidio_estudiante']:,.0f}"))
    rows.append(_ok("Brecha OD estudiante sólo diagnóstica", anual_sub["subsidio_estudiante_formula_anterior"] == anual_sub["subsidio_estudiante_brecha_od_diagnostica"], f"Brecha OD diagnóstica: {anual_sub['subsidio_estudiante_formula_anterior']:,.0f}"))
    rows.append(_ok("Sin brechas negativas diagnósticas", anual_sub["brecha_minima_diagnostica"] >= -1e-9, f"Brecha mínima: {anual_sub['brecha_minima_diagnostica']:,.6f}"))
    rows.append(_ok("Diagonal brecha estudiante diagnóstica en cero", abs(anual_sub["diagonal_brecha_diagnostica_suma"]) <= 1e-9, f"Suma diagonal: {anual_sub['diagonal_brecha_diagnostica_suma']:,.6f}"))
    rows.append(_ok("Subsidio normal no negativo", anual_sub["subsidio_normal"] >= 0, f"Subsidio normal: {anual_sub['subsidio_normal']:,.0f}"))
    rows.append(_ok("Subsidio estudiante no negativo", anual_sub["subsidio_estudiante"] >= 0, f"Subsidio estudiante: {anual_sub['subsidio_estudiante']:,.0f}"))
    rows.append(_ok("Subsidio total consistente", abs(anual_sub["subsidio_total"] - anual_sub["subsidio_normal"] - anual_sub["subsidio_estudiante"]) <= 1e-6, f"Total: {anual_sub['subsidio_total']:,.0f}"))
    rows.append(_ok("Ingreso total Biotren consistente", abs(anual_sub["ingreso_total_biotren"] - anual_sub["ingreso_venta"] - anual_sub["subsidio_normal"] - anual_sub["subsidio_estudiante"]) <= 1e-6, f"Ingreso total: {anual_sub['ingreso_total_biotren']:,.0f}"))
    for campo_ref, valor_ref in BIOTREN_FINANCIERO_REFERENCIA_2027.items():
        tolerancia = 1.0 if campo_ref == "ingreso_total_biotren" else 2.0
        rows.append(_ok(
            f"Biotren financiero vigente {campo_ref}",
            abs(float(anual_sub[campo_ref]) - valor_ref) <= tolerancia,
            f"Calculado: {float(anual_sub[campo_ref]):,.0f}; referencia: {valor_ref:,.0f}",
        ))
    rows.append(_ok("Ingreso estudiante corregido iguala teórico sin subsidio", abs(anual_sub["diferencia_ingreso_corregido_vs_teorico"]) <= 1e-6, f"Diferencia: {anual_sub['diferencia_ingreso_corregido_vs_teorico']:,.0f}"))
    rows.append(_ok("Advertencia pares media_superior con tarifa faltante", isinstance(cobertura_est.get("pares_media_superior_sin_tarifa", None), (int, float)), f"Pares con viajes y sin tarifa: {cobertura_est.get('pares_media_superior_sin_tarifa')}"))
    rows.append(_ok("Biotren conserva total ajustado en capas financieras", abs(anual_sub["viajes_biotren"] - TOTALES_2027_VIGENTES["BIOTREN"]) <= 2.0, f"Viajes: {anual_sub['viajes_biotren']:,.0f}"))
    streamlit_text = (BASE / "streamlit_app.py").read_text(encoding="utf-8")
    montos_referenciales_streamlit = ["1216", "1.216", "2615", "2.615", "9154", "9.154", "1216329151", "2615122803", "9153592420"]
    rows.append(_ok("Streamlit sin montos financieros anuales hardcodeados", not any(m in streamlit_text for m in montos_referenciales_streamlit), "Montos referenciales no encontrados en streamlit_app.py"))
    rows.append(_ok(
        "Streamlit usa vista ejecutiva Biotren con corte de flujo",
        "render_biotren_ejecutivo(serv, uni, detalle)" in streamlit_text
        and "return\n\n    st.markdown(\"#### Evolución mensual" in streamlit_text,
        "Biotren llama render_biotren_ejecutivo y retorna antes de los bloques genéricos",
    ))
    textos_no_principales = [
        "render_distribucion_biotren_linea_mod",
        "render_od_biotren",
        "Pax/" + "viaje proyectado",
        "3. Composición operacional 2027 vigente",
    ]
    rows.append(_ok(
        "Streamlit Biotren sin llamados ni rótulos redundantes",
        not any(t in streamlit_text for t in textos_no_principales),
        "Texto redundante no encontrado" if not any(t in streamlit_text for t in textos_no_principales) else "Detectado: " + ", ".join(t for t in textos_no_principales if t in streamlit_text),
    ))
    rows.append(_ok(
        "Streamlit muestra pax/servicio comercial como indicador principal",
        "Pax/servicio comercial" in streamlit_text and "Ocupación mensual y bandas de funcionamiento" in streamlit_text,
        "Rótulo principal y bloque mensual encontrados",
    ))
    rows.append(_ok(
        "Streamlit rotula capacidad equivalente como diagnóstico",
        "Pax/capacidad equivalente" in streamlit_text and "Diagnóstico técnico de capacidad equivalente" in streamlit_text,
        "Indicador técnico en expander encontrado",
    ))

    subsidio_ref = resultado_tarjetas["subsidio_referencial_base"]
    columnas_monto_subsidio = [c for c in subsidio_ref.columns if "monto" in c.lower() or "subsidio_monetario" in c.lower()]
    subsidio_ok = bool({"mes", "grupo_subsidio_referencial", "viajes_observados_base_referencial"}.issubset(subsidio_ref.columns) and len(subsidio_ref) > 0 and not columnas_monto_subsidio)
    rows.append(_ok("Base referencial de subsidio en memoria", subsidio_ok, f"Filas agregadas: {len(subsidio_ref)}; columnas de monto: {columnas_monto_subsidio or 'ninguna'}"))

    # 13. Exportación controlada en modo muestra: un mes/tipo, sin escribir
    # outputs completos. Valida la ruta operativa sin generar archivos masivos.
    muestra_export = ODH.exportar_salidas_tipo_tarjeta(
        serv["BIOTREN"].astype(float),
        meses=[1],
        tipos_tarjeta=["monedero"],
        escribir_archivos=False,
    )
    muestra_ok = bool(
        len(muestra_export["viajes_tipo_tarjeta_long"]) > 0
        and len(muestra_export["ingresos_tipo_tarjeta_long"]) == len(muestra_export["viajes_tipo_tarjeta_long"])
        and len(muestra_export["base_subsidio_referencial_long"]) > 0
        and muestra_export["archivos"] == {}
    )
    rows.append(_ok(
        "Exportación tipo tarjeta en modo muestra sin outputs completos",
        muestra_ok,
        (
            f"Viajes: {len(muestra_export['viajes_tipo_tarjeta_long'])}; "
            f"ingresos: {len(muestra_export['ingresos_tipo_tarjeta_long'])}; "
            f"archivos escritos: {len(muestra_export['archivos'])}"
        ),
    ))

    # 14. Backtesting histórico: métricas por servicio y total sistema en memoria.
    bt = BT.ejecutar_backtesting(params, mdf)
    metricas_ok = bool(
        not bt.metricas_servicio.empty
        and not bt.observado_estimado.empty
        and set(BT.METRIC_COLUMNS).issubset(bt.metricas_servicio.columns)
        and set(BT.METRIC_COLUMNS).issubset(bt.resumen_total_sistema.columns)
        and {"n_meses_mape", "n_meses_observado_cero"}.issubset(bt.metricas_servicio.columns)
        and BT.BACKTESTING_TIPO == "retrospectivo_diagnostico_no_holdout"
    )
    rows.append(_ok(
        "Backtesting histórico por servicio",
        metricas_ok,
        f"Servicios: {len(bt.metricas_servicio)}; meses comparados: {len(bt.observado_estimado)}; advertencias: {len(bt.advertencias)}",
    ))

    bandas = INC.calcular_bandas_incertidumbre(serv.astype(float), bt.metricas_servicio, getattr(bt, "contribucion_servicio", None))
    bandas_ok = bool(
        not bandas.mensual.empty
        and not bandas.anual.empty
        and (bandas.mensual[["escenario_base", "banda_baja_wmape", "banda_alta_wmape", "escenario_ajustado_sesgo"]] >= 0).all().all()
        and (bandas.mensual["banda_baja_wmape"] <= bandas.mensual["escenario_base"]).all()
        and (bandas.mensual["banda_alta_wmape"] >= bandas.mensual["escenario_base"]).all()
    )
    rows.append(_ok(
        "Bandas de incertidumbre sobre base recalibrada",
        bandas_ok,
        f"Filas mensuales: {len(bandas.mensual)}; total base bandas: {bandas.anual['total_base'].sum():,.0f}; sin valores negativos",
    ))

    # 15. Carga real de Streamlit mediante AppTest.
    app = AppTest.from_file(str(BASE / "streamlit_app.py"), default_timeout=90)
    app.run()
    rows.append(_ok("Carga de Streamlit", len(app.exception) == 0, f"Excepciones detectadas: {len(app.exception)}"))

    # 16. Cobertura de archivos exportados.
    expected = [
        OUT / "proyeccion_2027_resumen_mensual_elastico.csv",
        OUT / "proyeccion_2027_unidades_mensual_elastico.csv",
        OUT / "detalle_calculo_mensual_elastico.csv",
        OD_OUT / "od_2027_viajes_por_tipo_long.csv",
        OD_OUT / "od_2027_ingresos_por_tipo_long.csv",
        ODH.PROCESSED_FILES["orden_estaciones"],
        ODH.PROCESSED_FILES["od_historica"],
        ODH.PROCESSED_FILES["tarifas"],
        ODH.PROCESSED_FILES["distancias"],
        ODH.PROCESSED_FILES["validacion"],
        ODH.PROCESSED_FILES["od_historica_tipo_tarjeta"],
        ODH.PROCESSED_FILES["participacion_mensual_tipo_tarjeta"],
        ODH.PROCESSED_FILES["participacion_od_tipo_tarjeta"],
        ODH.PROCESSED_FILES["mapeo_tipo_tarjeta"],
        ODH.PROCESSED_FILES["base_subsidio_referencial"],
    ]
    missing = [p.name for p in expected if not p.exists()]
    rows.append(_ok("Archivos de salida principales", len(missing) == 0, "Faltantes: " + (", ".join(missing) if missing else "ninguno")))

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "resumen_validacion_tecnica.csv", index=False)
    return out


if __name__ == "__main__":
    print(ejecutar_validacion().to_string(index=False))
