"""Motor de simulacion segundo a segundo (validado contra el Excel original).

Movido desde motor_sim.py. La raiz mantiene un shim de compatibilidad.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

SEC_DAY = 86400


def hhmmss_to_sec(s: str) -> int:
    """'06:00:00' -> 21600"""
    h, m, sec = (s.split('.')[0]).split(':')
    return int(h) * 3600 + int(m) * 60 + int(float(sec))


@dataclass
class Inputs:
    """Insumos del modelo. Los arma la capa de datos (datos.construir_inputs)."""
    crossing: str
    start_s: int
    end_s: int
    h: float
    n_carriles: float
    buffer: int
    k_dem: float
    prog_fases: list
    plan: list
    llegadas: list
    hcall_in: list   # segundos del dia
    hcall_out: list
    # Comportamiento post-HCALL:
    #   False -> reset a posición 0 del ciclo (Base a fase 1)
    #   True  -> reset a green_start (Reconfiguración: salto al verde lateral)
    post_hcall_lateral: bool = False


@dataclass
class Resultados:
    crossing: str
    mode: str
    # Base
    demanda: float
    espera_vs: float          # veh*s
    espera_vh: float          # veh*h
    demora_prom: float        # s/veh
    cola_max: float
    cola_final: float
    # Pre-vaciado
    espera_pre_vs: float
    espera_pre_vh: float
    demora_pre: float
    cola_max_pre: float
    cola_final_pre: float
    # Comparacion
    reduccion_vh: float
    reduccion_pct: float
    reduccion_demora: float
    # Series (opcional, para graficar)
    series: dict = field(default_factory=dict)

    def resumen(self) -> str:
        return (
            f"[{self.crossing} | modo={self.mode}]\n"
            f"  Demanda evaluada      : {self.demanda:10.2f} veh\n"
            f"  Espera base           : {self.espera_vh:10.3f} veh*h  "
            f"({self.demora_prom:.2f} s/veh)\n"
            f"  Espera pre-vaciado    : {self.espera_pre_vh:10.3f} veh*h  "
            f"({self.demora_pre:.2f} s/veh)\n"
            f"  Cola max base / pre   : {self.cola_max:8.3f} / "
            f"{self.cola_max_pre:.3f} veh\n"
            f"  Reduccion espera      : {self.reduccion_vh:10.3f} veh*h  "
            f"({self.reduccion_pct*100:.2f} %)\n"
            f"  Reduccion demora      : {self.reduccion_demora:10.2f} s/veh"
        )


class PhasePlan:
    """Plan de fases de un (cruce, plan_id): ciclo + arreglo verde-movX."""
    def __init__(self, fases: list):
        fases = sorted(fases, key=lambda x: x['cumstart'])
        self.ciclo = int(fases[-1]['ciclo'])
        self.green_start = 0
        self.green_dur = 0
        self.green = np.zeros(self.ciclo, dtype=np.int8)
        # cada fase ocupa [cumstart, cumend)  (cumend incluye entreverde)
        for fz in fases:
            a, b = int(fz['cumstart']), int(fz['cumend'])
            b = min(b, self.ciclo)
            self.green[a:b] = int(fz['green_movx'])
            if int(fz['green_movx']) == 1:
                self.green_start = int(fz['cumstart'])
                self.green_dur = int(fz['dur'])

    def is_green(self, pos: int) -> int:
        return int(self.green[pos % self.ciclo])


class Simulador:
    """Reconstruccion del motor SIM segundo a segundo."""

    def __init__(self, inp: Inputs):
        self.inp = inp
        self._build_plans()
        self._build_arrivals()

    # ---- preparacion de estructuras de consulta -------------------------
    def _build_plans(self):
        """PhasePlan por cada plan_id disponible para el cruce."""
        self.plans: dict[int, PhasePlan] = {}
        by_plan: dict[int, list] = {}
        for fz in self.inp.prog_fases:
            if fz['cross'] == self.inp.crossing:
                by_plan.setdefault(int(fz['plan']), []).append(fz)
        for pid, fases in by_plan.items():
            self.plans[pid] = PhasePlan(fases)
        # tabla horaria de planes (hoja Plan)
        self.plan_table = []
        for row in self.inp.plan:
            self.plan_table.append((
                hhmmss_to_sec(row['ini']),
                hhmmss_to_sec(row['fin']),
                int(row['plan']),
            ))

    def _plan_id_hora(self, tod: int) -> int:
        """AR: plan vigente segun hora del dia (tod en s, 0..86399)."""
        result = 1
        for ini, fin, pid in self.plan_table:
            if ini <= fin:
                hit = ini <= tod < fin
            else:  # cruza medianoche
                hit = tod >= ini or tod < fin
            if hit:
                result = pid
        return result

    def _plan_efectivo(self, ar: int) -> int:
        """AS: usa AR si el cruce tiene ese plan; si no, plan 1."""
        return ar if ar in self.plans else 1

    def _build_arrivals(self):
        """Lambda (veh/s) por segundo del dia para el cruce."""
        self.lam = np.zeros(SEC_DAY, dtype=float)
        # k_dem se aplica de forma EXPLICITA aqui. El Excel ya lo tiene
        # incrustado en Llegadas.lambda, por eso el factor base es lambda
        # y k_dem actua como multiplicador adicional configurable.
        for r in self.inp.llegadas:
            if r['cruce'] != self.inp.crossing:
                continue
            a, b = int(r['t_ini']), int(r['t_fin'])
            self.lam[a:b + 1] = float(r['lambda'])

    # ---- nucleo de simulacion ------------------------------------------
    def run(self, mode: str = 'corrected', keep_series: bool = False) -> Resultados:
        inp = self.inp
        t0, tend = inp.start_s, inp.end_s
        u = inp.n_carriles / inp.h          # capacidad veh/s (L2 = N1/L1)
        kdem = inp.k_dem

        # ventana de calculo. El Excel solo tenia formulas hasta fila ~56799.
        # Simulamos hasta tend + margen para el lookahead del pre-vaciado.
        lookahead = 400
        n = (tend - t0) + lookahead
        idx = np.arange(n)
        C = t0 + idx                         # segundo del dia
        tod = C % SEC_DAY

        # Excel: rango "faithful" del pre-vaciado = filas 7..10807 -> C<=32400
        faithful_limit = t0 + 10800          # = 09:00 si t0=06:00

        # --- HCALL (D, E) ---
        D = np.zeros(n, dtype=np.int8)        # HCALL-CHECK-IN
        E = np.zeros(n, dtype=np.int8)        # HCALL-CHECK-OUT
        for s in inp.hcall_in:
            if t0 <= s < t0 + n:
                D[s - t0] = 1
        for s in inp.hcall_out:
            if t0 <= s < t0 + n:
                E[s - t0] = 1

        # --- plan dinamico por fila (AR, AS, AT, AU, AV) ---
        AR = np.array([self._plan_id_hora(int(x)) for x in tod])
        AS = np.array([self._plan_efectivo(int(x)) for x in AR])
        ciclo = np.array([self.plans[p].ciclo for p in AS])
        gstart = np.array([self.plans[p].green_start for p in AS])
        gdur = np.array([self.plans[p].green_dur for p in AS])

        # --- llegadas (V) ---
        V = self.lam[C % SEC_DAY] * kdem

        # --- columnas recursivas HCALL: F,G,H,I,J ---
        F = np.cumsum(D) - np.cumsum(E)       # HCALL-BAL
        G = (F > 0).astype(np.int8)           # ACTIVE-HCALL
        H = np.zeros(n, dtype=np.int8)        # HCALL-END
        H[1:] = ((F[1:] == 0) & (F[:-1] > 0)).astype(np.int8)
        I = np.cumsum(G)                      # HCALL-PAUSE
        J = (C - C[0]) - I                    # TIME ITP (reloj congelado)

        # --- BASE: M (sticky), N, fase, rojo efectivo, cola ---
        K = (J + 5) % ciclo
        # Salto post-HCALL: a posición 0 (Base a fase 1) o a green_start (Reconfig)
        post_pos = gstart if inp.post_hcall_lateral else np.zeros(n, dtype=int)
        M = np.zeros(n, dtype=int)            # ADJ1
        m = 0
        for i in range(n):
            if H[i] == 1:
                m = int(post_pos[i]) - int(K[i])
            M[i] = m
        N = (J + 5 + M) % ciclo
        # fase verde-movX del plan
        Pgreen = np.array([self.plans[AS[i]].is_green(int(N[i]))
                           for i in range(n)])
        Qred = 1 - Pgreen                     # RED-PLAN-MovX
        R = ((Qred == 1) | (G == 1)).astype(np.int8)   # EFEC-RED
        Geff = 1 - R
        Cap = Geff * u

        # cola base (X) y espera (Y)
        X = np.zeros(n)
        for i in range(n):
            prevq = X[i - 1] if i > 0 else 0.0
            dep = min(Cap[i], prevq + V[i])
            X[i] = max(0.0, prevq + V[i] - dep)
        # W_cum no se necesita: la espera total = suma de X

        # --- PRE-VACIADO: AA (lookahead), AE/AF (salto), AG, cola ---
        AA = np.zeros(n, dtype=np.int8)
        # AA[i] = 1 si en C[i]+gdur[i]+buffer hay un HCALL-IN
        for i in range(n):
            tgt = C[i] + int(gdur[i]) + inp.buffer
            j = tgt - t0
            if 0 <= j < n:
                if mode == 'faithful' and tgt > faithful_limit:
                    continue                 # bug Excel: lookup acotado
                AA[i] = D[j]

        AF = np.zeros(n, dtype=int)
        af = 0
        for i in range(n):
            base = (J[i] + 5 + af) % ciclo[i]
            if AA[i] == 1:
                ae = int(gstart[i]) - int(base)
            elif H[i] == 1:
                ae = int(post_pos[i]) - int(base)
            else:
                ae = 0
            af = af + ae
            AF[i] = af
        AG = (J + 5 + AF) % ciclo
        AIgreen = np.array([self.plans[AS[i]].is_green(int(AG[i]))
                            for i in range(n)])
        AJred = 1 - AIgreen
        AK = ((AJred == 1) | (G == 1)).astype(np.int8)   # EFEC-RED-PRE
        ALeff = 1 - AK
        CapPre = ALeff * u

        AO = np.zeros(n)                      # cola pre
        for i in range(n):
            prevq = AO[i - 1] if i > 0 else 0.0
            dep = min(CapPre[i], prevq + V[i])
            AO[i] = max(0.0, prevq + V[i] - dep)

        # --- mascara "Check" (S): dentro de la ventana de evaluacion ---
        S = C < tend                          # B < H1

        # rango para cola max/final
        if mode == 'faithful':
            rng = S & (C <= faithful_limit)   # bug Excel: solo 3 h
        else:
            rng = S                           # corregido: ventana completa

        # --- KPIs ---
        demanda = float(np.sum(V[S]))
        espera_vs = float(np.sum(X[S]))
        if mode == 'faithful':
            # bug Excel: AE3 (espera pre) suma SOLO hasta fila 10807
            espera_pre_vs = float(np.sum(AO[S & (C <= faithful_limit)]))
            demanda_pre = demanda             # AE2 usa ventana completa
        else:
            espera_pre_vs = float(np.sum(AO[S]))
            demanda_pre = demanda

        espera_vh = espera_vs / 3600
        espera_pre_vh = espera_pre_vs / 3600
        demora = espera_vs / demanda if demanda else 0.0
        demora_pre = espera_pre_vs / demanda_pre if demanda_pre else 0.0
        cola_max = float(np.max(X[rng])) if np.any(rng) else 0.0
        cola_max_pre = float(np.max(AO[rng])) if np.any(rng) else 0.0
        cola_final = float(X[rng][-1]) if np.any(rng) else 0.0
        cola_final_pre = float(AO[rng][-1]) if np.any(rng) else 0.0
        red_vh = espera_vh - espera_pre_vh
        red_pct = red_vh / espera_vh if espera_vh else 0.0

        series = {}
        if keep_series:
            series = dict(C=C[S], V=V[S], Q=X[S], Qpre=AO[S],
                          G=G[S], R=R[S], Geff=Geff[S], Cap=Cap[S],
                          AK=AK[S], plan=AS[S], ciclo=ciclo[S])

        return Resultados(
            crossing=inp.crossing, mode=mode,
            demanda=demanda, espera_vs=espera_vs, espera_vh=espera_vh,
            demora_prom=demora, cola_max=cola_max, cola_final=cola_final,
            espera_pre_vs=espera_pre_vs, espera_pre_vh=espera_pre_vh,
            demora_pre=demora_pre, cola_max_pre=cola_max_pre,
            cola_final_pre=cola_final_pre,
            reduccion_vh=red_vh, reduccion_pct=red_pct,
            reduccion_demora=demora - demora_pre,
            series=series,
        )


    # ---- modo estocastico (Monte Carlo, llegadas Poisson) --------------
    def run_stochastic(self, n_rep: int = 30, seed: int = 1) -> dict:
        """Corre n_rep replicaciones con llegadas Poisson por segundo.

        El modelo Excel es deterministico: usa la tasa media lambda como
        si llegaran 0.03 veh exactos cada segundo. La literatura (Newell
        1968) advierte que esto SUBESTIMA la cola. Aqui las llegadas de
        cada segundo se muestrean Poisson(lambda) y se promedia.
        Devuelve media y desv. de espera base y pre (veh*h).
        """
        rng = np.random.default_rng(seed)
        inp = self.inp
        t0, tend = inp.start_s, inp.end_s
        u = inp.n_carriles / inp.h
        n = (tend - t0) + 400
        C = t0 + np.arange(n)
        lam = self.lam[C % SEC_DAY] * inp.k_dem
        # estructura de rojo efectivo: se calcula una vez (no depende de V)
        det = self.run(mode='corrected')          # para reusar mascara
        base_det = self.run(mode='corrected')
        esperas_base, esperas_pre = [], []
        # precomputar R y AK (independientes de V) via run interno
        # se reusa la logica: re-simular con V aleatorio
        for _ in range(n_rep):
            arr = rng.poisson(lam).astype(float)
            eb, ep = self._sim_con_llegadas(arr, u, n, C, tend)
            esperas_base.append(eb)
            esperas_pre.append(ep)
        eb = np.array(esperas_base) / 3600
        ep = np.array(esperas_pre) / 3600
        return dict(
            det_base_vh=base_det.espera_vh, det_pre_vh=base_det.espera_pre_vh,
            est_base_vh=float(eb.mean()), est_base_sd=float(eb.std()),
            est_pre_vh=float(ep.mean()), est_pre_sd=float(ep.std()),
            sesgo_pct=float((eb.mean() - base_det.espera_vh)
                            / base_det.espera_vh * 100),
        )

    def _sim_con_llegadas(self, V, u, n, C, tend):
        """Nucleo de cola reusable con un vector de llegadas dado."""
        inp = self.inp
        t0 = inp.start_s
        D = np.zeros(n, np.int8); E = np.zeros(n, np.int8)
        for s in inp.hcall_in:
            if t0 <= s < t0 + n:
                D[s - t0] = 1
        for s in inp.hcall_out:
            if t0 <= s < t0 + n:
                E[s - t0] = 1
        tod = C % SEC_DAY
        AS = np.array([self._plan_efectivo(self._plan_id_hora(int(x)))
                       for x in tod])
        ciclo = np.array([self.plans[p].ciclo for p in AS])
        gstart = np.array([self.plans[p].green_start for p in AS])
        post_pos = gstart if inp.post_hcall_lateral else np.zeros(n, dtype=int)
        F = np.cumsum(D) - np.cumsum(E)
        G = (F > 0).astype(np.int8)
        H = np.zeros(n, np.int8)
        H[1:] = ((F[1:] == 0) & (F[:-1] > 0)).astype(np.int8)
        I = np.cumsum(G)
        J = (C - C[0]) - I
        K = (J + 5) % ciclo
        M = np.zeros(n, int); m = 0
        for i in range(n):
            if H[i] == 1:
                m = int(post_pos[i]) - int(K[i])
            M[i] = m
        N = (J + 5 + M) % ciclo
        Pg = np.array([self.plans[AS[i]].is_green(int(N[i]))
                       for i in range(n)])
        R = ((1 - Pg == 1) | (G == 1)).astype(np.int8)
        Cap = (1 - R) * u
        X = np.zeros(n)
        for i in range(n):
            pq = X[i - 1] if i > 0 else 0.0
            X[i] = max(0.0, pq + V[i] - min(Cap[i], pq + V[i]))
        S = C < tend
        # escenario pre: sin lookahead-bug
        gdur = np.array([self.plans[p].green_dur for p in AS])
        AA = np.zeros(n, np.int8)
        for i in range(n):
            j = (C[i] + int(gdur[i]) + inp.buffer) - t0
            if 0 <= j < n:
                AA[i] = D[j]
        AF = np.zeros(n, int); af = 0
        for i in range(n):
            b = (J[i] + 5 + af) % ciclo[i]
            ae = (int(gstart[i]) - int(b) if AA[i] == 1
                  else (int(post_pos[i]) - int(b) if H[i] == 1 else 0))
            af += ae; AF[i] = af
        AG = (J + 5 + AF) % ciclo
        AIg = np.array([self.plans[AS[i]].is_green(int(AG[i]))
                        for i in range(n)])
        AK = ((1 - AIg == 1) | (G == 1)).astype(np.int8)
        CapP = (1 - AK) * u
        AO = np.zeros(n)
        for i in range(n):
            pq = AO[i - 1] if i > 0 else 0.0
            AO[i] = max(0.0, pq + V[i] - min(CapP[i], pq + V[i]))
        return float(np.sum(X[S])), float(np.sum(AO[S]))


if __name__ == "__main__":
    print("Motor de simulacion SIM. Importar Simulador/Inputs desde otro modulo.")
