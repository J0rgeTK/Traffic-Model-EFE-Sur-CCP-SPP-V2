"""
oferta.py -- motor de OFERTA del modelo de afluencia (v12, mensual-elastico + feriados 2027 + escenario oferta 2027 actualizado).

El modelo NO usa clima. Base: fechas (estacionalidad) + reporte operacional (RROO).
La oferta de trenes es la VARIABLE de planificacion, editable por el usuario y
diferenciada por TIPO DE DIA (Lunes-Viernes 'LV', Sabado 'Sab', Domingo 'Dom') y mes. Desde v11 incorpora calendario operacional con feriados nacionales 2027.

Unidades: BIOTREN_L1, BIOTREN_L2, CORTO_LAJA, TREN_ARAUCANIA, LLANQUIHUE_PM.
Para Tren Araucania la demanda se calcula por tipo de servicio/tramo:
TA_TEMUCO_VICTORIA, TA_TEMUCO_PITRUFQUEN y TA_CLARET. La demanda anual
del servicio resulta de sumar los tramos, y Claret se restringe a marzo-diciembre
por tratarse de un servicio escolar.
La distribución de Biotren por línea y OD se recalcula desde el total mensual vigente; no se usa una regla 80/20 como criterio de escenario.

Estaciones Llanquihue-PM (XP-NQ): XP=La Paloma, NQ=Llanquihue, AL=Alerce, EV=Puerto Varas.
Nota operacional: los servicios Laja-Talcahuano circulan sobre el corredor de L1,
pero su afluencia se proyecta en CORTO_LAJA. En este escenario, por instrucción
de planificación 2027, BIOTREN_L1 se parametriza con 47 servicios L-V para evaluar
el crecimiento específico de Biotren.

Modelo por unidad/mes:
  proy_oferta = SUMA_tipo_dia [ servicios_por_dia x n_dias_operacionales_2027 x pax_por_viaje x (1-supresion) ]
  Escenario recomendado 2027 = oferta mensual calibrada con información histórica y operacional disponible.
  Ajuste especifico Biotren: se aplica un factor prudencial sobre la
  productividad base y el desempeño histórico reciente para representar
  un crecimiento conservador de la demanda ante mejoras de oferta.
  Ajuste Laja-Talcahuano: se incorpora recuperacion parcial de confiabilidad
  usando mayor peso del patron 2024, sin replicar directamente su nivel anual.
"""
import numpy as np
import pandas as pd
from pathlib import Path

STATIONS = {"XP": "La Paloma", "NQ": "Llanquihue", "AL": "Alerce", "EV": "Puerto Varas"}
UNIT = {'BIOTREN L1': 'BIOTREN_L1', 'BIOTREN L2': 'BIOTREN_L2', 'CORTO LJ': 'CORTO_LAJA',
        'XP - NQ': 'LLANQUIHUE_PM', 'XP-NQ': 'LLANQUIHUE_PM',
        'VI - TM': 'TREN_ARAUCANIA', 'VI-TM': 'TREN_ARAUCANIA'}
SERVICIOS = ['BIOTREN', 'CORTO_LAJA', 'TREN_ARAUCANIA', 'LLANQUIHUE_PM']

CAPACIDAD_REFERENCIA_BIOTREN_PAX_TREN = 605.0
CAPACIDAD_REFERENCIA_LAJA_TALCAHUANO_PAX_TREN = 578.0
UNIDADES_DE = {'BIOTREN': ['BIOTREN_L1', 'BIOTREN_L2'], 'CORTO_LAJA': ['CORTO_LAJA'],
               'TREN_ARAUCANIA': ['TREN_ARAUCANIA'], 'LLANQUIHUE_PM': ['LLANQUIHUE_PM']}

TA_TRAMOS = ['TA_TEMUCO_VICTORIA', 'TA_TEMUCO_PITRUFQUEN', 'TA_CLARET']
TA_TRAMO_NOMBRE = {
    'TA_TEMUCO_VICTORIA': 'Temuco - Victoria',
    'TA_TEMUCO_PITRUFQUEN': 'Temuco - Pitrufquen',
    'TA_CLARET': 'Claret',
}
# Elasticidades por tramo para Tren Araucania. El efecto marginal de una
# modificacion de oferta se estima por tipo de servicio y no con una proporcion
# agregada fija. Victoria-Temuco tiene mayor respuesta esperada; Pitrufquen y
# Claret tienen menor elasticidad por su demanda mas acotada y/o escolar.
TA_TRAMO_ELASTICIDAD = {
    'TA_TEMUCO_VICTORIA': 0.46,
    'TA_TEMUCO_PITRUFQUEN': 0.28,
    'TA_CLARET': 0.12,
}
TA_DISTRIBUCION_ANIO_PESOS = {2024: 0.25, 2025: 0.45, 2026: 0.30}

# Se mantiene un set de pesos auxiliares sólo para compatibilidad con funciones
# antiguas; la proyección principal usa distribución observada en TA-Dist.xlsx.
TA_TRAMO_PESO_DEMANDA = {
    'TA_TEMUCO_VICTORIA': 1.00,
    'TA_TEMUCO_PITRUFQUEN': 0.16,
    'TA_CLARET': 0.08,
}
NOMBRE = {'BIOTREN': 'Biotren', 'CORTO_LAJA': 'Laja-Talcahuano',
          'TREN_ARAUCANIA': 'Tren Araucania', 'LLANQUIHUE_PM': 'Llanquihue-Puerto Montt'}
DTYPES = ['LV', 'Sab', 'Dom']
DTNOMBRE = {'LV': 'Lunes a Viernes', 'Sab': 'Sabado', 'Dom': 'Domingo'}


# Feriados nacionales utilizados para el calendario operacional 2027.
# Fuente de respaldo: Feriados de Chile, Año 2027, basado en Biblioteca del Congreso Nacional.
# Se excluyen feriados regionales/comunales para mantener un calendario común de EFE Sur.
FERIADOS_CHILE_2027 = [
    {'fecha': '2027-01-01', 'nombre': 'Año Nuevo'},
    {'fecha': '2027-03-26', 'nombre': 'Viernes Santo'},
    {'fecha': '2027-03-27', 'nombre': 'Sábado Santo'},
    {'fecha': '2027-05-01', 'nombre': 'Día Nacional del Trabajo'},
    {'fecha': '2027-05-21', 'nombre': 'Día de las Glorias Navales'},
    {'fecha': '2027-06-21', 'nombre': 'Día Nacional de los Pueblos Indígenas'},
    {'fecha': '2027-06-28', 'nombre': 'San Pedro y San Pablo'},
    {'fecha': '2027-07-16', 'nombre': 'Día de la Virgen del Carmen'},
    {'fecha': '2027-08-15', 'nombre': 'Asunción de la Virgen'},
    {'fecha': '2027-09-17', 'nombre': 'Feriado Adicional Fiestas Patrias'},
    {'fecha': '2027-09-18', 'nombre': 'Independencia Nacional'},
    {'fecha': '2027-09-19', 'nombre': 'Día de las Glorias del Ejército'},
    {'fecha': '2027-10-11', 'nombre': 'Encuentro de Dos Mundos'},
    {'fecha': '2027-10-31', 'nombre': 'Día de las Iglesias Evangélicas y Protestantes'},
    {'fecha': '2027-11-01', 'nombre': 'Día de Todos los Santos'},
    {'fecha': '2027-12-08', 'nombre': 'Inmaculada Concepción'},
    {'fecha': '2027-12-25', 'nombre': 'Navidad'},
]

FERIADOS_FUENTE = 'https://www.feriados.cl/2027.htm'


DATA_DIR = Path(__file__).resolve().parent / 'data'


# ---------------------------------------------------------------------------
# Oferta vigente informada para el escenario base del modelo.
#
# Criterio de planificación 2027:
# - L1 operacional total informada: 48 LV, 16 Sab, 8 Dom, incluyendo servicios
#   Laja-Talcahuano en un mes tipo.
# - En el escenario 2027 actualizado, BIOTREN_L1 se parametriza con 47 servicios
#   L-V durante todo el año, según instrucción de planificación.
# - CORTO_LAJA usa 8 servicios base todos los dias. La excepcion operacional
#   corresponde solo a sabado y domingo de enero-febrero, donde se consideran
#   10 servicios. No se aplica 10 servicios a lunes-viernes.
# - Tren Araucania se representa con oferta por tramo; en el agregado LV se usa
#   24,6 servicios/dia: 15 Victoria-Temuco + 6,6 Pitrufquen + 3 Claret.
# ---------------------------------------------------------------------------
OFERTA_ACTUAL_MODELO = {
    'BIOTREN_L1': {'LV': 47.0, 'Sab': 8.0, 'Dom': 0.0},
    'BIOTREN_L2': {'LV': 110.0, 'Sab': 53.0, 'Dom': 32.0},
    'CORTO_LAJA': {'LV': 8.0, 'Sab': 8.0, 'Dom': 8.0},
    'TREN_ARAUCANIA': {'LV': 20.6, 'Sab': 12.0, 'Dom': 6.0},
    'LLANQUIHUE_PM': {'LV': 20.0, 'Sab': 0.0, 'Dom': 0.0},
}

# Excepciones mensuales respecto a la oferta tipo anterior. Se aplican sobre
# servicios_dia para que el resultado predictivo quede acorde con la oferta
# efectivamente informada por mes.
OFERTA_ACTUAL_EXCEPCIONES = [
    {'unit': 'CORTO_LAJA', 'mes': 1, 'dt': 'Sab', 'servicios_dia': 10.0,
     'detalle': 'Enero: 10 servicios sabado y domingo en lugar de 8'},
    {'unit': 'CORTO_LAJA', 'mes': 1, 'dt': 'Dom', 'servicios_dia': 10.0,
     'detalle': 'Enero: 10 servicios sabado y domingo en lugar de 8'},
    {'unit': 'CORTO_LAJA', 'mes': 2, 'dt': 'Sab', 'servicios_dia': 10.0,
     'detalle': 'Febrero: 10 servicios sabado y domingo en lugar de 8'},
    {'unit': 'CORTO_LAJA', 'mes': 2, 'dt': 'Dom', 'servicios_dia': 10.0,
     'detalle': 'Febrero: 10 servicios sabado y domingo en lugar de 8'},
]

# Excepciones operacionales Biotren L2 de fines de semana.
# La frecuencia comercial L2 L-V se mantiene en 110 todo el año.
# Los servicios acoplados desde mayo se modelan por separado como capacidad efectiva,
# no como incremento de frecuencia comercial.
for _mes_l2_fds in (1, 2):
    for _dt_l2_fds in ('Sab', 'Dom'):
        OFERTA_ACTUAL_EXCEPCIONES.append({
            'unit': 'BIOTREN_L2', 'mes': _mes_l2_fds, 'dt': _dt_l2_fds, 'servicios_dia': 14.0,
            'detalle': 'Enero-febrero 2027: Biotren L2 opera 14 servicios de fin de semana'
        })
del _mes_l2_fds, _dt_l2_fds

