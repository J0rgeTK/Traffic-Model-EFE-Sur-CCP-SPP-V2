"""
Composicion vehicular y ocupacion efectiva
==========================================
Incorpora la presencia de buses de transporte publico en el calculo del
beneficio social. Los buses transportan mas pasajeros que un vehiculo
liviano, de modo que el beneficio por ahorro de tiempo —que se mide en
pasajeros-hora— es mayor cuando una fraccion del flujo corresponde a buses.

Procedimiento (por cruce y hora):
  - El flujo total de vehiculos de la hora se mantiene constante (el dato
    aforado). De ese total, una parte son buses (segun la frecuencia de
    lineas de transporte publico) y el resto, vehiculos livianos.
        livianos(h) = max(0, flujo(h) - buses(h))
  - La ocupacion media de la hora es el promedio ponderado por composicion:
        O(h) = [ buses(h)*O_bus + livianos(h)*O_liviano ] / flujo(h)
  - La ocupacion efectiva del cruce pondera O(h) por el flujo de cada hora
    (proxy de la distribucion de la espera a lo largo del dia):
        O_efectiva = sum_h [ flujo(h)*O(h) ] / sum_h flujo(h)

Con O_bus = 20 pax/bus por defecto. Si un cruce no tiene lineas de buses
registradas, su ocupacion efectiva es la ocupacion de vehiculo liviano.
"""
from __future__ import annotations

OCUPACION_BUS_DEFAULT = 20.0


def ocupacion_efectiva_cruce(con, cruce_id: int, campania_id: int,
                             ocup_liviano: float,
                             ocup_bus: float = OCUPACION_BUS_DEFAULT) -> dict:
    """Calcula la ocupacion efectiva de un cruce considerando los buses.

    Devuelve un dict con la ocupacion efectiva y antecedentes para mostrar.
    """
    cur = con.cursor()
    # Flujo por hora (campania vigente)
    flujo_h: dict[int, float] = {}
    for r in cur.execute(
        "SELECT t_inicio_s, flujo_veh_h FROM dem.llegadas_vehiculares "
        "WHERE campania_id=? AND cruce_id=? ORDER BY t_inicio_s",
        (campania_id, cruce_id)).fetchall():
        flujo_h[r['t_inicio_s'] // 3600] = r['flujo_veh_h']

    # Buses por hora (suma de lineas)
    buses_h: dict[int, float] = {}
    try:
        for r in cur.execute(
            "SELECT hora, SUM(buses_hora) b FROM dem.buses_cruce "
            "WHERE cruce_id=? GROUP BY hora", (cruce_id,)).fetchall():
            buses_h[r['hora']] = r['b'] or 0
    except Exception:
        buses_h = {}

    if not flujo_h:
        return {'ocupacion_efectiva': ocup_liviano, 'tiene_buses': False,
                'buses_dia': 0, 'flujo_dia': 0, 'pax_bus_dia': 0, 'pax_liviano_dia': 0}

    num = 0.0; den = 0.0
    buses_dia = 0.0; flujo_dia = 0.0; pax_bus = 0.0; pax_liv = 0.0
    for h, f in flujo_h.items():
        if f <= 0:
            continue
        b = min(f, buses_h.get(h, 0))          # no mas buses que el flujo total
        liv = max(0.0, f - b)                   # se mantiene el flujo total
        o_h = (b * ocup_bus + liv * ocup_liviano) / f
        num += f * o_h; den += f
        buses_dia += b; flujo_dia += f
        pax_bus += b * ocup_bus; pax_liv += liv * ocup_liviano

    o_ef = num / den if den > 0 else ocup_liviano
    return {
        'ocupacion_efectiva': o_ef,
        'tiene_buses': bool(buses_h),
        'buses_dia': buses_dia, 'flujo_dia': flujo_dia,
        'pax_bus_dia': pax_bus, 'pax_liviano_dia': pax_liv,
        'frac_buses': (buses_dia / flujo_dia) if flujo_dia > 0 else 0.0,
    }
