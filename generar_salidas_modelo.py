"""Regenera las salidas principales del modelo mensual-elástico."""
from pathlib import Path
import pandas as pd
import pipeline_afluencia as P
import oferta as O
import od_biotren_hibrido as ODH
import validar_modelo as VM

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
OUT = BASE / "outputs"
OUT.mkdir(exist_ok=True)

params = O.aplicar_oferta_actual(pd.read_csv(DATA / "oferta_params.csv"))
diario = pd.read_csv(DATA / "afluencia_diaria_consolidada.csv", parse_dates=["fecha"])
mdf = P.mensualizar(diario)
uni, serv, detalle = O.proyectar_mensual_elastico(params, mdf, return_detalle=True)
recal_attrs = serv.attrs.get('recalibracion_2027', {})
comparativo_recal = pd.DataFrame(recal_attrs.get('comparativo', []))
mensual_recal = pd.DataFrame(recal_attrs.get('mensual', []))
diagnostico_recal = pd.DataFrame(recal_attrs.get('diagnostico', []))
mensual_recal = mensual_recal.copy()
if not mensual_recal.empty and 'mes' in mensual_recal.columns:
    mensual_recal['periodo'] = mensual_recal['mes'].map(lambda m: f'2027-{int(m):02d}')
mensual_recal.to_csv(OUT / 'comparativo_mensual_escenario_2027_recalibrado.csv', index=False)
comparativo_recal.to_csv(OUT / 'comparativo_escenario_2027_recalibrado.csv', index=False)
diagnostico_recal.to_csv(OUT / 'diagnostico_recalibracion_escenario_2027.csv', index=False)
O.diagnostico_redistribucion_biotren_2027(
    mensual_recal.set_index('mes').query("servicio == 'BIOTREN'")['proyeccion_vigente_pre_redistribucion'],
    serv['BIOTREN'],
).to_csv(OUT / 'diagnostico_participacion_mensual_biotren_2027.csv', index=False)

serv.to_csv(OUT / "proyeccion_2027_resumen_mensual_elastico.csv")
uni.to_csv(OUT / "proyeccion_2027_unidades_mensual_elastico.csv")
detalle.to_csv(OUT / "detalle_calculo_mensual_elastico.csv", index=False)
O.analisis_mensual_historico(mdf).to_csv(OUT / "analisis_mensual_historico_servicio.csv", index=False)
O.resumen_historico_anual(mdf).to_csv(OUT / "resumen_historico_anual_servicio.csv", index=False)
O.factores_estacionalidad_mensual(params, mdf).to_csv(OUT / "factores_estacionalidad_mensual.csv", index=False)
uni[[c for c in uni.columns if str(c).startswith("TA_")]].to_csv(OUT / "proyeccion_2027_tren_araucania_tramos.csv")
O.perfil_distribucion_tren_araucania_por_tramo().to_csv(OUT / "tren_araucania_distribucion_historica_tramos.csv", index=False)
O.feriados_chile(2027).to_csv(DATA / 'feriados_chile_2027.csv', index=False)
O.feriados_chile(2027).to_csv(OUT / 'feriados_chile_2027.csv', index=False)
O.calendario_operacional_resumen(2027).to_csv(DATA / 'calendario_operacional_2027.csv', index=False)
O.calendario_operacional_resumen(2027).to_csv(OUT / 'calendario_operacional_2027.csv', index=False)

# Validación específica del ajuste de recuperación Laja-Talcahuano.
hist_laja = O.resumen_historico_anual(mdf)
hist_laja = hist_laja[hist_laja['servicio'] == 'CORTO_LAJA'].copy()
hist_laja['tipo_registro'] = 'historico_observado_normalizado'
hist_laja = hist_laja[['tipo_registro', 'anio', 'meses_observados', 'primer_mes', 'ultimo_mes', 'afluencia_observada_normalizada']]
proy_laja = pd.DataFrame([{
    'tipo_registro': 'proyeccion_2027_recuperacion_540k',
    'anio': 2027,
    'meses_observados': 12,
    'primer_mes': 1,
    'ultimo_mes': 12,
    'afluencia_observada_normalizada': int(serv['CORTO_LAJA'].sum()),
}])
pd.concat([hist_laja, proy_laja], ignore_index=True).to_csv(OUT / 'validacion_laja_recuperacion.csv', index=False)

plan = O.oferta_actual_df(mensual=True)
plan.loc[(plan.unit == "BIOTREN_L2") & (plan.mes == 3) & (plan.dt == "LV"), "servicios_dia"] += 10
_, serv2, _ = O.proyectar_mensual_elastico(params, mdf, plan=plan, return_detalle=True)
(serv2 - serv).reset_index().rename(columns={"index": "periodo"}).to_csv(
    OUT / "validacion_sensibilidad_cambio_oferta_marzo_l2.csv", index=False
)