OFERTA_ACTUAL_DETALLE = [
    {'servicio': 'Biotren L2', 'unit': 'BIOTREN_L2', 'dt': 'LV', 'servicios_dia': 110.0,
     'detalle': '110 servicios comerciales lunes-viernes durante todo 2027'},
    {'servicio': 'Biotren L2', 'unit': 'BIOTREN_L2', 'dt': 'Sab', 'servicios_dia': 14.0,
     'detalle': 'Enero-febrero: 14 servicios sabado'},
    {'servicio': 'Biotren L2', 'unit': 'BIOTREN_L2', 'dt': 'Dom', 'servicios_dia': 14.0,
     'detalle': 'Enero-febrero: 14 servicios domingo'},
    {'servicio': 'Biotren L2', 'unit': 'BIOTREN_L2', 'dt': 'Sab', 'servicios_dia': 53.0,
     'detalle': 'Marzo-diciembre: 53 servicios sabado'},
    {'servicio': 'Biotren L2', 'unit': 'BIOTREN_L2', 'dt': 'Dom', 'servicios_dia': 32.0,
     'detalle': 'Marzo-diciembre: 32 servicios domingo'},
    {'servicio': 'Biotren L2 capacidad efectiva', 'unit': 'BIOTREN_L2', 'dt': 'LV', 'servicios_dia': 3.0,
     'detalle': 'Mayo-diciembre: 3 servicios L2 L-V acoplados en punta mañana; incluidos dentro de los 110 servicios comerciales'},
    {'servicio': 'Biotren L1 operacional total', 'unit': 'BIOTREN_L1_TOTAL_OPERACIONAL', 'dt': 'LV', 'servicios_dia': 48.0,
     'detalle': 'Incluye 8 servicios Laja-Talcahuano'},
    {'servicio': 'Biotren L1 operacional total', 'unit': 'BIOTREN_L1_TOTAL_OPERACIONAL', 'dt': 'Sab', 'servicios_dia': 16.0,
     'detalle': 'Mes tipo: 8 servicios Biotren L1 propios + 8 Laja-Talcahuano'},
    {'servicio': 'Biotren L1 operacional total', 'unit': 'BIOTREN_L1_TOTAL_OPERACIONAL', 'dt': 'Dom', 'servicios_dia': 8.0,
     'detalle': 'Mes tipo: corresponde a 8 servicios Laja-Talcahuano'},
    {'servicio': 'Biotren L1 operacional total', 'unit': 'BIOTREN_L1_TOTAL_OPERACIONAL', 'dt': 'Sab', 'servicios_dia': 18.0,
     'detalle': 'Enero-febrero: 8 servicios Biotren L1 propios + 10 Laja-Talcahuano'},
    {'servicio': 'Biotren L1 operacional total', 'unit': 'BIOTREN_L1_TOTAL_OPERACIONAL', 'dt': 'Dom', 'servicios_dia': 10.0,
     'detalle': 'Enero-febrero: corresponde a 10 servicios Laja-Talcahuano'},
    {'servicio': 'Biotren L1 modelo 2027', 'unit': 'BIOTREN_L1', 'dt': 'LV', 'servicios_dia': 47.0,
     'detalle': 'Escenario 2027 actualizado: L1 opera con 47 servicios lunes-viernes durante todo el año'},
    {'servicio': 'Biotren L1 modelo 2027', 'unit': 'BIOTREN_L1', 'dt': 'Sab', 'servicios_dia': 8.0,
     'detalle': 'Oferta sabado mantenida para Biotren L1 dentro del escenario base'},
    {'servicio': 'Biotren L1 modelo 2027', 'unit': 'BIOTREN_L1', 'dt': 'Dom', 'servicios_dia': 0.0,
     'detalle': 'Sin oferta dominical propia para Biotren L1 en el escenario base'},
    {'servicio': 'Laja-Talcahuano', 'unit': 'CORTO_LAJA', 'dt': 'LV', 'servicios_dia': 8.0,
     'detalle': '8 servicios lunes a viernes; los 10 servicios aplican solo a fines de semana de enero-febrero'},
    {'servicio': 'Laja-Talcahuano', 'unit': 'CORTO_LAJA', 'dt': 'Sab', 'servicios_dia': 10.0,
     'detalle': 'Enero-febrero: 10 servicios sabado'},
    {'servicio': 'Laja-Talcahuano', 'unit': 'CORTO_LAJA', 'dt': 'Dom', 'servicios_dia': 10.0,
     'detalle': 'Enero-febrero: 10 servicios domingo'},
    {'servicio': 'Laja-Talcahuano', 'unit': 'CORTO_LAJA', 'dt': 'Sab', 'servicios_dia': 8.0,
     'detalle': 'Marzo-diciembre: 8 servicios sabado'},
    {'servicio': 'Laja-Talcahuano', 'unit': 'CORTO_LAJA', 'dt': 'Dom', 'servicios_dia': 8.0,
     'detalle': 'Marzo-diciembre: 8 servicios domingo'},
    {'servicio': 'Tren Araucania', 'unit': 'TREN_ARAUCANIA', 'dt': 'LV', 'servicios_dia': 24.6,
     'detalle': 'Escenario 2027 recalibrado: Victoria-Temuco 11 LV + Pitrufquen 6,6 LV + Claret 3 LV escolar'},
    {'servicio': 'Tren Araucania', 'unit': 'TREN_ARAUCANIA', 'dt': 'Sab', 'servicios_dia': 12.0,
     'detalle': '8 Victoria-Temuco + 4 Pitrufquen-Temuco'},
    {'servicio': 'Tren Araucania', 'unit': 'TREN_ARAUCANIA', 'dt': 'Dom', 'servicios_dia': 6.0,
     'detalle': '6 Victoria-Temuco'},
    {'servicio': 'Llanquihue-Puerto Montt', 'unit': 'LLANQUIHUE_PM', 'dt': 'LV', 'servicios_dia': 20.0,
     'detalle': '20 servicios de lunes a viernes'},
    {'servicio': 'Llanquihue-Puerto Montt', 'unit': 'LLANQUIHUE_PM', 'dt': 'Sab', 'servicios_dia': 0.0,
     'detalle': 'Sin servicios planificados de fin de semana'},
    {'servicio': 'Llanquihue-Puerto Montt', 'unit': 'LLANQUIHUE_PM', 'dt': 'Dom', 'servicios_dia': 0.0,
     'detalle': 'Sin servicios planificados de fin de semana'},
]


def oferta_actual_df(detalle=False, mensual=True):
    """Devuelve la oferta vigente informada.

    detalle=True retorna filas explicativas de respaldo operacional.
    mensual=True retorna la oferta usada por el modelo para cada mes y tipo de dia,
    incluyendo excepciones como Laja-Talcahuano en enero-febrero.
    mensual=False retorna la oferta tipo sin excepciones mensuales.
    """
    if detalle:
        return pd.DataFrame(OFERTA_ACTUAL_DETALLE)

    rows = []
    for unit, vals in OFERTA_ACTUAL_MODELO.items():
        for mes in range(1, 13):
            for dt, servicios_dia in vals.items():
                rows.append({'unit': unit, 'mes': mes, 'dt': dt, 'servicios_dia': float(servicios_dia)})
    df = pd.DataFrame(rows)

    if mensual:
        exc = pd.DataFrame(OFERTA_ACTUAL_EXCEPCIONES)
        if not exc.empty:
            for _, x in exc.iterrows():
                m = (df['unit'] == x['unit']) & (df['mes'] == int(x['mes'])) & (df['dt'] == x['dt'])
                df.loc[m, 'servicios_dia'] = float(x['servicios_dia'])
        return df

    return df.drop(columns='mes').drop_duplicates().reset_index(drop=True)


def aplicar_oferta_actual(params, oferta=None, excepciones=None):
    """Reemplaza servicios_dia por la oferta vigente, manteniendo pax_x_viaje y tasa_sup.

    La asignacion se define por unidad, mes y tipo de dia. Esto permite representar
    modificaciones mensuales especificas sin cambiar la estimacion historica de
    pax_x_viaje ni las tasas de supresion.
    """
    p = params.copy()
    p['mes'] = p['mes'].astype(int)

    if oferta is None:
        oferta_df = oferta_actual_df(mensual=True)
    elif isinstance(oferta, pd.DataFrame):
        oferta_df = oferta.copy()
        if 'mes' not in oferta_df.columns:
            base = []
            for mes in range(1, 13):
                x = oferta_df.copy()
                x['mes'] = mes
                base.append(x)
            oferta_df = pd.concat(base, ignore_index=True)
    else:
        rows = []
        for unit, vals in oferta.items():
            for mes in range(1, 13):
                for dt, servicios_dia in vals.items():
                    rows.append({'unit': unit, 'mes': mes, 'dt': dt, 'servicios_dia': float(servicios_dia)})
        oferta_df = pd.DataFrame(rows)

    if excepciones is not None:
        exc = pd.DataFrame(excepciones)
        if not exc.empty:
            for _, x in exc.iterrows():
                m = (oferta_df['unit'] == x['unit']) & (oferta_df['mes'] == int(x['mes'])) & (oferta_df['dt'] == x['dt'])
                oferta_df.loc[m, 'servicios_dia'] = float(x['servicios_dia'])

    oferta_df = oferta_df[['unit', 'mes', 'dt', 'servicios_dia']].rename(columns={'servicios_dia': 'servicios_dia_actual'})
    p = p.merge(oferta_df, on=['unit', 'mes', 'dt'], how='left')
    p['servicios_dia'] = pd.to_numeric(p['servicios_dia_actual'], errors='coerce').fillna(p['servicios_dia'])
    return p.drop(columns='servicios_dia_actual')

def _dt(dow):
    return 'LV' if dow < 5 else ('Sab' if dow == 5 else 'Dom')


def construir_parametros(rroo_path, afluencia_csv, sheet='2024-2025-Mar2026',
                         biotren_split=(0.20, 0.80), ventana_meses=12):
    """ventana_meses: usa solo los ultimos N meses para estimar servicios_dia y
    pax_por_viaje (refleja el desempenio reciente). None => toda la historia."""
    r = pd.read_excel(rroo_path, sheet_name=sheet)
    r.columns = [c.strip() for c in r.columns]
    r['Fecha'] = pd.to_datetime(r['Fecha'])
    _af_fechas = pd.read_csv(afluencia_csv, parse_dates=['fecha'])['fecha']
    if ventana_meses:
        maxd = min(r['Fecha'].max(), _af_fechas.max())
        corte = maxd - pd.DateOffset(months=ventana_meses)
        r = r[r['Fecha'] >= corte]
    r['unit'] = r['LINEA'].map(UNIT)
    col = [c for c in r.columns if c.startswith('Atraso') and 'Salida' in c][0]
    r['sup'] = r['Salida Real'].isna() | r[col].astype(str).str.contains('SUP', case=False, na=False)
    r = r.dropna(subset=['unit'])
    r['mes'] = r['Fecha'].dt.month
    r['dt'] = r['Fecha'].dt.dayofweek.map(_dt)
    r['d'] = r['Fecha'].dt.date

    perday = r.groupby(['unit', 'd', 'mes', 'dt']).agg(prog=('sup', 'size'), sup=('sup', 'sum')).reset_index()
    perday['oper'] = perday['prog'] - perday['sup']
    sd = perday.groupby(['unit', 'mes', 'dt']).agg(servicios_dia=('prog', 'mean'),
                                                   sup=('sup', 'sum'), prog=('prog', 'sum')).reset_index()
    sd['tasa_sup'] = (sd['sup'] / sd['prog']).round(4)
    sd = sd[['unit', 'mes', 'dt', 'servicios_dia', 'tasa_sup']]
    sd['servicios_dia'] = sd['servicios_dia'].round(1)

    af = pd.read_csv(afluencia_csv, parse_dates=['fecha'])
    if ventana_meses:
        af = af[af['fecha'] >= corte]
    recs = []
    for _, x in af.iterrows():
        if x['servicio'] == 'BIOTREN':
            recs.append(('BIOTREN_L1', x['fecha'], x['pasajeros'] * biotren_split[0]))
            recs.append(('BIOTREN_L2', x['fecha'], x['pasajeros'] * biotren_split[1]))
        else:
            recs.append((x['servicio'], x['fecha'], x['pasajeros']))
    afu = pd.DataFrame(recs, columns=['unit', 'fecha', 'afluencia'])
    afu['d'] = afu['fecha'].dt.date
    j = afu.merge(perday[['unit', 'd', 'oper']], on=['unit', 'd'])
    j = j[j['oper'] > 0]
    j['mes'] = pd.to_datetime(j['fecha']).dt.month
    j['dt'] = pd.to_datetime(j['fecha']).dt.dayofweek.map(_dt)
    j['pxv'] = j['afluencia'] / j['oper']
    pxv = j.groupby(['unit', 'mes', 'dt'])['pxv'].mean().reset_index(name='pax_x_viaje')

    params = sd.merge(pxv, on=['unit', 'mes', 'dt'], how='left')
    full = pd.MultiIndex.from_product([params['unit'].unique(), range(1, 13), DTYPES],
                                      names=['unit', 'mes', 'dt'])
    params = params.set_index(['unit', 'mes', 'dt']).reindex(full).reset_index()
    for c in ['servicios_dia', 'pax_x_viaje', 'tasa_sup']:
        params[c] = params.groupby(['unit', 'dt'])[c].transform(lambda s: s.fillna(s.mean()))
        params[c] = params.groupby('unit')[c].transform(lambda s: s.fillna(s.mean()))
    params['servicios_dia'] = params['servicios_dia'].round(1)
    params['pax_x_viaje'] = params['pax_x_viaje'].round(1)
    params['tasa_sup'] = params['tasa_sup'].round(4)

    # La oferta historica del RROO se utiliza para estimar pax_x_viaje y tasa_sup.
    # El escenario base predictivo se alinea con la oferta vigente informada.
    params = aplicar_oferta_actual(params)
    return params.sort_values(['unit', 'mes', 'dt']).reset_index(drop=True)


def feriados_chile(anio=2027):
    """Retorna feriados nacionales usados por el modelo para el año solicitado.

    Actualmente el calendario operacional se parametriza para 2027, que es el
    horizonte del modelo. Para otro año retorna DataFrame vacío, evitando usar
    feriados de un año incorrecto.
    """
    if int(anio) != 2027:
        return pd.DataFrame(columns=['fecha', 'nombre', 'mes', 'dt_calendario'])
    df = pd.DataFrame(FERIADOS_CHILE_2027).copy()
    df['fecha'] = pd.to_datetime(df['fecha'])
    df['mes'] = df['fecha'].dt.month.astype(int)
    df['dt_calendario'] = df['fecha'].dt.dayofweek.map(_dt)
    return df[['fecha', 'nombre', 'mes', 'dt_calendario']]


def calendario_diario_operacional(anio=2027, units=None):
    """Calendario diario con regla operacional de feriados por unidad.

    Reglas aplicadas:
    - Biotren, Tren Araucanía y Llanquihue-Puerto Montt: los feriados nacionales
      no aportan días operacionales, por lo que su oferta programada efectiva es 0.
    - Laja-Talcahuano: los feriados nacionales operan con oferta de fin de semana.
      Si el feriado cae lunes-viernes se imputa como tipo 'Dom' para efectos de
      oferta; si cae sábado o domingo conserva su tipo de día calendario.
    """
    if units is None:
        units = list(OFERTA_ACTUAL_MODELO.keys()) + TA_TRAMOS
    dates = pd.date_range(f'{anio}-01-01', f'{anio}-12-31', freq='D')
    base = pd.DataFrame({'fecha': dates})
    base['mes'] = base['fecha'].dt.month.astype(int)
    base['dt_calendario'] = base['fecha'].dt.dayofweek.map(_dt)
    fer = feriados_chile(anio)
    if fer.empty:
        base['es_feriado'] = False
        base['feriado'] = ''
    else:
        base = base.merge(fer[['fecha', 'nombre']], on='fecha', how='left')
        base['es_feriado'] = base['nombre'].notna()
        base['feriado'] = base['nombre'].fillna('')
        base = base.drop(columns='nombre')

    rows = []
    for unit in units:
        x = base.copy()
        x['unit'] = unit
        if unit == 'CORTO_LAJA':
            x['opera'] = True
            x['regla_feriado'] = np.where(x['es_feriado'], 'opera_como_fin_de_semana', 'opera_normal')
            x['dt_operacional'] = x['dt_calendario']
            x.loc[x['es_feriado'] & x['dt_calendario'].eq('LV'), 'dt_operacional'] = 'Dom'
        else:
            x['opera'] = ~x['es_feriado']
            x['regla_feriado'] = np.where(x['es_feriado'], 'sin_servicio_en_feriado', 'opera_normal')
            x['dt_operacional'] = x['dt_calendario']
        rows.append(x)
    out = pd.concat(rows, ignore_index=True)
    return out[['unit', 'fecha', 'mes', 'dt_calendario', 'dt_operacional', 'opera', 'es_feriado', 'feriado', 'regla_feriado']]


