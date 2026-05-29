"""Shim de compatibilidad. El motor real vive en modelo_cruces.motor.

Se conserva este modulo para no romper imports existentes
(`from motor_sim import Simulador, Inputs, ...`).
"""
from modelo_cruces.motor import (  # noqa: F401
    Inputs, Resultados, PhasePlan, Simulador,
)