# Validación específica de la corrección marzo-abril de Biotren.
biotren_mar_abr = serv.loc[['2027-03', '2027-04'], ['BIOTREN']].copy()
biotren_mar_abr['periodo'] = biotren_mar_abr.index
biotren_mar_abr['mes'] = biotren_mar_abr['periodo'].str[-2:].astype(int)
biotren_mar_abr['participacion_bloque_marzo_abril'] = biotren_mar_abr['BIOTREN'] / biotren_mar_abr['BIOTREN'].sum()
biotren_mar_abr['criterio_ajuste'] = 'Bloque marzo-abril nivelado para Biotren: 50,2% marzo y 49,8% abril; total anual y suma del bloque se mantienen.'
biotren_mar_abr[['periodo','mes','BIOTREN','participacion_bloque_marzo_abril','criterio_ajuste']].to_csv(
    OUT / 'validacion_biotren_marzo_abril_ajustado.csv', index=False
)

# Validación específica de sensibilidad por tramo en Tren Araucanía.
base_ta = O.oferta_tren_araucania_tramos_df(mensual=True)
_, serv_base_ta, _ = O.proyectar_mensual_elastico(params, mdf, plan=base_ta, return_detalle=True)
registros_ta = []
for unit, dt, mes, delta in [
    ("TA_TEMUCO_VICTORIA", "LV", 3, 1.0),
    ("TA_TEMUCO_PITRUFQUEN", "LV", 3, 1.0),
    ("TA_CLARET", "LV", 3, 1.0),
    ("TA_CLARET", "LV", 1, 1.0),
]:
    plan_ta = base_ta.copy()
    m = (plan_ta.unit == unit) & (plan_ta.mes == mes) & (plan_ta.dt == dt)
    plan_ta.loc[m, "servicios_dia"] += delta
    _, serv_alt_ta, _ = O.proyectar_mensual_elastico(params, mdf, plan=plan_ta, return_detalle=True)
    periodo = f"2027-{mes:02d}"
    registros_ta.append({
        "unit": unit,
        "tramo": O.TA_TRAMO_NOMBRE.get(unit, unit),
        "mes": mes,
        "dt": dt,
        "delta_servicios_dia": delta,
        "impacto_mes": int(serv_alt_ta.loc[periodo, "TREN_ARAUCANIA"] - serv_base_ta.loc[periodo, "TREN_ARAUCANIA"]),
        "impacto_anual": int(serv_alt_ta["TREN_ARAUCANIA"].sum() - serv_base_ta["TREN_ARAUCANIA"].sum()),
    })
pd.DataFrame(registros_ta).to_csv(OUT / "validacion_sensibilidad_tren_araucania_tramos.csv", index=False)

# Validación mensual de magnitudes para Biotren y Tren Araucanía.
# Contrasta la participación mensual proyectada 2027 con participaciones históricas observadas.
hist_valid = O.analisis_mensual_historico(mdf)
hist_valid = hist_valid[hist_valid['servicio'].isin(['BIOTREN', 'TREN_ARAUCANIA'])].copy()
hist_valid['periodo'] = hist_valid['anio'].astype(str) + '-' + hist_valid['mes'].astype(int).astype(str).str.zfill(2)
hist_valid = hist_valid.rename(columns={
    'afluencia_mensual_normalizada': 'afluencia',
    'participacion_sobre_periodo_observado': 'participacion_anual'
})
hist_valid['tipo'] = 'historico'
hist_valid = hist_valid[['tipo','servicio','anio','mes','periodo','afluencia','participacion_anual','cobertura']]
proj_valid = []
for servicio in ['BIOTREN', 'TREN_ARAUCANIA']:
    total = float(serv[servicio].sum())
    for periodo, valor in serv[servicio].items():
        mes = int(str(periodo)[5:7])
        proj_valid.append({
            'tipo': 'proyeccion_2027',
            'servicio': servicio,
            'anio': 2027,
            'mes': mes,
            'periodo': periodo,
            'afluencia': float(valor),
            'participacion_anual': float(valor) / total if total else 0.0,
            'cobertura': 1.0,
        })
valid = pd.concat([hist_valid, pd.DataFrame(proj_valid)], ignore_index=True)
valid.to_csv(OUT / 'validacion_magnitud_mensual_biotren_araucania.csv', index=False)


# Justificación metodológica por servicio para respaldar lo mostrado en la app.
hist_mensual = O.analisis_mensual_historico(mdf)
hist_anual = O.resumen_historico_anual(mdf)

def _hist_total(servicio, anio, meses=None):
    h = hist_mensual[(hist_mensual['servicio'] == servicio) & (hist_mensual['anio'].astype(int) == int(anio))].copy()
    if meses is not None:
        h = h[h['mes'].astype(int).isin([int(m) for m in meses])]
    if h.empty:
        return None
    return float(h['afluencia_mensual_normalizada'].sum())