def dias_operacionales_por_tipo(anio=2027, units=None):
    """Cuenta días operacionales por unidad, mes y tipo de día operativo."""
    cal = calendario_diario_operacional(anio=anio, units=units)
    cal = cal[cal['opera']].copy()
    g = cal.groupby(['unit', 'mes', 'dt_operacional']).size().reset_index(name='n_dias')
    g = g.rename(columns={'dt_operacional': 'dt'})
    if units is None:
        units = list(OFERTA_ACTUAL_MODELO.keys()) + TA_TRAMOS
    full = pd.MultiIndex.from_product([units, range(1, 13), DTYPES], names=['unit', 'mes', 'dt'])
    g = g.set_index(['unit', 'mes', 'dt']).reindex(full, fill_value=0).reset_index()
    return g


def calendario_operacional_resumen(anio=2027):
    """Resumen para mostrar y auditar el calendario operacional utilizado."""
    units = list(OFERTA_ACTUAL_MODELO.keys()) + TA_TRAMOS
    cal = calendario_diario_operacional(anio=anio, units=units)
    g = cal.groupby(['unit', 'mes', 'dt_operacional'], as_index=False).agg(
        n_dias_operacionales=('opera', 'sum'),
        feriados_sin_servicio=('regla_feriado', lambda s: int((s == 'sin_servicio_en_feriado').sum())),
        feriados_como_fin_semana=('regla_feriado', lambda s: int((s == 'opera_como_fin_de_semana').sum())),
    ).rename(columns={'dt_operacional': 'dt'})
    g['servicio'] = g['unit'].map(unidad_a_servicio()).fillna(g['unit'].map(lambda u: 'TREN_ARAUCANIA' if u in TA_TRAMOS else u))
    return g[['servicio', 'unit', 'mes', 'dt', 'n_dias_operacionales', 'feriados_sin_servicio', 'feriados_como_fin_semana']]


def dias_por_tipo(anio=2027):
    """Conteo calendario simple, mantenido por compatibilidad.

    Para la proyección principal se usa dias_operacionales_por_tipo(), porque
    incorpora feriados y reglas por servicio.
    """
    d = pd.date_range(f'{anio}-01-01', f'{anio}-12-31')
    df = pd.DataFrame({'mes': d.month, 'dt': d.dayofweek.map(_dt)})
    return df.groupby(['mes', 'dt']).size().reset_index(name='n_dias')



def unidad_a_servicio():
    rows = {}
    for s, units in UNIDADES_DE.items():
        for u in units:
            rows[u] = s
    return rows


# Elasticidades de respuesta de demanda ante cambios de oferta programada.
# Se usan valores inferiores a 1 para representar rendimientos marginales decrecientes:
# un aumento de servicios mejora accesibilidad/frecuencia, pero no genera pasajeros
# en la misma proporción que la oferta adicional.
ELASTICIDAD_OFERTA_SERVICIO = {
    'BIOTREN': 0.55,
    'CORTO_LAJA': 0.38,
    'TREN_ARAUCANIA': 0.42,
    'LLANQUIHUE_PM': 0.35,
}

# Ajuste de nivel construido con información histórica y operacional disponible.
# Funciona como calibrador de productividad base y no como referencia visible.
AJUSTE_NIVEL_SERVICIO = {
    'BIOTREN': 1.004,
    'CORTO_LAJA': 1.133,
    'TREN_ARAUCANIA': 0.955,
    'LLANQUIHUE_PM': 1.000,
}

# Recuperacion operacional especifica para Laja-Talcahuano.
# Se utiliza porque el escenario 2027 asume menor afectacion/supresion y
# recuperacion de confiabilidad respecto del comportamiento observado en 2025-2026,
# pero sin replicar directamente el nivel alto de 2024.
RECUPERACION_LAJA = {
    'tasa_sup_max': 0.010,
    'criterio': 'capar supresion historica a 1% y aplicar recuperacion parcial de productividad hacia escenario ~540 mil',
}

# Intensidad con que se aproxima la productividad mensual al patrón histórico.
# 0 = sólo productividad/oferta observada; 1 = calza completamente la estacionalidad histórica.
# Se deja por debajo de 1 para no volver a un modelo de simple distribución anual.
FUERZA_ESTACIONALIDAD = {
    'BIOTREN': 0.55,
    'CORTO_LAJA': 0.55,
    'TREN_ARAUCANIA': 0.50,
    'LLANQUIHUE_PM': 0.85,
}

# Regularización del perfil mensual Biotren 2027.
# Se aplica sólo sobre el bloque marzo-abril para evitar peaks mensuales no
# respaldados por el comportamiento histórico observado. El ajuste conserva
# la suma del bloque y no transforma el modelo en una distribución anual fija.
AJUSTE_BIOTREN_MARZO_ABRIL = {
    'activo': True,
    'meses': (3, 4),
    'participacion_marzo': 0.502,
    'criterio': 'regularizar sólo el bloque marzo-abril de Biotren, manteniendo la suma del bloque y la sensibilidad mensual a la oferta',
}

RAMP_NUEVA_OFERTA = {
    'BIOTREN': 0.55,
    'CORTO_LAJA': 0.45,
    'TREN_ARAUCANIA': 0.45,
    'LLANQUIHUE_PM': 0.40,
}

# Parámetros editables de recalibración operacional 2027. Se aplican después
# del motor mensual-elástico y antes de OD, ingresos, backtesting e incertidumbre.
RECALIBRACION_2027 = {
    'activa': True,
    'biotren': {
        'objetivo_base_intermedio': 12_800_000.0,
        'objetivo_ocupacion_pasajeros_por_servicio': 300.0,
        'meses_afectacion_l2_fds': (1, 2),
        'factor_afectacion_l2_fds': 0.32,
        'meses_revision_estival': (1, 2),
        'meses_ajuste_ocupacion': tuple(range(1, 13)),
        'tolerancia_ocupacion_pasajeros_por_servicio': 2.0,
    },
    'llanquihue_pm': {
        'demanda_laboral_promedio_objetivo_mar_dic': 1_500.0,
        'meses_ancla_laboral': tuple(range(3, 13)),
        'factor_novedad_enero': 0.78,
        'factor_novedad_febrero': 0.78,
        'no_forzar_1500_en_todos_los_meses': True,
        'amplitud_estacional_mar_dic': 0.08,
    },
    'tren_araucania': {
        'servicios_lv_victoria_temuco': 11.0,
        'umbral_marzo_vs_abr_dic': 1.18,
        # Ajuste de nivel mensual previo a la futura etapa MOD TA.
        # Mayo se refuerza para mantener una lectura coherente con el bloque
        # marzo-mayo observado en 2026, sin replicarlo mecánicamente. El resto
        # de los meses recibe sólo un incremento marginal para preservar el perfil
        # mensual 2025, especialmente la lectura estival de enero-febrero.
        'mes_foco_refuerzo': 5,
        'afluencia_mes_foco_objetivo': 81_000.0,
        'factor_incremento_marginal_resto_meses': 1.02,
    },
}



def servicios_comerciales_biotren_mensuales(anio=2027, oferta_df=None):
    """Calcula servicios comerciales mensuales de Biotren desde la oferta vigente."""
    if oferta_df is None:
        oferta_df = oferta_actual_df(mensual=True)
    cal = dias_operacionales_por_tipo(anio, units=['BIOTREN_L1', 'BIOTREN_L2'])
    bi = oferta_df[oferta_df['unit'].isin(['BIOTREN_L1', 'BIOTREN_L2'])].copy()
    bi = bi.merge(cal, on=['unit', 'mes', 'dt'], how='left')
    bi['n_dias'] = pd.to_numeric(bi['n_dias'], errors='coerce').fillna(0.0)
    bi['servicios_mes'] = pd.to_numeric(bi['servicios_dia'], errors='coerce').fillna(0.0) * bi['n_dias']
    return bi.groupby('mes')['servicios_mes'].sum().reindex(range(1, 13), fill_value=0.0).astype(float)



def servicios_acoplados_l2_lv_mensuales(anio=2027):
    """Servicios L2 L-V acoplados por mes como capacidad efectiva, no frecuencia."""
    valores = {mes: (3.0 if mes >= 5 else 0.0) for mes in range(1, 13)}
    return pd.Series(valores, dtype=float)


def diagnostico_capacidad_biotren_mensual(anio=2027, oferta_df=None):
    """Tabla mensual que separa frecuencia comercial y capacidad efectiva Biotren."""
    if oferta_df is None:
        oferta_df = oferta_actual_df(mensual=True)
    plan = oferta_df[oferta_df['unit'].isin(['BIOTREN_L1', 'BIOTREN_L2'])].copy()
    tabla = plan.pivot_table(index='mes', columns=['unit', 'dt'], values='servicios_dia', aggfunc='first').reindex(range(1, 13))
    def col(unit, dt):
        if (unit, dt) in tabla.columns:
            return tabla[(unit, dt)].astype(float).fillna(0.0)
        return pd.Series(0.0, index=tabla.index, dtype=float)
    out = pd.DataFrame({
        'mes': range(1, 13),
        'l1_lv': col('BIOTREN_L1', 'LV').values,
        'l1_sab': col('BIOTREN_L1', 'Sab').values,
        'l1_dom': col('BIOTREN_L1', 'Dom').values,
        'l2_lv': col('BIOTREN_L2', 'LV').values,
        'l2_sab': col('BIOTREN_L2', 'Sab').values,
        'l2_dom': col('BIOTREN_L2', 'Dom').values,
    })
    acoplados_dia = servicios_acoplados_l2_lv_mensuales(anio).reindex(range(1, 13)).fillna(0.0)
    dias_lv = dias_operacionales_por_tipo(anio, units=['BIOTREN_L2'])
    dias_lv = dias_lv[dias_lv['dt'].eq('LV')].set_index('mes')['n_dias'].reindex(range(1, 13)).fillna(0.0).astype(float)
    comerciales = servicios_comerciales_biotren_mensuales(anio, oferta_df=oferta_df).reindex(range(1, 13)).fillna(0.0)
    acoplados_mes = acoplados_dia * dias_lv
    out['servicios_acoplados_l2_lv'] = acoplados_dia.values
    out['servicios_comerciales_mensuales'] = comerciales.values
    out['servicios_acoplados_mensuales'] = acoplados_mes.values
    out['servicios_equivalentes_capacidad_mensuales'] = (comerciales + acoplados_mes).values
    out['diferencia_capacidad_vs_comercial'] = acoplados_mes.values
    return out

# Bandas diagnósticas de ocupación Biotren. No recalibran demanda ni modifican oferta.
BANDAS_FUNCIONAMIENTO_BIOTREN = {
    "Baja utilización": {"min": None, "max": 270.0, "lectura": "Mes con baja carga relativa; revisar captación, estacionalidad u oferta."},
    "Operación estable": {"min": 270.0, "max": 300.0, "lectura": "Uso razonable de la oferta; cercano al rango objetivo."},
    "Alta utilización": {"min": 300.0, "max": 330.0, "lectura": "Alta eficiencia operacional; requiere monitoreo."},
    "Tensión operacional": {"min": 330.0, "max": None, "lectura": "Posible tensión de capacidad, especialmente en punta o línea específica."},
}


def _banda_funcionamiento_biotren(pax_servicio_comercial: float) -> str:
    """Clasifica la ocupación mensual por servicio comercial Biotren."""
    valor = float(pax_servicio_comercial) if pd.notna(pax_servicio_comercial) else 0.0
    if valor < 270.0:
        return "Baja utilización"
    if valor < 300.0:
        return "Operación estable"
    if valor <= 330.0:
        return "Alta utilización"
    return "Tensión operacional"


