"""Sección 2 — Supuestos de cálculo y consideraciones metodológicas."""
import pandas as pd
import streamlit as st

from modelo_cruces import (
    VST_URBANO_VIAJE_2026, VST_URBANO_ESPERA_2026, OCUPACION_VEH_DEFAULT,
    DIAS_LABORALES_AÑO, TASA_SOCIAL_DESCUENTO_2026, HORIZONTE_SNI_DEFAULT,
    TASA_CRECIMIENTO_DEMANDA_DEFAULT,
)
from modelo_cruces.externalidades import (
    CONSUMO_RALENTI_L_H, PRECIO_SOCIAL_COMBUSTIBLE_CLP_L,
)
from modelo_cruces.cartera import UF_CLP

st.set_page_config(page_title='Supuestos y consideraciones', page_icon='⚙️', layout='wide')
st.title('2 · Supuestos de cálculo y consideraciones')
st.caption('Parámetros y decisiones metodológicas que gobiernan toda la '
           'evaluación, reunidos en un solo lugar para su trazabilidad.')

st.subheader('Parámetros de evaluación social')
st.dataframe(pd.DataFrame([
    {'Parámetro': 'Valor social del tiempo (viaje, urbano)',
     'Valor': f'{VST_URBANO_VIAJE_2026:,} CLP/h-pax',
     'Fuente': 'Informe de Precios Sociales 2026 (MDSF)'},
    {'Parámetro': 'Valor social del tiempo de espera (detenido)',
     'Valor': f'{VST_URBANO_ESPERA_2026:,} CLP/h-pax',
     'Fuente': 'Precios Sociales 2026 — ponderador de espera (×2 sobre viaje)'},
    {'Parámetro': 'Tasa social de descuento',
     'Valor': f'{TASA_SOCIAL_DESCUENTO_2026*100:.1f} %',
     'Fuente': 'Informe de Precios Sociales 2026 (MDSF)'},
    {'Parámetro': 'Horizonte de evaluación',
     'Valor': f'{HORIZONTE_SNI_DEFAULT} años',
     'Fuente': 'Captura ≥2 ciclos de reinversión de equipos electrónicos'},
    {'Parámetro': 'Días laborales por año',
     'Valor': f'{DIAS_LABORALES_AÑO}',
     'Fuente': 'Anualización estándar SNI'},
    {'Parámetro': 'Crecimiento de demanda vehicular',
     'Valor': f'{TASA_CRECIMIENTO_DEMANDA_DEFAULT*100:.1f} % anual (referencial)',
     'Fuente': 'Tasas SECTRA Sur, corredor Línea 2'},
    {'Parámetro': 'Valor de la UF',
     'Valor': f'{UF_CLP:,.0f} CLP',
     'Fuente': 'Referencial'},
], columns=['Parámetro', 'Valor', 'Fuente']),
    use_container_width=True, hide_index=True)

st.subheader('Parámetros operacionales del modelo')
st.dataframe(pd.DataFrame([
    {'Parámetro': 'Headway de saturación', 'Valor': '2,0 s/veh',
     'Consideración': 'Tiempo entre vehículos consecutivos al descargar cola; '
     'calibrable con medición de campo.'},
    {'Parámetro': 'Ocupación vehicular', 'Valor': f'{OCUPACION_VEH_DEFAULT} pax/veh',
     'Consideración': 'Supuesto conservador (todos los vehículos livianos); '
     'taxibuses y buses elevan la ocupación real.'},
    {'Parámetro': 'Consumo en ralentí', 'Valor': f'{CONSUMO_RALENTI_L_H} L/h',
     'Consideración': 'Para externalidad de combustible en cola.'},
    {'Parámetro': 'Precio social combustible',
     'Valor': f'{PRECIO_SOCIAL_COMBUSTIBLE_CLP_L} CLP/L',
     'Consideración': 'Precios Sociales 2026.'},
    {'Parámetro': 'Ventana de simulación', 'Valor': '06:00 – 24:00',
     'Consideración': 'Día laboral tipo, período de operación del servicio.'},
    {'Parámetro': 'Umbrales de saturación', 'Valor': 'x≤0,85 / 0,85–1,20 / >1,20',
     'Consideración': 'Definen el régimen y el método de cálculo aplicable.'},
], columns=['Parámetro', 'Valor', 'Consideración']),
    use_container_width=True, hide_index=True)

st.subheader('Consideraciones metodológicas')
st.markdown("""
**Marco de evaluación incremental.** La situación sin proyecto corresponde
a la base ya optimizada con la reconfiguración semafórica (verde inmediato
a las vías laterales tras el paso del tren). El beneficio atribuible al
proyecto es el **incremental** de la integración GPS–SCATS sobre esa base
optimizada, no sobre la configuración previa. Esto evita sobreestimar el
beneficio.

**Composición vehicular conservadora.** Se asume que la totalidad de los
vehículos son livianos. Como los taxibuses y buses tienen mayor ocupación,
el supuesto subestima los beneficiarios y mantiene la evaluación del lado
conservador.

**Frecuencia ferroviaria constante.** No se proyectan aumentos de
frecuencia del servicio, pese a que existen proyectos que los habilitan
(nuevo Puente Biobío). Mantener la frecuencia constante es un supuesto
conservador sobre el beneficio.

**Tratamiento del movimiento principal.** El reparto de verde de la vía
principal (Ruta 160) no se modifica por el componente GPS del proyecto; lo
ajusta la reconfiguración, que pertenece a la situación base. La vía
principal opera con holgura de verde y no acumula cola durante el paso del
tren, por lo que la reasignación de tiempo hacia las laterales no le
impone un costo significativo.

**Cruces sin programación semafórica.** Cuando un cruce no cuenta con
programación registrada, su resultado se estima por transferencia desde
cruces de la misma tipología y régimen de saturación, reportando bandas de
incertidumbre. Esta estimación sirve para dimensionar la cartera, no para
reclamar beneficio formal por cruce.
""")