def _hist_resumen(servicio, anio):
    h = hist_anual[(hist_anual['servicio'] == servicio) & (hist_anual['anio'].astype(int) == int(anio))].copy()
    if h.empty:
        return None
    r = h.iloc[0]
    return {
        'total': float(r['afluencia_observada_normalizada']),
        'meses': int(r['meses_observados']),
        'primer_mes': int(r['primer_mes']),
        'ultimo_mes': int(r['ultimo_mes']),
    }


def _var(valor, base):
    if base is None or float(base) == 0:
        return None
    return (float(valor) / float(base) - 1.0) * 100.0

just_rows = []
for servicio in O.SERVICIOS:
    total = float(serv[servicio].sum())
    det_s = detalle[detalle['servicio'] == servicio].copy()
    viajes = float(det_s['viajes_operados_plan'].sum())
    pax_viaje = total / viajes if viajes > 0 else 0.0
    h2024 = _hist_total(servicio, 2024)
    h2025 = _hist_total(servicio, 2025)
    h2026 = _hist_total(servicio, 2026)
    hs2024 = _hist_resumen(servicio, 2024)
    hs2025 = _hist_resumen(servicio, 2025)
    meses_2026 = sorted(hist_mensual[(hist_mensual['servicio'] == servicio) & (hist_mensual['anio'].astype(int) == 2026)]['mes'].astype(int).unique().tolist())
    proy_2027_mismos_meses = None
    if meses_2026:
        proy_2027_mismos_meses = float(serv.loc[[f'2027-{m:02d}' for m in meses_2026], servicio].sum())
    base = {
        'servicio': servicio,
        'nombre_servicio': O.NOMBRE[servicio],
        'proyeccion_2027': round(total, 0),
        'viajes_operados_2027': round(viajes, 0),
        'pax_por_viaje_2027': round(pax_viaje, 1),
        'historico_2024': None if h2024 is None else round(h2024, 0),
        'meses_historico_2024': None if hs2024 is None else hs2024['meses'],
        'variacion_vs_2024_pct': None if hs2024 is None or hs2024['meses'] < 12 or _var(total, h2024) is None else round(_var(total, h2024), 1),
        'historico_2025': None if h2025 is None else round(h2025, 0),
        'meses_historico_2025': None if hs2025 is None else hs2025['meses'],
        'variacion_vs_2025_pct': None if hs2025 is None or hs2025['meses'] < 12 or _var(total, h2025) is None else round(_var(total, h2025), 1),
        'historico_2026_observado': None if h2026 is None else round(h2026, 0),
        'proyeccion_2027_mismos_meses_2026': None if proy_2027_mismos_meses is None else round(proy_2027_mismos_meses, 0),
        'variacion_mismos_meses_vs_2026_pct': None if _var(proy_2027_mismos_meses, h2026) is None else round(_var(proy_2027_mismos_meses, h2026), 1),
    }
    if servicio == 'BIOTREN':
        base['justificacion'] = 'Escenario 2027 recalibrado: baja progresiva del total, afectación operacional L2 en fines de semana de enero-febrero, ajuste residual laboral marzo-diciembre y recalculo posterior de MOD, OD por tarjeta e ingresos preliminares.'
    elif servicio == 'CORTO_LAJA':
        base['justificacion'] = 'Recuperación de confiabilidad con supresión acotada a 1%, mayor referencia 2024, oferta 8 servicios diarios y 10 sólo fines de semana de enero-febrero.'
    elif servicio == 'TREN_ARAUCANIA':
        base['justificacion'] = 'Proyección por tramo; Victoria-Temuco opera 11 servicios LV durante 2027, Pitrufquén se mantiene separado y Claret opera como componente escolar sólo marzo-diciembre; perfil mensual con diagnóstico de marzo.'
    elif servicio == 'LLANQUIHUE_PM':
        base['justificacion'] = 'Calibración basada en promedio de día laboral cercano a 1.500 pasajeros marzo-diciembre, con reducción de enero-febrero por menor efecto novedad y operación sólo lunes-viernes sin feriados.'
    just_rows.append(base)

pd.DataFrame(just_rows).to_csv(OUT / 'justificacion_metodologica_servicios.csv', index=False)

print(serv.sum().to_string())

# Salidas OD híbridas Biotren por tipo de pasajero e ingresos proyectados.
ODH.generar_salidas_od_2027(serv['BIOTREN'])

# Exportación local controlada OD Biotren por tipo de tarjeta.
# Los CSV long completos se escriben en una carpeta ignorada por Git.
export_tarjetas = ODH.exportar_salidas_tipo_tarjeta(serv['BIOTREN'])
print(f"Salidas OD por tipo de tarjeta exportadas localmente en: {export_tarjetas['output_dir']}")

# Validación técnica final del modelo.
VM.ejecutar_validacion()