def diagnostico_ocupacion_biotren_mensual(serie_biotren, anio=2027, oferta_df=None):
    """Construye diagnóstico mensual de ocupación Biotren.

    Separa servicios comerciales de servicios equivalentes de capacidad. Los
    servicios L2 acoplados se suman sólo al denominador técnico de capacidad
    equivalente y no alteran la frecuencia comercial.
    """
    serie = pd.Series(serie_biotren, dtype=float).copy()
    serie.index = [int(str(i)[5:7]) if isinstance(i, str) and "-" in str(i) else int(i) for i in serie.index]
    serie = serie.reindex(range(1, 13)).fillna(0.0)

    capacidad = diagnostico_capacidad_biotren_mensual(anio=anio, oferta_df=oferta_df).set_index("mes")
    servicios_com = capacidad["servicios_comerciales_mensuales"].reindex(range(1, 13)).astype(float)
    servicios_eq = capacidad["servicios_equivalentes_capacidad_mensuales"].reindex(range(1, 13)).astype(float)

    out = pd.DataFrame({
        "mes": range(1, 13),
        "afluencia_biotren": serie.values,
        "servicios_comerciales": servicios_com.values,
        "servicios_equivalentes_capacidad": servicios_eq.values,
        "servicios_acoplados_l2_lv": capacidad["servicios_acoplados_l2_lv"].reindex(range(1, 13)).astype(float).values,
        "servicios_acoplados_mensuales": capacidad["servicios_acoplados_mensuales"].reindex(range(1, 13)).astype(float).values,
    })
    out["pax_servicio_comercial"] = np.where(
        out["servicios_comerciales"] > 0,
        out["afluencia_biotren"] / out["servicios_comerciales"],
        np.nan,
    )
    out["pax_capacidad_equivalente"] = np.where(
        out["servicios_equivalentes_capacidad"] > 0,
        out["afluencia_biotren"] / out["servicios_equivalentes_capacidad"],
        np.nan,
    )
    out["diferencia_pax_comercial_vs_capacidad"] = out["pax_servicio_comercial"] - out["pax_capacidad_equivalente"]
    out["capacidad_pax_comercial"] = out["servicios_comerciales"] * CAPACIDAD_REFERENCIA_BIOTREN_PAX_TREN
    out["capacidad_pax_equivalente"] = out["servicios_equivalentes_capacidad"] * CAPACIDAD_REFERENCIA_BIOTREN_PAX_TREN
    out["tasa_ocupacion_comercial_pct"] = np.where(
        out["capacidad_pax_comercial"] > 0,
        out["afluencia_biotren"] / out["capacidad_pax_comercial"],
        np.nan,
    )
    out["tasa_ocupacion_equivalente_pct"] = np.where(
        out["capacidad_pax_equivalente"] > 0,
        out["afluencia_biotren"] / out["capacidad_pax_equivalente"],
        np.nan,
    )
    out["capacidad_referencia_tren"] = CAPACIDAD_REFERENCIA_BIOTREN_PAX_TREN
    total = float(out["afluencia_biotren"].sum())
    out["participacion_mensual_afluencia"] = out["afluencia_biotren"] / total if total else 0.0
    out["banda_funcionamiento"] = out["pax_servicio_comercial"].map(_banda_funcionamiento_biotren)
    out["observacion_metodologica"] = np.where(
        out["servicios_acoplados_mensuales"] > 0,
        "Incluye capacidad equivalente por acoplados L2; no aumenta frecuencia comercial.",
        "Frecuencia comercial y capacidad equivalente coinciden en el mes.",
    )
    return out


def resumen_ocupacion_biotren(serie_biotren, anio=2027, oferta_df=None):
    """Resume ocupación anual y mensual Biotren con bandas diagnósticas."""
    diag = diagnostico_ocupacion_biotren_mensual(serie_biotren, anio=anio, oferta_df=oferta_df)
    total = float(diag["afluencia_biotren"].sum())
    servicios_com = float(diag["servicios_comerciales"].sum())
    servicios_eq = float(diag["servicios_equivalentes_capacidad"].sum())
    pax_servicio = total / servicios_com if servicios_com else np.nan
    pax_capacidad = total / servicios_eq if servicios_eq else np.nan
    capacidad_pax_com = float(diag["capacidad_pax_comercial"].sum())
    capacidad_pax_eq = float(diag["capacidad_pax_equivalente"].sum())
    tasa_ocup_com = total / capacidad_pax_com if capacidad_pax_com else np.nan
    tasa_ocup_eq = total / capacidad_pax_eq if capacidad_pax_eq else np.nan
    idx_max = diag["pax_servicio_comercial"].idxmax()
    idx_min = diag["pax_servicio_comercial"].idxmin()
    return {
        "total_anual_biotren": total,
        "servicios_comerciales_anuales": servicios_com,
        "servicios_equivalentes_capacidad_anuales": servicios_eq,
        "pax_servicio_comercial_anual": pax_servicio,
        "pax_capacidad_equivalente_anual": pax_capacidad,
        "capacidad_pax_comercial_anual": capacidad_pax_com,
        "capacidad_pax_equivalente_anual": capacidad_pax_eq,
        "tasa_ocupacion_comercial_anual": tasa_ocup_com,
        "tasa_ocupacion_equivalente_anual": tasa_ocup_eq,
        "capacidad_referencia_tren": CAPACIDAD_REFERENCIA_BIOTREN_PAX_TREN,
        "mes_mayor_pax_servicio_comercial": int(diag.loc[idx_max, "mes"]),
        "valor_mayor_pax_servicio_comercial": float(diag.loc[idx_max, "pax_servicio_comercial"]),
        "mes_menor_pax_servicio_comercial": int(diag.loc[idx_min, "mes"]),
        "valor_menor_pax_servicio_comercial": float(diag.loc[idx_min, "pax_servicio_comercial"]),
        "meses_por_banda": diag["banda_funcionamiento"].value_counts().reindex(BANDAS_FUNCIONAMIENTO_BIOTREN.keys(), fill_value=0).astype(int).to_dict(),
        "diagnostico_mensual": diag,
    }


def _referencia_historica_biotren_mensual():
    """Referencia mensual observada/estimada para ponderar ajustes de Biotren."""
    path = DATA_DIR / 'afluencia_mensual_modelo.csv'
    if not path.exists():
        return pd.DataFrame(columns=['anio', 'mes', 'pax_norm'])
    hist = pd.read_csv(path)
    hist = hist[hist['servicio'].eq('BIOTREN')].copy()
    hist['periodo'] = pd.PeriodIndex(hist['mes'], freq='M')
    hist['anio'] = hist['periodo'].dt.year.astype(int)
    hist['mes'] = hist['periodo'].dt.month.astype(int)
    hist['pax_norm'] = pd.to_numeric(hist['pax_norm'], errors='coerce')
    return hist[hist['anio'].isin([2024, 2025, 2026])][['anio', 'mes', 'pax_norm']].dropna()




BIOTREN_TOTAL_ANUAL_REFERENCIA_2027 = 13_095_299.0
BIOTREN_PESOS_PARTICIPACION_RECIENTE = {2024: 0.25, 2025: 0.35, 2026: 0.40}


def participaciones_historicas_biotren():
    """Participación mensual Biotren 2024, 2025 y cierre 2026 desde referencias versionadas."""
    path = DATA_DIR / 'referencias_cierre_2026' / 'afluencia_historica_cierre_2026_long.csv'
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df = df[df['servicio'].astype(str).eq('Biotren')].copy()
    df['anio'] = pd.to_numeric(df['anio'], errors='coerce').astype('Int64')
    df['mes'] = pd.to_numeric(df['mes_num'], errors='coerce').astype('Int64')
    df['afluencia'] = pd.to_numeric(df['afluencia'], errors='coerce')
    df = df[df['anio'].isin([2024, 2025, 2026]) & df['mes'].between(1, 12) & df['afluencia'].notna()].copy()
    total = df.groupby('anio')['afluencia'].transform('sum')
    df['participacion'] = df['afluencia'] / total.replace(0, np.nan)
    return df[['anio', 'mes', 'afluencia', 'participacion', 'tipo_dato', 'fuente']]


def diagnostico_redistribucion_biotren_2027(serie_vigente, serie_redistribuida=None, anio=2027, servicios_mensuales=None):
    """Construye tabla mensual de participaciones históricas, escenario vigente y redistribuido."""
    vigente = pd.Series(serie_vigente, dtype=float).copy()
    vigente.index = [int(str(i)[5:7]) if isinstance(i, str) and '-' in str(i) else int(i) for i in vigente.index]
    vigente = vigente.reindex(range(1, 13)).fillna(0.0)
    if serie_redistribuida is None:
        redis = vigente.copy()
    else:
        redis = pd.Series(serie_redistribuida, dtype=float).copy()
        redis.index = [int(str(i)[5:7]) if isinstance(i, str) and '-' in str(i) else int(i) for i in redis.index]
        redis = redis.reindex(range(1, 13)).fillna(0.0)
    hist = participaciones_historicas_biotren()
    piv = hist.pivot_table(index='mes', columns='anio', values='participacion', aggfunc='sum').reindex(range(1, 13))
    for y in [2024, 2025, 2026]:
        if y not in piv.columns:
            piv[y] = np.nan
    promedio = piv[[2024, 2025, 2026]].mean(axis=1)
    pesos = pd.Series(BIOTREN_PESOS_PARTICIPACION_RECIENTE, dtype=float)
    ponderado = piv[[2024, 2025, 2026]].mul(pesos, axis=1).sum(axis=1) / piv[[2024, 2025, 2026]].notna().mul(pesos, axis=1).sum(axis=1)
    if servicios_mensuales is None:
        servicios = servicios_comerciales_biotren_mensuales(anio)
    else:
        servicios = pd.Series(servicios_mensuales, dtype=float).copy()
        servicios.index = [int(str(i)[5:7]) if isinstance(i, str) and '-' in str(i) else int(i) for i in servicios.index]
        servicios = servicios.reindex(range(1, 13)).fillna(0.0)
    vtot = float(vigente.sum()) or 1.0
    rtot = float(redis.sum()) or 1.0
    rows = []
    for mes in range(1, 13):
        dif_pp = (float(vigente.loc[mes]) / vtot - float(ponderado.loc[mes])) * 100
        if dif_pp < -0.35:
            diag = 'Participación 2027 vigente bajo el patrón reciente.'
            rec = 'Aumentar participación usando promedio ponderado reciente y oferta mensual.'
        elif dif_pp > 0.35:
            diag = 'Participación 2027 vigente sobre el patrón reciente.'
            rec = 'Moderar participación para conservar estacionalidad anual.'
        else:
            diag = 'Participación 2027 vigente dentro del rango reciente.'
            rec = 'Mantener ajuste acotado por oferta y suavización.'
        rows.append({
            'mes': mes,
            'afluencia_2027_vigente': float(vigente.loc[mes]),
            'participacion_2027_vigente': float(vigente.loc[mes]) / vtot,
            'participacion_2024': float(piv.loc[mes, 2024]),
            'participacion_2025': float(piv.loc[mes, 2025]),
            'participacion_cierre_2026': float(piv.loc[mes, 2026]),
            'participacion_promedio_reciente': float(promedio.loc[mes]),
            'participacion_ponderada_reciente': float(ponderado.loc[mes]),
            'participacion_2027_redistribuida': float(redis.loc[mes]) / rtot,
            'diferencia_pp_vs_ponderado_vigente': dif_pp,
            'afluencia_2027_redistribuida': float(redis.loc[mes]),
            'diferencia_afluencia': float(redis.loc[mes] - vigente.loc[mes]),
            'servicios_comerciales_2027': float(servicios.loc[mes]),
            'pasajeros_por_servicio_vigente': float(vigente.loc[mes] / servicios.loc[mes]) if servicios.loc[mes] else np.nan,
            'pasajeros_por_servicio_redistribuido': float(redis.loc[mes] / servicios.loc[mes]) if servicios.loc[mes] else np.nan,
            'diagnostico': diag,
            'recomendacion': rec,
            'observacion_metodologica': 'Participación objetivo combina 80% patrón histórico ponderado 2024-2026 y 20% participación de servicios comerciales 2027; total anual Biotren conservado.',
        })
    return pd.DataFrame(rows)


def redistribuir_biotren_2027_por_participacion(serie_vigente, anio=2027, servicios_mensuales=None):
    """Redistribuye el total anual Biotren según participación histórica reciente y oferta."""
    vigente = pd.Series(serie_vigente, dtype=float).copy()
    vigente.index = [int(str(i)[5:7]) if isinstance(i, str) and '-' in str(i) else int(i) for i in vigente.index]
    vigente = vigente.reindex(range(1, 13)).fillna(0.0)
    total = BIOTREN_TOTAL_ANUAL_REFERENCIA_2027
    diag_base = diagnostico_redistribucion_biotren_2027(vigente, vigente, anio=anio, servicios_mensuales=servicios_mensuales)
    hist_share = diag_base.set_index('mes')['participacion_ponderada_reciente'].astype(float).reindex(range(1, 13))
    if servicios_mensuales is None:
        servicios = servicios_comerciales_biotren_mensuales(anio)
    else:
        servicios = pd.Series(servicios_mensuales, dtype=float).copy()
        servicios.index = [int(str(i)[5:7]) if isinstance(i, str) and '-' in str(i) else int(i) for i in servicios.index]
        servicios = servicios.reindex(range(1, 13)).fillna(0.0)
    oferta_share = servicios / servicios.sum()
    target_share = (0.80 * hist_share + 0.20 * oferta_share).clip(lower=0.0)
    target_share = target_share / target_share.sum()
    raw = target_share * total
    redondeado = np.floor(raw).astype(int)
    residuo = int(round(total - redondeado.sum()))
    if residuo > 0:
        orden = (raw - redondeado).sort_values(ascending=False).index[:residuo]
        redondeado.loc[orden] += 1
    redis = redondeado.astype(float)
    diagnostico = diagnostico_redistribucion_biotren_2027(vigente, redis, anio=anio, servicios_mensuales=servicios)
    return redis, diagnostico

def _ajustar_biotren_por_ocupacion(post, anio, cfg):
    """Distribuye ajuste mensual para aproximar ocupación anual objetivo sin factor plano."""
    servicios = servicios_comerciales_biotren_mensuales(anio)
    objetivo_pps = float(cfg['objetivo_ocupacion_pasajeros_por_servicio'])
    total_objetivo = float(servicios.sum() * objetivo_pps)
    total_actual = float(post.sum())
    ajuste_total = max(0.0, total_objetivo - total_actual)
    ajuste = pd.Series(0.0, index=range(1, 13), dtype=float)
    if ajuste_total <= 0:
        return post.copy(), ajuste, servicios, total_objetivo, pd.Series('', index=range(1, 13), dtype=object)

    hist = _referencia_historica_biotren_mensual()
    hist_max = hist.groupby('mes')['pax_norm'].max().reindex(range(1, 13)).fillna(post)
    pps = post / servicios.replace(0, np.nan)
    brecha_ocupacion = ((objetivo_pps - pps).clip(lower=0.0) * servicios).fillna(0.0)
    # Enero-febrero se revisan contra máximos históricos recientes para evitar meses estivales artificialmente bajos.
    estival = pd.Series(0.0, index=range(1, 13), dtype=float)
    for mes in cfg.get('meses_revision_estival', (1, 2)):
        estival.loc[int(mes)] = max(0.0, float(hist_max.loc[int(mes)] - post.loc[int(mes)]))
    meses = list(cfg.get('meses_ajuste_ocupacion', range(1, 13)))
    pesos = (brecha_ocupacion.reindex(meses).fillna(0.0) + estival.reindex(meses).fillna(0.0)).clip(lower=0.0)
    if pesos.sum() <= 0:
        pesos = post.reindex(meses).clip(lower=0.0)
    pesos = pesos / pesos.sum()
    ajuste.loc[meses] = ajuste_total * pesos
    razones = pd.Series('ajuste moderado por ocupación anual y oferta mensual', index=range(1, 13), dtype=object)
    for mes in cfg.get('meses_revision_estival', (1, 2)):
        razones.loc[int(mes)] = 'revisión estival contra referencia histórica reciente y ocupación mensual'
    for mes in [m for m in meses if brecha_ocupacion.loc[m] > 0 and m not in cfg.get('meses_revision_estival', (1, 2))]:
        razones.loc[int(mes)] = 'cierre de brecha de ocupación mensual respecto de referencia anual'
    return post + ajuste, ajuste, servicios, total_objetivo, razones

