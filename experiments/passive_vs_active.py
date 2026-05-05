"""Benchmark: K-shot requirement passive vs active.

For each scenario, find the MINIMUM K such that:
  - Passive: K observations alone uniquely determine the rule
  - Active:  K_initial + K_active queries suffice via Kazdov's active query

This is the empirical data that underpins the "active learning for cryptanalytic
rule recovery" paper claim — measuring the gap, not just asserting it.
"""
from __future__ import annotations

import json
import time

from kbound.active.state import ActiveSession
from kbound.active.posterior import (
    LCGCandidate, PolycoefCandidate, ModMulCandidate, ModExpCandidate,
    build_initial_pool, reduce_to_unique_or_lower,
)


# ============================================================
# Scenarios — same families as case studies
# ============================================================

SCENARIOS = [
    {"id": "lcg_mod7", "true": LCGCandidate(3, 2, 7),
     "inputs": [17, 22, 41, 92, 3, 55, 12, 9, 30, 100, 50, 200, 5]},
    {"id": "lcg_mod11", "true": LCGCandidate(5, 4, 11),
     "inputs": [10, 20, 30, 40, 50, 70, 80, 90, 100, 60, 25, 33, 77]},
    {"id": "lcg_mod13", "true": LCGCandidate(4, 1, 13),
     "inputs": [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]},
    {"id": "polycoef_mod11", "true": PolycoefCandidate(2, 3, 5, 11),
     "inputs": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14]},
    {"id": "modmul_mod11", "true": ModMulCandidate(3, 11),
     "inputs": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20]},
    {"id": "modmul_mod13", "true": ModMulCandidate(7, 13),
     "inputs": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14]},
    {"id": "modexp_mod11", "true": ModExpCandidate(3, 11),
     "inputs": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 16]},
]


def measure_passive_K(scenario) -> int:
    """Find minimal K such that the first K observations uniquely determine the rule."""
    inputs = scenario["inputs"]
    true = scenario["true"]
    for K in range(2, len(inputs) + 1):
        obs = [(x, true.predict(x)) for x in inputs[:K]]
        candidates = build_initial_pool(obs)
        candidates = reduce_to_unique_or_lower(candidates)
        if len(candidates) == 1:
            return K
    return len(inputs) + 1  # not unique even with all observations


def measure_active_K(scenario) -> tuple[int, int, int]:
    """Find K via active strategy: start with 2, query optimally until unique.

    Returns (K_initial, K_active_queries, K_total).
    """
    inputs = scenario["inputs"]
    true = scenario["true"]
    K_init = 2
    initial_obs = [(x, true.predict(x)) for x in inputs[:K_init]]
    session = ActiveSession(initial_obs)

    n_active = 0
    max_iter = 20
    while not session.is_unique and not session.is_failed and n_active < max_iter:
        suggestion = session.suggest_query()
        x_q = suggestion["suggested_x"]
        if x_q is None:
            break
        y_q = true.predict(x_q)
        session.add_observation(x_q, y_q)
        n_active += 1

    return K_init, n_active, K_init + n_active


def main():
    results = []
    print(f"{'Scenario':<20} {'Passive K':>10} {'Active K_total':>16} {'Gap':>8}")
    print("-" * 60)
    for sc in SCENARIOS:
        t0 = time.perf_counter()
        Kp = measure_passive_K(sc)
        t_passive = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        Ki, Ka, Kt = measure_active_K(sc)
        t_active = (time.perf_counter() - t0) * 1000

        gap = Kp - Kt
        print(f"{sc['id']:<20} {Kp:>10} {Kt:>16} {gap:>+8d}")
        results.append({
            "scenario": sc["id"],
            "passive_K": Kp,
            "active_K_initial": Ki,
            "active_K_queries": Ka,
            "active_K_total": Kt,
            "gap": gap,
            "passive_ms": round(t_passive, 1),
            "active_ms": round(t_active, 1),
        })

    print()
    avg_passive = sum(r["passive_K"] for r in results) / len(results)
    avg_active = sum(r["active_K_total"] for r in results) / len(results)
    avg_gap = sum(r["gap"] for r in results) / len(results)
    print(f"AVERAGE         passive K = {avg_passive:.1f}")
    print(f"                active K  = {avg_active:.1f}")
    print(f"                gap       = {avg_gap:+.1f} ({(avg_passive/avg_active):.2f}× reduction)")

    out_path = "/Users/kazdov/code/OriginalKazdov/kbound/experiments/passive_vs_active_results.json"
    with open(out_path, "w") as f:
        json.dump({"avg_passive": avg_passive, "avg_active": avg_active,
                   "ratio": avg_passive/avg_active, "results": results}, f, indent=2)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
