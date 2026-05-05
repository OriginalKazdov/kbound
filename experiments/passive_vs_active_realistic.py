"""Realistic benchmark: passive (random testnet observations) vs active (optimal queries).

Real-world auditor scenario:
  - Passive: pulls N sequential transactions from testnet → inputs from a narrow
    correlated range (e.g., block.timestamp values close together, sequential
    block numbers). These are HIGHLY correlated and information-poor.
  - Active: chooses each query specifically to disambiguate remaining candidates.
    Can request inputs FAR from observed ones to break degeneracies.

This is where active query shines — when input distribution is constrained,
correlated, or just sub-optimal for natural disambiguation.
"""
from __future__ import annotations

import json
import random
import time

from kbound.active.state import ActiveSession
from kbound.active.posterior import (
    LCGCandidate, PolycoefCandidate, ModMulCandidate, ModExpCandidate,
    build_initial_pool, reduce_to_unique_or_lower,
)


SCENARIOS = [
    {"id": "lcg_mod7",       "true": LCGCandidate(3, 2, 7)},
    {"id": "lcg_mod11",      "true": LCGCandidate(5, 4, 11)},
    {"id": "lcg_mod13",      "true": LCGCandidate(4, 1, 13)},
    {"id": "polycoef_mod11", "true": PolycoefCandidate(2, 3, 5, 11)},
    {"id": "modmul_mod11",   "true": ModMulCandidate(3, 11)},
    {"id": "modmul_mod13",   "true": ModMulCandidate(7, 13)},
    {"id": "modexp_mod11",   "true": ModExpCandidate(3, 11)},
]


def measure_passive_correlated(scenario, base_input: int, max_K: int = 30) -> int:
    """Passive K with CORRELATED inputs — simulates sequential testnet observations.

    The auditor pulls observations starting at a narrow base_input and incrementing
    by 1 each time (like consecutive block numbers).
    """
    true = scenario["true"]
    for K in range(2, max_K):
        inputs = [base_input + i for i in range(K)]
        obs = [(x, true.predict(x)) for x in inputs]
        candidates = build_initial_pool(obs)
        candidates = reduce_to_unique_or_lower(candidates)
        if len(candidates) == 1:
            return K
    return max_K + 1


def measure_passive_random(scenario, seed: int, max_K: int = 30) -> int:
    """Passive K with RANDOM inputs — auditor gets uncorrelated samples."""
    rng = random.Random(seed)
    true = scenario["true"]
    inputs = []
    for K in range(2, max_K):
        while len(inputs) < K:
            inputs.append(rng.randint(0, 200))
        obs = [(x, true.predict(x)) for x in inputs[:K]]
        candidates = build_initial_pool(obs)
        candidates = reduce_to_unique_or_lower(candidates)
        if len(candidates) == 1:
            return K
    return max_K + 1


def measure_active(scenario, base_input: int, max_iter: int = 20) -> tuple[int, int, int]:
    """Active K — initial observations from sequential window + optimal queries."""
    true = scenario["true"]
    K_init = 2
    initial = [(base_input + i, true.predict(base_input + i)) for i in range(K_init)]
    session = ActiveSession(initial)

    n_active = 0
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
    print(f"{'Scenario':<18} {'Passive (corr)':>15} {'Passive (rand)':>15} {'Active':>8} {'Gap vs corr':>12}")
    print("-" * 75)

    results = []
    base_inputs = [100, 1000, 50, 500, 10, 200, 7]

    for sc, base in zip(SCENARIOS, base_inputs):
        Kp_corr = measure_passive_correlated(sc, base)
        # Average across 3 random seeds for stability
        Kp_rand_runs = [measure_passive_random(sc, seed) for seed in range(3)]
        Kp_rand_avg = sum(Kp_rand_runs) / len(Kp_rand_runs)

        Ki, Ka, Kt = measure_active(sc, base)
        gap = Kp_corr - Kt
        print(f"{sc['id']:<18} {Kp_corr:>15} {Kp_rand_avg:>15.1f} {Kt:>8} {gap:>+12d}")
        results.append({
            "scenario": sc["id"],
            "passive_correlated_K": Kp_corr,
            "passive_random_K_avg": Kp_rand_avg,
            "active_K_total": Kt,
            "gap_vs_correlated": gap,
        })

    avg_corr = sum(r["passive_correlated_K"] for r in results) / len(results)
    avg_rand = sum(r["passive_random_K_avg"] for r in results) / len(results)
    avg_active = sum(r["active_K_total"] for r in results) / len(results)

    print()
    print(f"AVERAGE     passive (correlated) K = {avg_corr:.1f}")
    print(f"            passive (random)     K = {avg_rand:.1f}")
    print(f"            active               K = {avg_active:.1f}")
    print(f"            reduction (vs correlated): {avg_corr/avg_active:.2f}×")
    print(f"            reduction (vs random):     {avg_rand/avg_active:.2f}×")

    out_path = "/Users/kazdov/code/OriginalKazdov/kbound/experiments/passive_vs_active_realistic_results.json"
    with open(out_path, "w") as f:
        json.dump({
            "avg_passive_correlated": avg_corr,
            "avg_passive_random": avg_rand,
            "avg_active": avg_active,
            "ratio_vs_correlated": avg_corr / avg_active,
            "ratio_vs_random": avg_rand / avg_active,
            "results": results,
        }, f, indent=2)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