def _escalar_detalle_servicio(detalle, servicio, factores_por_mes):
    out = detalle.copy()
    for mes, factor in factores_por_mes.items():
        m = out['servicio'].eq(servicio) & out['mes'].astype(int).eq(int(mes))
        out.loc[m, 'afl'] = pd.to_numeric(out.loc[m, 'afl'], errors='coerce').fillna(0.0) * float(factor)
        if 'demanda_base_mensual' in out.columns:
            out.loc[m, 'demanda_base_mensual'] = pd.to_numeric(out.loc[m, 'demanda_base_mensual'], errors='coerce').fillna(0.0) * float(factor)
    return out


def recalibrar_escenario_2027(detalle, anio=2027):
    """Aplica supuestos operacionales 2027 trazables sin cambiar backtesting.

    Biotren: baja progresiva a un total intermedio, afectación L2 en fines de
    semana de enero-febrero y ajuste residual en meses laborales.
    Llanquihue-Puerto Montt: calibración marzo-diciembre por promedio de día
    laboral cercano a 1.500, con reducción de enero-febrero por menor novedad.
    Tren Araucanía se recalcula desde la oferta por tramo; aquí sólo se suaviza
    un marzo metodológicamente excesivo conservando su total anual.
    """
    if not RECALIBRACION_2027.get('activa', True):
        return detalle.copy(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    d = detalle.copy()
    diag = []
    mensual_rows = []

    # Biotren.
    cfg = RECALIBRACION_2027['biotren']
    bi = d[d['servicio'].eq('BIOTREN')].groupby('mes')['afl'].sum().astype(float)
    total_ant = float(bi.sum())
    f_base = float(cfg['objetivo_base_intermedio']) / total_ant if total_ant else 1.0
    inter = bi * f_base
    cal = calendario_diario_operacional(anio, units=['BIOTREN_L2'])
    fds = cal[(cal['unit'].eq('BIOTREN_L2')) & (cal['opera'])].assign(es_fds=lambda x: x['dt_calendario'].isin(['Sab','Dom']))
    part_fds = fds.groupby('mes')['es_fds'].mean().reindex(range(1,13)).fillna(0.0)
    unit_mes = d[d['servicio'].eq('BIOTREN')].groupby(['unit','mes'])['afl'].sum().unstack(0).fillna(0.0)
    part_l2 = (unit_mes.get('BIOTREN_L2', 0.0) / unit_mes.sum(axis=1).replace(0, np.nan)).reindex(range(1,13)).fillna(0.0)
    post = inter.copy()
    impacto_l2 = pd.Series(0.0, index=range(1,13))
    for mes in cfg['meses_afectacion_l2_fds']:
        impacto_l2.loc[mes] = inter.loc[mes] * part_l2.loc[mes] * part_fds.loc[mes] * float(cfg['factor_afectacion_l2_fds'])
        post.loc[mes] -= impacto_l2.loc[mes]
    post_conservador = post.copy()
    vigente_pre_redistribucion, ajuste_ocupacion, servicios_biotren, objetivo_total_ocupacion, razones_biotren = _ajustar_biotren_por_ocupacion(post, anio, cfg)
    servicios_biotren_plan = d[d['servicio'].eq('BIOTREN')].groupby('mes')['viajes_programados_plan'].sum().reindex(range(1, 13)).fillna(servicios_biotren)
    post, diagnostico_participacion_biotren = redistribuir_biotren_2027_por_participacion(vigente_pre_redistribucion, anio=anio, servicios_mensuales=servicios_biotren_plan)
    servicios_biotren = servicios_biotren_plan.astype(float)
    factores = (post / bi.replace(0, np.nan)).replace([np.inf,-np.inf], np.nan).fillna(1.0).to_dict()
    d = _escalar_detalle_servicio(d, 'BIOTREN', factores)
    for mes in range(1,13):
        mensual_rows.append({
            'mes': mes,
            'servicio': 'BIOTREN',
            'proyeccion_anterior': post_conservador.loc[mes],
            'proyeccion_recalibrada': post.loc[mes],
            'proyeccion_vigente_pre_redistribucion': vigente_pre_redistribucion.loc[mes],
            'diferencia': post.loc[mes]-vigente_pre_redistribucion.loc[mes],
            'factor_o_ajuste_aplicado': f"base={f_base:.6f}; impacto_l2_fds={impacto_l2.loc[mes]:.0f}; ajuste_ocupacion={ajuste_ocupacion.loc[mes]:.0f}; redistribucion_participacion={post.loc[mes]-vigente_pre_redistribucion.loc[mes]:.0f}; servicios_comerciales={servicios_biotren.loc[mes]:.0f}; criterio=participación histórica reciente, oferta mensual y conservación del total anual",
        })
    diag.append({'servicio':'BIOTREN','indicador':'total_pre_ajuste_ocupacion','valor':float(post_conservador.sum())})
    diag.append({'servicio':'BIOTREN','indicador':'total_anterior_motor','valor':total_ant})
    diag.append({'servicio':'BIOTREN','indicador':'total_intermedio_base','valor':float(inter.sum())})
    diag.append({'servicio':'BIOTREN','indicador':'total_recalibrado','valor':float(post.sum())})
    diag.append({'servicio':'BIOTREN','indicador':'total_vigente_pre_redistribucion','valor':float(vigente_pre_redistribucion.sum())})
    diag.append({'servicio':'BIOTREN','indicador':'servicios_comerciales_anuales','valor':float(servicios_biotren.sum())})
    diag.append({'servicio':'BIOTREN','indicador':'pasajeros_por_servicio_pre_ajuste_ocupacion','valor':float(post_conservador.sum()/servicios_biotren.sum())})
    diag.append({'servicio':'BIOTREN','indicador':'pasajeros_por_servicio_recalibrado','valor':float(post.sum()/servicios_biotren.sum())})
    diag.append({'servicio':'BIOTREN','indicador':'objetivo_ocupacion_pasajeros_por_servicio','valor':float(cfg['objetivo_ocupacion_pasajeros_por_servicio'])})
    diag.append({'servicio':'BIOTREN','indicador':'objetivo_total_ocupacion','valor':float(objetivo_total_ocupacion)})
    diag.append({'servicio':'BIOTREN','indicador':'impacto_l2_fds_ene_feb','valor':float(impacto_l2.sum())})
    diag.append({'servicio':'BIOTREN','indicador':'ajuste_ocupacion_total','valor':float(ajuste_ocupacion.sum())})
    diag.append({'servicio':'BIOTREN','indicador':'participaciones_redistribuidas_suman','valor':float(diagnostico_participacion_biotren['participacion_2027_redistribuida'].sum())})

    # Llanquihue-Puerto Montt.
    cfg = RECALIBRACION_2027['llanquihue_pm']
    ll = d[d['servicio'].eq('LLANQUIHUE_PM')].groupby('mes')['afl'].sum().astype(float)
    newll = ll.copy()
    newll.loc[1] = ll.loc[1] * float(cfg['factor_novedad_enero'])
    newll.loc[2] = ll.loc[2] * float(cfg['factor_novedad_febrero'])
    lv = dias_operacionales_por_tipo(anio, units=['LLANQUIHUE_PM'])
    lv = lv[(lv.unit.eq('LLANQUIHUE_PM')) & (lv.dt.eq('LV'))].set_index('mes')['n_dias'].reindex(range(1,13)).fillna(0.0)
    meses = list(cfg['meses_ancla_laboral'])
    raw_ratio = (ll.reindex(meses) / lv.reindex(meses).replace(0,np.nan)).replace([np.inf,-np.inf], np.nan)
    rel = (raw_ratio / raw_ratio.mean()).fillna(1.0)
    amp = float(cfg['amplitud_estacional_mar_dic'])
    rel = 1.0 + (rel - 1.0) * amp
    for mes in meses:
        newll.loc[mes] = float(cfg['demanda_laboral_promedio_objetivo_mar_dic']) * float(lv.loc[mes]) * float(rel.loc[mes])
    factores = (newll / ll.replace(0, np.nan)).replace([np.inf,-np.inf], np.nan).fillna(1.0).to_dict()
    d = _escalar_detalle_servicio(d, 'LLANQUIHUE_PM', factores)
    for mes in range(1,13):
        mensual_rows.append({'mes': mes, 'servicio': 'LLANQUIHUE_PM', 'proyeccion_anterior': ll.loc[mes], 'proyeccion_recalibrada': newll.loc[mes], 'diferencia': newll.loc[mes]-ll.loc[mes], 'factor_o_ajuste_aplicado': 'efecto_novedad_ene_feb' if mes in (1,2) else 'calibracion_promedio_laboral_mar_dic'})
    diag.append({'servicio':'LLANQUIHUE_PM','indicador':'total_anterior','valor':float(ll.sum())})
    diag.append({'servicio':'LLANQUIHUE_PM','indicador':'total_recalibrado','valor':float(newll.sum())})
    diag.append({'servicio':'LLANQUIHUE_PM','indicador':'promedio_laboral_mar_dic','valor':float(newll.reindex(meses).sum()/lv.reindex(meses).sum())})

    # Tren Araucanía: suavizado metodológico de marzo y refuerzo mensual 2027.
    # El refuerzo se aplica antes de montar la MOD TA: mayo se ajusta para que
    # el bloque marzo-abril-mayo conserve una relación similar a 2026, sin copiar
    # exactamente los niveles 2026. El resto de los meses recibe un incremento
    # marginal, manteniendo el perfil mensual 2025 como patrón estacional principal.
    cfg_ta = RECALIBRACION_2027['tren_araucania']
    ta = d[d['servicio'].eq('TREN_ARAUCANIA')].groupby('mes')['afl'].sum().astype(float)
    ta_suavizada = ta.copy()
    prom_abr_dic = float(ta.reindex(range(4,13)).mean())
    ratio_mar = float(ta.loc[3] / prom_abr_dic) if prom_abr_dic else 0.0
    umbral = float(cfg_ta['umbral_marzo_vs_abr_dic'])
    ajuste_marzo = 0.0
    if ratio_mar > umbral:
        exceso = ta.loc[3] - prom_abr_dic * umbral
        ajuste_marzo = -float(exceso)
        ta_suavizada.loc[3] -= exceso
        pesos = ta_suavizada.reindex(range(4,13)) / ta_suavizada.reindex(range(4,13)).sum()
        ta_suavizada.loc[list(range(4,13))] += exceso * pesos

    ta_new = ta_suavizada.copy()
    mes_foco = int(cfg_ta.get('mes_foco_refuerzo', 5))
    factor_marginal = float(cfg_ta.get('factor_incremento_marginal_resto_meses', 1.0))
    for mes in range(1, 13):
        if mes != mes_foco:
            ta_new.loc[mes] = ta_new.loc[mes] * factor_marginal
    objetivo_mes_foco = cfg_ta.get('afluencia_mes_foco_objetivo')
    if objetivo_mes_foco is not None and mes_foco in ta_new.index:
        ta_new.loc[mes_foco] = max(float(ta_new.loc[mes_foco]), float(objetivo_mes_foco))

    factores = (ta_new / ta.replace(0, np.nan)).replace([np.inf,-np.inf], np.nan).fillna(1.0).to_dict()
    d = _escalar_detalle_servicio(d, 'TREN_ARAUCANIA', factores)
    for mes in range(1,13):
        if mes == 3 and ajuste_marzo != 0:
            criterio = 'oferta_victoria_temuco_11_lv_suavizamiento_marzo_e_incremento_marginal'
        elif mes == mes_foco:
            criterio = 'refuerzo_mayo_coherencia_mar_abr_may_2026'
        else:
            criterio = 'incremento_marginal_preservando_perfil_2025'
        mensual_rows.append({'mes': mes, 'servicio': 'TREN_ARAUCANIA', 'proyeccion_anterior': ta.loc[mes], 'proyeccion_recalibrada': ta_new.loc[mes], 'diferencia': ta_new.loc[mes]-ta.loc[mes], 'factor_o_ajuste_aplicado': criterio})
    diag.append({'servicio':'TREN_ARAUCANIA','indicador':'servicios_lv_victoria_temuco','valor':float(cfg_ta['servicios_lv_victoria_temuco'])})
    diag.append({'servicio':'TREN_ARAUCANIA','indicador':'ratio_marzo_vs_promedio_abr_dic','valor':float(ta_new.loc[3]/ta_new.reindex(range(4,13)).mean())})
    diag.append({'servicio':'TREN_ARAUCANIA','indicador':'ratio_marzo_vs_promedio_anual','valor':float(ta_new.loc[3]/ta_new.mean())})
    diag.append({'servicio':'TREN_ARAUCANIA','indicador':'total_pre_refuerzo_mensual','valor':float(ta_suavizada.sum())})
    diag.append({'servicio':'TREN_ARAUCANIA','indicador':'total_recalibrado_refuerzo_mensual','valor':float(ta_new.sum())})
    diag.append({'servicio':'TREN_ARAUCANIA','indicador':'afluencia_mayo_objetivo_2027','valor':float(ta_new.loc[mes_foco])})
    diag.append({'servicio':'TREN_ARAUCANIA','indicador':'factor_incremento_marginal_resto_meses','valor':float(factor_marginal)})

    # Laja se deja sin ajuste específico.
    laja = d[d['servicio'].eq('CORTO_LAJA')].groupby('mes')['afl'].sum().astype(float)
    for mes in range(1,13):
        mensual_rows.append({'mes': mes, 'servicio': 'CORTO_LAJA', 'proyeccion_anterior': laja.loc[mes], 'proyeccion_recalibrada': laja.loc[mes], 'diferencia': 0.0, 'factor_o_ajuste_aplicado': 'sin_ajuste_especifico_nuevo'})

    # Comparativo anual anterior vs recalibrado dentro de esta función.
    ant = {'BIOTREN': bi.sum(), 'LLANQUIHUE_PM': ll.sum(), 'TREN_ARAUCANIA': ta.sum(), 'CORTO_LAJA': laja.sum()}
    rec = d.groupby('servicio')['afl'].sum().to_dict()
    motivos = {'BIOTREN':'validación operacional por ocupación promedio, revisión estival y oferta mensual', 'TREN_ARAUCANIA':'Victoria-Temuco 11 servicios LV, refuerzo de mayo por coherencia marzo-mayo 2026 e incremento marginal del resto de meses', 'LLANQUIHUE_PM':'promedio laboral marzo-diciembre y menor efecto novedad estival', 'CORTO_LAJA':'sin ajuste específico nuevo'}
    comp = pd.DataFrame([{'servicio':s, 'total_anterior':float(ant.get(s,0)), 'total_recalibrado':float(rec.get(s,0)), 'diferencia_absoluta':float(rec.get(s,0)-ant.get(s,0)), 'diferencia_porcentual':float((rec.get(s,0)/ant.get(s,1)-1)*100) if ant.get(s,0) else np.nan, 'motivo_principal_ajuste':motivos[s]} for s in SERVICIOS])
    return d, comp, pd.DataFrame(mensual_rows), pd.DataFrame(diag)


def cargar_calibracion_productividad(path=None):
    """Carga factores de calibración de pax/viaje construidos con información reciente.

    El archivo esperado contiene, al menos:
      unit, dt, factor_objetivo, peso_calibracion, factor_min, factor_max.
    Si el archivo no existe, retorna DataFrame vacio y no modifica parametros.
    """
    if path is None:
        path = DATA_DIR / 'calibracion_mayo_2026.csv'
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def calibrar_productividad_reciente(params, calibracion=None):
    """Ajusta pax_x_viaje con el comportamiento operativo reciente.

    La calibración es parcial: no reemplaza la serie histórica, sino que
    aproxima la productividad histórica a la productividad reciente usando un
    peso configurable y límites de variación. Esto permite representar que un
    aumento de servicios puede reducir pasajeros promedio por viaje.
    """
    p = params.copy()
    if calibracion is None:
        cal = cargar_calibracion_productividad()
    elif isinstance(calibracion, pd.DataFrame):
        cal = calibracion.copy()
    else:
        cal = pd.read_csv(calibracion)

    if cal.empty:
        return p

    required = {'unit', 'dt', 'factor_objetivo'}
    if not required.issubset(set(cal.columns)):
        return p

    for _, r in cal.iterrows():
        unit = r['unit']
        dt = r['dt']
        peso = float(r.get('peso_calibracion', 1.0))
        f_obj = float(r['factor_objetivo'])
        f_min = float(r.get('factor_min', 0.65))
        f_max = float(r.get('factor_max', 1.45))
        f_aplicado = np.clip(1 + peso * (f_obj - 1), f_min, f_max)
        m = (p['unit'] == unit) & (p['dt'] == dt)
        p.loc[m, 'pax_x_viaje'] = p.loc[m, 'pax_x_viaje'] * f_aplicado
    p['pax_x_viaje'] = p['pax_x_viaje'].round(1)
    return p


def oferta_tren_araucania_tramos_df(mensual=True):
    """Oferta vigente de Tren Araucania desagregada por tramo.

    Claret se modela como servicio escolar activo sólo entre marzo y diciembre.
    En enero y febrero su oferta se fuerza a cero, incluso si se trabaja en
    edición mensual de oferta.
    """
    base = {
        # Escenario 2027 recalibrado: Victoria-Temuco opera 11 servicios LV todo el año.
        # Pitrufquen mantiene promedio LV: lunes-jueves 7 y viernes 5 => 6,6. Claret 3 LV escolar.
        'TA_TEMUCO_VICTORIA': {'LV': 11.0, 'Sab': 8.0, 'Dom': 6.0},
        'TA_TEMUCO_PITRUFQUEN': {'LV': 6.6, 'Sab': 4.0, 'Dom': 0.0},
        'TA_CLARET': {'LV': 3.0, 'Sab': 0.0, 'Dom': 0.0},
    }
    rows = []
    for unit, vals in base.items():
        meses = range(1, 13) if mensual else [None]
        for mes in meses:
            for dt, servicios_dia in vals.items():
                sdia = float(servicios_dia)
                if mensual and unit == 'TA_CLARET' and int(mes) in (1, 2):
                    sdia = 0.0
                row = {'unit': unit, 'dt': dt, 'servicios_dia': sdia}
                if mensual:
                    row['mes'] = mes
                rows.append(row)
    cols = ['unit', 'mes', 'dt', 'servicios_dia'] if mensual else ['unit', 'dt', 'servicios_dia']
    return pd.DataFrame(rows)[cols]


def _normalizar_plan_tramos_ta(plan_tramos=None):
    """Completa y valida un plan de oferta por tramo de Tren Araucania."""
    base = oferta_tren_araucania_tramos_df(mensual=True)
    if plan_tramos is None:
        df = base.copy()
    else:
        pl = plan_tramos.copy()
        pl = pl[pl['unit'].isin(TA_TRAMOS)].copy()
        if pl.empty:
            df = base.copy()
        else:
            pl['mes'] = pl['mes'].astype(int)
            df = base[['unit', 'mes', 'dt']].merge(
                pl[['unit', 'mes', 'dt', 'servicios_dia']], on=['unit', 'mes', 'dt'], how='left'
            )
            df = df.merge(base.rename(columns={'servicios_dia': 'servicios_base'}),
                          on=['unit', 'mes', 'dt'], how='left')
            df['servicios_dia'] = pd.to_numeric(df['servicios_dia'], errors='coerce').fillna(df['servicios_base'])
            df = df[['unit', 'mes', 'dt', 'servicios_dia']]
    df.loc[(df['unit'] == 'TA_CLARET') & (df['mes'].isin([1, 2])), 'servicios_dia'] = 0.0
    df['servicios_dia'] = pd.to_numeric(df['servicios_dia'], errors='coerce').fillna(0.0).clip(lower=0.0)
    return df


def cargar_distribucion_tren_araucania(path=None):
    """Carga la distribución mensual observada por tipo de servicio de Tren Araucania.

    Archivo esperado: data/tren_araucania_distribucion_tramos.csv, derivado de
    TA-Dist.xlsx. Contiene afluencia mensual por Victoria-Temuco,
    Pitrufquen-Temuco y Claret en el periodo histórico disponible.
    """
    if path is None:
        path = DATA_DIR / 'tren_araucania_distribucion_tramos.csv'
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=['fecha'])
    if 'anio' not in df.columns:
        df['anio'] = df['fecha'].dt.year
    if 'mes' not in df.columns:
        df['mes'] = df['fecha'].dt.month
    return df


def perfil_distribucion_tren_araucania_por_tramo():
    """Perfil mensual de participación de demanda por tramo de Tren Araucania.

    Se calcula con TA-Dist.xlsx, ponderando años recientes y normalizando por mes.
    Claret se fija en cero para enero y febrero por su carácter de servicio escolar.
    """
    df = cargar_distribucion_tren_araucania()
    rows = []
    if df.empty:
        fallback = {
            'TA_TEMUCO_VICTORIA': 0.58,
            'TA_TEMUCO_PITRUFQUEN': 0.17,
            'TA_CLARET': 0.25,
        }
        for mes in range(1, 13):
            vals = fallback.copy()
            if mes in (1, 2):
                vals['TA_CLARET'] = 0.0
            sm = sum(vals.values()) or 1.0
            for u, v in vals.items():
                rows.append({'mes': mes, 'unit': u, 'participacion_demanda_historica': v / sm,
                             'fuente': 'fallback_sin_TA_Dist'})
        return pd.DataFrame(rows)

    share_cols = {
        'TA_TEMUCO_VICTORIA': 'share_TA_TEMUCO_VICTORIA',
        'TA_TEMUCO_PITRUFQUEN': 'share_TA_TEMUCO_PITRUFQUEN',
        'TA_CLARET': 'share_TA_CLARET',
    }
    for mes in range(1, 13):
        dm = df[df['mes'] == mes].copy()
        vals = {}
        years = []
        for u, c in share_cols.items():
            num = 0.0
            den = 0.0
            for _, r in dm.iterrows():
                y = int(r['anio'])
                w = float(TA_DISTRIBUCION_ANIO_PESOS.get(y, 1.0))
                if pd.notna(r.get(c, np.nan)):
                    num += float(r[c]) * w
                    den += w
                    years.append(y)
            vals[u] = num / den if den else np.nan
        if all(pd.isna(v) for v in vals.values()):
            # Fallback con promedio global observado por tramo.
            totals = {u: float(df[u].sum()) for u in TA_TRAMOS if u in df.columns}
            smt = sum(totals.values()) or 1.0
            vals = {u: totals.get(u, 0.0) / smt for u in TA_TRAMOS}
        if mes in (1, 2):
            vals['TA_CLARET'] = 0.0
        vals = {u: (0.0 if pd.isna(v) else float(v)) for u, v in vals.items()}
        sm = sum(vals.values()) or 1.0
        for u, v in vals.items():
            rows.append({'mes': mes, 'unit': u, 'participacion_demanda_historica': v / sm,
                         'fuente': 'TA-Dist.xlsx ponderado con serie historica disponible',
                         'anios_utilizados': ','.join(map(str, sorted(set(years))))})
    return pd.DataFrame(rows)


def proyectar_tren_araucania_por_tramo(detalle_agregado, plan_tramos=None, anio=2027):
    """Proyecta Tren Araucania por tipo de servicio/tramo.

    La base mensual agregada se distribuye con el perfil observado en TA-Dist y
    luego cada tramo responde a su propia variación de oferta. Por lo tanto, un
    aumento de servicios en Victoria-Temuco, Pitrufquen-Temuco o Claret modifica
    el resultado anual con impactos distintos.
    """
    ag = detalle_agregado.copy()
    if ag.empty:
        return pd.DataFrame()
    base_mes = ag.groupby('mes', as_index=False)['demanda_base_mensual'].sum()
    base_mes = base_mes.rename(columns={'demanda_base_mensual': 'demanda_base_ta_mes'})

    # Parámetros de calendario y supresión del servicio agregado por mes/tipo de día.
    pars = ag[['mes', 'dt', 'n_dias', 'tasa_sup', 'f_sup_base', 'f_sup_plan',
               'factor_estacionalidad', 'fuerza_estacionalidad']].drop_duplicates(['mes', 'dt']).copy()
    base_tr = oferta_tren_araucania_tramos_df(mensual=True).rename(columns={'servicios_dia': 'servicios_dia_base_tramo'})
    plan_tr = _normalizar_plan_tramos_ta(plan_tramos).rename(columns={'servicios_dia': 'servicios_dia_plan_tramo'})
    tr = base_tr.merge(plan_tr, on=['unit', 'mes', 'dt'], how='left')
    tr = tr.merge(pars, on=['mes', 'dt'], how='left')
    tr['servicios_dia_plan_tramo'] = tr['servicios_dia_plan_tramo'].fillna(tr['servicios_dia_base_tramo'])
    tr['n_dias'] = tr['n_dias'].fillna(0)
    tr['f_sup_base'] = tr['f_sup_base'].fillna((1 - tr['tasa_sup']).clip(0, 1))
    tr['f_sup_plan'] = tr['f_sup_plan'].fillna(tr['f_sup_base'])
    tr['viajes_programados_base'] = tr['servicios_dia_base_tramo'] * tr['n_dias']
    tr['viajes_programados_plan'] = tr['servicios_dia_plan_tramo'] * tr['n_dias']
    tr['viajes_operados_base'] = tr['viajes_programados_base'] * tr['f_sup_base']
    tr['viajes_operados_plan'] = tr['viajes_programados_plan'] * tr['f_sup_plan']

    m = tr.groupby(['unit', 'mes'], as_index=False).agg(
        n_dias_mes=('n_dias', 'sum'),
        viajes_programados_base=('viajes_programados_base', 'sum'),
        viajes_programados_plan=('viajes_programados_plan', 'sum'),
        viajes_operados_base=('viajes_operados_base', 'sum'),
        viajes_operados_plan=('viajes_operados_plan', 'sum'),
        factor_estacionalidad=('factor_estacionalidad', 'mean'),
        fuerza_estacionalidad=('fuerza_estacionalidad', 'mean'),
    )
    m['servicios_dia'] = m['viajes_programados_base'] / m['n_dias_mes'].replace(0, np.nan)
    m['servicios_dia_plan'] = m['viajes_programados_plan'] / m['n_dias_mes'].replace(0, np.nan)
    dist = perfil_distribucion_tren_araucania_por_tramo()
    m = m.merge(dist[['mes', 'unit', 'participacion_demanda_historica']], on=['mes', 'unit'], how='left')
    m = m.merge(base_mes, on='mes', how='left')
    m['participacion_demanda_historica'] = m['participacion_demanda_historica'].fillna(0.0)
    m['demanda_base_mensual'] = m['demanda_base_ta_mes'] * m['participacion_demanda_historica']
    m['elasticidad'] = m['unit'].map(TA_TRAMO_ELASTICIDAD).fillna(ELASTICIDAD_OFERTA_SERVICIO['TREN_ARAUCANIA'])
    m['ratio_oferta_operada'] = m['viajes_operados_plan'] / m['viajes_operados_base'].replace(0, np.nan)
    m['afl'] = m['demanda_base_mensual'] * m['ratio_oferta_operada'].pow(m['elasticidad'])

    # Si un tramo no tiene base y se intentara crear oferta nueva, se usa rampa reducida.
    new = m['viajes_operados_base'].le(0) & m['viajes_operados_plan'].gt(0)
    if new.any():
        m.loc[new, 'afl'] = 0.0
    m['afl'] = m['afl'].fillna(0.0).clip(lower=0.0)
    m['servicio'] = 'TREN_ARAUCANIA'
    m['dt'] = 'Mes'
    m['tasa_sup_original'] = np.nan
    m['tasa_sup'] = np.nan
    m['nivel_factor'] = AJUSTE_NIVEL_SERVICIO['TREN_ARAUCANIA']
    m['factor_recuperacion_laja'] = 1.0
    m['f_sup_base'] = m['viajes_operados_base'] / m['viajes_programados_base'].replace(0, np.nan)
    m['f_sup_plan'] = m['viajes_operados_plan'] / m['viajes_programados_plan'].replace(0, np.nan)
    m['pax_x_viaje'] = m['demanda_base_mensual'] / m['viajes_operados_base'].replace(0, np.nan)
    m['pax_por_viaje_resultante'] = m['afl'] / m['viajes_operados_plan'].replace(0, np.nan)
    m['pax_por_viaje_base'] = m['demanda_base_mensual'] / m['viajes_operados_base'].replace(0, np.nan)
    m['variacion_servicios_dia'] = m['servicios_dia_plan'] - m['servicios_dia']
    m['variacion_pct_oferta_operada'] = (m['viajes_operados_plan'] / m['viajes_operados_base'].replace(0, np.nan) - 1) * 100
    m['variacion_pct_demanda'] = (m['afl'] / m['demanda_base_mensual'].replace(0, np.nan) - 1) * 100
    m['periodo'] = m['mes'].map(lambda x: f'{anio}-{int(x):02d}')
    return m


def plan_tren_araucania_agregado(plan_tramos):
    """Convierte oferta por tramo de Tren Araucania en oferta equivalente agregada.

    La oferta equivalente conserva el nivel actual cuando se usan los valores base.
    Si el usuario aumenta servicios en Victoria-Temuco, el efecto en demanda es
    mayor que si aumenta servicios en Pitrufquen o Claret.
    """
    base = oferta_tren_araucania_tramos_df(mensual=True)
    df = plan_tramos.copy()
    df['mes'] = df['mes'].astype(int)
    idx = base[['unit', 'mes', 'dt']].copy()
    df = idx.merge(df[['unit', 'mes', 'dt', 'servicios_dia']], on=['unit', 'mes', 'dt'], how='left')
    df = df.merge(base.rename(columns={'servicios_dia': 'servicios_base'}), on=['unit', 'mes', 'dt'], how='left')
    df['servicios_dia'] = pd.to_numeric(df['servicios_dia'], errors='coerce').fillna(df['servicios_base'])
    df['peso'] = df['unit'].map(TA_TRAMO_PESO_DEMANDA).fillna(0.0)
    df['ponderado'] = df['servicios_dia'] * df['peso']

    base2 = base.copy()
    base2['peso'] = base2['unit'].map(TA_TRAMO_PESO_DEMANDA).fillna(0.0)
    base2['ponderado_base'] = base2['servicios_dia'] * base2['peso']
    cur = df.groupby(['mes', 'dt'])['ponderado'].sum().reset_index()
    bas = base2.groupby(['mes', 'dt']).agg(ponderado_base=('ponderado_base', 'sum'),
                                           total_base=('servicios_dia', 'sum')).reset_index()
    out = cur.merge(bas, on=['mes', 'dt'], how='left')
    out['servicios_dia'] = out['total_base'] * out['ponderado'] / out['ponderado_base'].replace(0, np.nan)
    out['servicios_dia'] = out['servicios_dia'].fillna(0.0)
    out['unit'] = 'TREN_ARAUCANIA'
    return out[['unit', 'mes', 'dt', 'servicios_dia']]


def _preparar_mdf(mdf):
    g = mdf.copy()
    if not pd.api.types.is_period_dtype(g['mes']):
        g['mes'] = pd.PeriodIndex(g['mes'], freq='M')
    g['anio'] = g['mes'].dt.year
    g['m'] = g['mes'].dt.month
    return g


def analisis_mensual_historico(mdf):
    """Tabla auditable de comportamiento mensual por servicio y anio."""
    g = _preparar_mdf(mdf)
    rows = []
    for (servicio, anio), d in g.groupby(['servicio', 'anio']):
        total_obs = d['pax_norm'].sum()
        meses_obs = d['m'].nunique()
        media_obs = d['pax_norm'].mean()
        for _, r in d.iterrows():
            rows.append({
                'servicio': servicio,
                'anio': int(anio),
                'mes': int(r['m']),
                'afluencia_mensual_normalizada': round(float(r['pax_norm']), 0),
                'meses_observados_anio': int(meses_obs),
                'participacion_sobre_periodo_observado': float(r['pax_norm'] / total_obs) if total_obs else np.nan,
                'indice_mensual_vs_media_observada': float(r['pax_norm'] / media_obs) if media_obs else np.nan,
                'cobertura': float(r.get('cobertura', np.nan)),
            })
    return pd.DataFrame(rows).sort_values(['servicio', 'anio', 'mes']).reset_index(drop=True)


def resumen_historico_anual(mdf):
    g = _preparar_mdf(mdf)
    out = (g.groupby(['servicio', 'anio'])
             .agg(meses_observados=('m', 'nunique'),
                  afluencia_observada_normalizada=('pax_norm', 'sum'),
                  promedio_mensual=('pax_norm', 'mean'),
                  primer_mes=('m', 'min'), ultimo_mes=('m', 'max'))
             .reset_index())
    out['afluencia_observada_normalizada'] = out['afluencia_observada_normalizada'].round(0)
    out['promedio_mensual'] = out['promedio_mensual'].round(0)
    return out


def _share_full_years(g, servicio):
    weights_by_service = {
        'BIOTREN': {2024: 0.40, 2025: 0.45, 2026: 0.15},
        'CORTO_LAJA': {2024: 0.55, 2025: 0.30, 2026: 0.15},
        'TREN_ARAUCANIA': {2025: 0.70, 2026: 0.30},
        'LLANQUIHUE_PM': {2025: 0.30, 2026: 0.70},
    }
    weights = weights_by_service.get(servicio, {})
    out = pd.Series(0.0, index=range(1, 13), dtype=float)
    tw = 0.0

    # Años completos: uso directo de participación anual.
    for y, d in g.groupby('anio'):
        y = int(y)
        if d['m'].nunique() >= 12:
            sh = d.set_index('m')['pax_norm'].astype(float).reindex(range(1, 13))
            sh = sh / sh.sum()
            w = float(weights.get(y, 1.0))
            out = out.add(sh * w, fill_value=0.0)
            tw += w

    if tw > 0:
        out = out / tw
    else:
        piv = g.sort_values('mes').groupby('m')['pax_norm'].last()
        mean_val = float(piv.mean()) if len(piv) else 1.0
        out = pd.Series({m: float(piv.get(m, mean_val)) for m in range(1, 13)}, dtype=float)
        out = out / out.sum()

    # Año parcial 2026: se incorpora sólo en meses observados, sin inferir el año completo.
    obs26 = g[g['anio'] == 2026].set_index('m')['pax_norm'].astype(float)
    if not obs26.empty:
        denom = max(out.loc[obs26.index].sum(), 1e-9)
        anual_implicito = obs26.sum() / denom
        sh26 = obs26 / anual_implicito
        peso_2026 = {'BIOTREN': 0.45, 'CORTO_LAJA': 0.20, 'TREN_ARAUCANIA': 0.45, 'LLANQUIHUE_PM': 0.70}.get(servicio, 0.35)
        for m, v in sh26.items():
            out.loc[m] = (1 - peso_2026) * out.loc[m] + peso_2026 * v

    out = out.reindex(range(1, 13)).fillna(out.mean())
    return out / out.sum()


def perfil_mensual_historico(mdf, servicio, total_anual=None):
    """Perfil mensual histórico utilizado como corrección de productividad.

    Este perfil NO se usa para repartir un total anual fijo. Se usa para construir
    factores de productividad mensual que luego se aplican al cálculo mes a mes.
    """
    g_all = _preparar_mdf(mdf)
    g = g_all[g_all['servicio'] == servicio].copy()
    if g.empty:
        return pd.Series(1 / 12, index=[f'2027-{m:02d}' for m in range(1, 13)])

    if servicio == 'LLANQUIHUE_PM':
        # Mantener enero-febrero 2026 como señal estival cuando existen datos.
        vals = {}
        for m in range(1, 13):
            d = g[g['m'] == m].sort_values('anio')
            vals[m] = float(d.iloc[-1]['pax_norm']) if not d.empty else np.nan
        available = [v for v in vals.values() if pd.notna(v)]
        fill = float(np.mean(available)) if available else 1.0
        raw = pd.Series({m: (fill if pd.isna(v) else v) for m, v in vals.items()}, dtype=float).reindex(range(1, 13))
        share = raw / raw.sum()
    else:
        share = _share_full_years(g, servicio)

    share.index = [f'2027-{m:02d}' for m in range(1, 13)]
    return share.astype(float)


def _base_detalle(params, anio=2027, calibracion_productividad=True):
    p = params.copy()
    p['mes'] = p['mes'].astype(int)
    if calibracion_productividad:
        p = calibrar_productividad_reciente(p)
    p = p.merge(dias_operacionales_por_tipo(anio), on=['unit', 'mes', 'dt'], how='left')
    p['n_dias'] = pd.to_numeric(p['n_dias'], errors='coerce').fillna(0).astype(float)
    p['servicio'] = p['unit'].map(unidad_a_servicio())
    p['nivel_factor'] = p['servicio'].map(AJUSTE_NIVEL_SERVICIO).fillna(1.0)
    p['elasticidad'] = p['servicio'].map(ELASTICIDAD_OFERTA_SERVICIO).fillna(0.45)
    p['tasa_sup_original'] = p['tasa_sup']
    m_laja = p['unit'].eq('CORTO_LAJA')
    p.loc[m_laja, 'tasa_sup'] = p.loc[m_laja, 'tasa_sup'].clip(upper=float(RECUPERACION_LAJA['tasa_sup_max']))
    p['factor_recuperacion_laja'] = np.where(m_laja, p['nivel_factor'], 1.0)
    p['f_sup_base'] = (1 - p['tasa_sup']).clip(0, 1)
    p['viajes_programados_base'] = p['servicios_dia'] * p['n_dias']
    p['viajes_operados_base'] = p['viajes_programados_base'] * p['f_sup_base']
    p['afl_base_sin_estacionalidad'] = p['viajes_operados_base'] * p['pax_x_viaje'] * p['nivel_factor']
    return p


def _ajustar_estacionalidad_biotren_marzo_abril(factores, base_serv):
    """Suaviza marzo-abril de Biotren sin cambiar el total anual.

    El ajuste se aplica sobre los factores de estacionalidad y conserva la suma
    proyectada del par marzo-abril. De esta forma, el total anual se mantiene,
    pero la curva queda más coherente con 2026, donde marzo fue levemente mayor
    que abril.
    """
    cfg = AJUSTE_BIOTREN_MARZO_ABRIL
    if not cfg.get('activo', False):
        return factores

    meses = tuple(cfg.get('meses', (3, 4)))
    if len(meses) != 2:
        return factores
    m3, m4 = int(meses[0]), int(meses[1])
    peso_marzo = float(cfg.get('participacion_marzo', 0.50))
    peso_marzo = min(max(peso_marzo, 0.0), 1.0)

    f = factores.copy()
    raw = (base_serv[base_serv['servicio'].eq('BIOTREN')]
           .set_index('mes')['afl_base_sin_estacionalidad']
           .astype(float))
    if m3 not in raw.index or m4 not in raw.index:
        return f

    mask = f['servicio'].eq('BIOTREN') & f['mes'].isin([m3, m4])
    if mask.sum() != 2:
        return f

    fac = f.loc[mask].set_index('mes')['factor_estacionalidad'].astype(float)
    actual_m3 = float(raw.loc[m3] * fac.loc[m3])
    actual_m4 = float(raw.loc[m4] * fac.loc[m4])
    total_par = actual_m3 + actual_m4
    if total_par <= 0 or raw.loc[m3] <= 0 or raw.loc[m4] <= 0:
        return f

    objetivo = {m3: total_par * peso_marzo, m4: total_par * (1.0 - peso_marzo)}
    for mes in [m3, m4]:
        f.loc[f['servicio'].eq('BIOTREN') & f['mes'].eq(mes), 'factor_estacionalidad'] = objetivo[mes] / float(raw.loc[mes])
        f.loc[f['servicio'].eq('BIOTREN') & f['mes'].eq(mes), 'ajuste_biotren_marzo_abril'] = True
    f['ajuste_biotren_marzo_abril'] = f.get('ajuste_biotren_marzo_abril', False).fillna(False)
    return f


def factores_estacionalidad_mensual(params, mdf, anio=2027, calibracion_productividad=True):
    """Calcula factores mensuales de productividad por servicio.

    El factor se obtiene comparando la proyección directa por oferta actual con
    el patrón histórico mensual. Luego se aplica con una fuerza menor o igual a 1
    y se normaliza para que el escenario base conserve el nivel anual calibrado.
    Para Biotren se agrega un ajuste puntual marzo-abril, manteniendo el total
    anual y el total conjunto de ambos meses, para evitar que abril quede
    artificialmente sobrerrepresentado frente a marzo.
    """
    p0 = _base_detalle(params, anio=anio, calibracion_productividad=calibracion_productividad)
    base_serv = (p0.groupby(['servicio', 'mes'])['afl_base_sin_estacionalidad'].sum()
                   .reset_index())
    rows = []
    for s, d in base_serv.groupby('servicio'):
        total_base = float(d['afl_base_sin_estacionalidad'].sum())
        hist_share = perfil_mensual_historico(mdf, s)
        raw = d.set_index('mes')['afl_base_sin_estacionalidad'].astype(float).reindex(range(1, 13)).fillna(0.0)
        target = pd.Series({m: total_base * float(hist_share.get(f'{anio}-{m:02d}', 1/12)) for m in range(1, 13)}, dtype=float)
        ratio = (target / raw.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        fuerza = float(FUERZA_ESTACIONALIDAD.get(s, 0.5))
        f = ratio.pow(fuerza)
        annual_after = float((raw * f).sum())
        normalizador = total_base / annual_after if annual_after > 0 else 1.0
        for m in range(1, 13):
            rows.append({
                'servicio': s,
                'mes': int(m),
                'factor_estacionalidad': float(f.loc[m] * normalizador),
                'participacion_historica_utilizada': float(hist_share.get(f'{anio}-{m:02d}', 1/12)),
                'fuerza_estacionalidad': fuerza,
                'ajuste_biotren_marzo_abril': False,
            })
    out = pd.DataFrame(rows)
    out = _ajustar_estacionalidad_biotren_marzo_abril(out, base_serv)
    return out


def _aplicar_plan(detalle_base, plan=None, contingencia_extra=None):
    p = detalle_base.copy()
    if plan is not None:
        pl = plan[['unit', 'mes', 'dt', 'servicios_dia']].rename(columns={'servicios_dia': 'servicios_dia_plan'})
        pl['mes'] = pl['mes'].astype(int)
        p = p.merge(pl, on=['unit', 'mes', 'dt'], how='left')
        p['servicios_dia_plan'] = pd.to_numeric(p['servicios_dia_plan'], errors='coerce').fillna(p['servicios_dia'])
    else:
        p['servicios_dia_plan'] = p['servicios_dia']

    ce = contingencia_extra or {}
    p['f_sup_plan'] = (1 - p['tasa_sup'] - p['unit'].map(ce).fillna(0)).clip(0, 1)
    p['viajes_programados_plan'] = p['servicios_dia_plan'] * p['n_dias']
    p['viajes_operados_plan'] = p['viajes_programados_plan'] * p['f_sup_plan']
    return p


def proyectar_mensual_elastico(params, mdf, plan=None, contingencia_extra=None,
                               anio=2027, calibracion_productividad=True,
                               return_detalle=False):
    """Proyección mensual oferta-demanda con elasticidad parcial.

    Fórmula principal por unidad u, mes m y tipo de día d:
      D1 = D0 * (V1 / V0) ** e

    donde:
      D0 = demanda base mensual calibrada,
      V0 = viajes operados base,
      V1 = viajes operados con la oferta editada,
      e  = elasticidad de demanda respecto de oferta, con 0 < e < 1.

    Si el usuario modifica la oferta de un mes, sólo cambian las filas de ese mes.
    El total anual ya no se reparte posteriormente: resulta de sumar los meses.
    """
    base = _base_detalle(params, anio=anio, calibracion_productividad=calibracion_productividad)
    fest = factores_estacionalidad_mensual(params, mdf, anio=anio,
                                           calibracion_productividad=calibracion_productividad)
    p = _aplicar_plan(base, plan=plan, contingencia_extra=contingencia_extra)
    p = p.merge(fest[['servicio', 'mes', 'factor_estacionalidad', 'participacion_historica_utilizada', 'fuerza_estacionalidad']],
                on=['servicio', 'mes'], how='left')
    p['factor_estacionalidad'] = p['factor_estacionalidad'].fillna(1.0)
    p['demanda_base_mensual'] = p['afl_base_sin_estacionalidad'] * p['factor_estacionalidad']

    ratio = p['viajes_operados_plan'] / p['viajes_operados_base'].replace(0, np.nan)
    p['ratio_oferta_operada'] = ratio.replace([np.inf, -np.inf], np.nan)
    p['afl'] = p['demanda_base_mensual'] * p['ratio_oferta_operada'].pow(p['elasticidad'])

    # Fallback para oferta nueva donde no existe V0: productividad base reducida por etapa de maduración.
    m_new = p['viajes_operados_base'].le(0) & p['viajes_operados_plan'].gt(0)
    if m_new.any():
        ramp = p.loc[m_new, 'servicio'].map(RAMP_NUEVA_OFERTA).fillna(0.45)
        p.loc[m_new, 'afl'] = (p.loc[m_new, 'viajes_operados_plan'] *
                               p.loc[m_new, 'pax_x_viaje'] *
                               p.loc[m_new, 'nivel_factor'] *
                               p.loc[m_new, 'factor_estacionalidad'] * ramp)
    p['afl'] = p['afl'].fillna(0.0).clip(lower=0)
    p['pax_por_viaje_resultante'] = p['afl'] / p['viajes_operados_plan'].replace(0, np.nan)
    p['pax_por_viaje_base'] = p['demanda_base_mensual'] / p['viajes_operados_base'].replace(0, np.nan)
    p['variacion_servicios_dia'] = p['servicios_dia_plan'] - p['servicios_dia']
    p['variacion_pct_oferta_operada'] = (p['viajes_operados_plan'] / p['viajes_operados_base'].replace(0, np.nan) - 1) * 100
    p['variacion_pct_demanda'] = (p['afl'] / p['demanda_base_mensual'].replace(0, np.nan) - 1) * 100
    p['periodo'] = p['mes'].map(lambda m: f'{anio}-{int(m):02d}')

    # Tren Araucanía se reemplaza por cálculo desagregado por tipo de servicio.
    plan_tramos_ta = None
    if plan is not None and 'unit' in plan.columns and plan['unit'].isin(TA_TRAMOS).any():
        plan_tramos_ta = plan[plan['unit'].isin(TA_TRAMOS)].copy()
    ta_ag = p[p['servicio'] == 'TREN_ARAUCANIA'].copy()
    if not ta_ag.empty:
        ta_det = proyectar_tren_araucania_por_tramo(ta_ag, plan_tramos=plan_tramos_ta, anio=anio)
        # Alinear columnas antes de concatenar.
        all_cols = sorted(set(p.columns).union(set(ta_det.columns)))
        p = pd.concat([p[p['servicio'] != 'TREN_ARAUCANIA'].reindex(columns=all_cols),
                       ta_det.reindex(columns=all_cols)], ignore_index=True)

    p, comparativo_recalibracion, mensual_recalibracion, diagnostico_recalibracion = recalibrar_escenario_2027(p, anio=anio)

    uni = p.groupby(['unit', 'mes'])['afl'].sum().reset_index()
    uni_w = uni.pivot(index='mes', columns='unit', values='afl').fillna(0.0)
    uni_w.index = [f'{anio}-{m:02d}' for m in uni_w.index]
    serv_long = p.groupby(['servicio', 'mes'])['afl'].sum().reset_index()
    serv = serv_long.pivot(index='mes', columns='servicio', values='afl').fillna(0.0)
    serv.index = [f'{anio}-{m:02d}' for m in serv.index]
    for s in SERVICIOS:
        if s not in serv.columns:
            serv[s] = 0.0
    serv = serv[SERVICIOS]
    diag_bt = diagnostico_recalibracion[diagnostico_recalibracion['servicio'].eq('BIOTREN')]
    diag_bt = dict(zip(diag_bt['indicador'].astype(str), pd.to_numeric(diag_bt['valor'], errors='coerce')))

    uni_w = uni_w.round(0).astype('Int64')
    serv = serv.round(0).astype('Int64')
    serv.attrs['recalibracion_2027'] = {
        'diagnostico_biotren': {k: float(v) for k, v in diag_bt.items()},
        'comparativo': comparativo_recalibracion.to_dict('records'),
        'mensual': mensual_recalibracion.to_dict('records'),
        'diagnostico': diagnostico_recalibracion.to_dict('records'),
    }
    detalle = p.copy()
    if return_detalle:
        return uni_w, serv, detalle
    return uni_w, serv


def proyectar(params, plan=None, contingencia_extra=None, anio=2027, calibracion_productividad=True):
    """Compatibilidad: proyección directa mensual por oferta y productividad constante."""
    p = _base_detalle(params, anio=anio, calibracion_productividad=calibracion_productividad)
    p = _aplicar_plan(p, plan=plan, contingencia_extra=contingencia_extra)
    p['afl'] = p['viajes_operados_plan'] * p['pax_x_viaje'] * p['nivel_factor']
    uni = p.groupby(['unit', 'mes'])['afl'].sum().reset_index()
    uni_w = uni.pivot(index='mes', columns='unit', values='afl').fillna(0.0)
    uni_w.index = [f'{anio}-{m:02d}' for m in uni_w.index]
    serv = pd.DataFrame(index=uni_w.index)
    for s, us in UNIDADES_DE.items():
        cols = [u for u in us if u in uni_w.columns]
        if cols:
            serv[s] = uni_w[cols].sum(axis=1)
    return uni_w.round(0).astype('Int64'), serv.round(0).astype('Int64')


def proyectar_base_ajustada(params, mdf, plan=None, contingencia_extra=None,
                            anio=2027, calibracion_productividad=True,
                            factores_total=None):
    """Compatibilidad: ahora usa el motor mensual elástico, no distribución anual."""
    uni, serv, detalle = proyectar_mensual_elastico(params, mdf, plan=plan,
                                                    contingencia_extra=contingencia_extra,
                                                    anio=anio,
                                                    calibracion_productividad=calibracion_productividad,
                                                    return_detalle=True)
    perfiles = detalle.groupby(['servicio', 'periodo']).agg(
        afluencia_proyectada_mes=('afl', 'sum'),
        viajes_operados_plan=('viajes_operados_plan', 'sum'),
        viajes_operados_base=('viajes_operados_base', 'sum'),
        ratio_oferta_operada=('ratio_oferta_operada', 'mean'),
        elasticidad=('elasticidad', 'mean')
    ).reset_index().rename(columns={'periodo': 'mes'})
    return uni, serv, perfiles


def desagregar_tren_araucania_por_tramo(serie_total, plan_tramos=None, anio=2027):
    """Distribuye la proyección agregada de Tren Araucania según TA-Dist.

    Esta función queda para compatibilidad. La proyección principal ya calcula
    directamente por tramo; cuando sólo se entrega una serie total, se usa el
    perfil mensual observado por tramo, respetando Claret = 0 en enero-febrero.
    """
    dist = perfil_distribucion_tren_araucania_por_tramo()
    out = dist.pivot(index='mes', columns='unit', values='participacion_demanda_historica').fillna(0.0)
    out.index = [f'{anio}-{m:02d}' for m in out.index]
    total_series = pd.Series(serie_total, index=out.index).astype(float)
    for c in out.columns:
        out[c] = out[c] * total_series
    return out.round(0).astype('Int64')


def viajes_anuales(params, plan=None, contingencia_extra=None, anio=2027, units=None,
                   mdf=None, usar_motor_elastico=False):
    """Viajes operados anuales estimados, util para calcular pax/viaje proyectado."""
    p = _base_detalle(params, anio=anio, calibracion_productividad=True)
    p = _aplicar_plan(p, plan=plan, contingencia_extra=contingencia_extra)
    if units is not None:
        p = p[p['unit'].isin(units)]
    return float(p['viajes_operados_plan'].sum())


def sensibilidad_oferta_mensual(params, mdf, servicio, unit, mes, dt, delta_servicios=1.0, anio=2027):
    """Calcula efecto marginal de cambiar la oferta de un mes/tipo de día."""
    base_plan = oferta_actual_df(mensual=True)
    plan = base_plan.copy()
    m = (plan['unit'] == unit) & (plan['mes'] == mes) & (plan['dt'] == dt)
    if not m.any():
        return pd.DataFrame()
    uni0, serv0 = proyectar_mensual_elastico(params, mdf, plan=base_plan, anio=anio)
    plan.loc[m, 'servicios_dia'] = plan.loc[m, 'servicios_dia'] + float(delta_servicios)
    uni1, serv1 = proyectar_mensual_elastico(params, mdf, plan=plan, anio=anio)
    periodo = f'{anio}-{mes:02d}'
    return pd.DataFrame([{
        'servicio': servicio,
        'unit': unit,
        'mes': mes,
        'dt': dt,
        'delta_servicios_dia': delta_servicios,
        'afluencia_base_mes': int(serv0.loc[periodo, servicio]),
        'afluencia_con_cambio_mes': int(serv1.loc[periodo, servicio]),
        'impacto_mes': int(serv1.loc[periodo, servicio] - serv0.loc[periodo, servicio]),
        'impacto_anual': int(serv1[servicio].sum() - serv0[servicio].sum()),
    }])
