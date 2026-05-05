"""Statistical breadth — N random parameter configurations at multiple bit-widths.

Question: does the Z3 attack work on N% of random configurations, or only
on the cherry-picked examples we tested? Measure success rate + time distribution.

Test: at N ∈ {32, 48, 64}, sample N_TRIALS random (a, c, seed) configs
(forcing odd a for full period). Run Z3 attack with K observations; measure:
  - success (sat in time)
  - time elapsed
  - operational equivalence (predicts held-out future correctly)
  - whether recovered tuple equals truth (or up to swap)

Output: percentiles + histogram + failure cases logged.
"""
from __future__ import annotations

import sys, time, random, json
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT


def attack(out_seq, N, timeout_s):
    K = len(out_seq)
    s = Solver()
    s.set("timeout", timeout_s * 1000)
    a1 = BitVec("a1", N); c1 = BitVec("c1", N)
    a2 = BitVec("a2", N); c2 = BitVec("c2", N)
    s1 = [BitVec(f"s1_{k}", N) for k in range(K + 1)]
    s2 = [BitVec(f"s2_{k}", N) for k in range(K + 1)]
    for k in range(K):
        s.add(s1[k + 1] == a1 * s1[k] + c1)
        s.add(s2[k + 1] == a2 * s2[k] + c2)
        s.add(s1[k + 1] ^ s2[k + 1] == BitVecVal(out_seq[k], N))
    s.add(ULT(a1, a2)); s.add((a1 & 1) == 1); s.add((a2 & 1) == 1)
    t0 = time.time()
    res = s.check()
    elapsed = time.time() - t0
    if res != sat:
        return None, elapsed, str(res)
    m = s.model()
    return {
        "a1": m[a1].as_long(), "c1": m[c1].as_long(), "s1_0": m[s1[0]].as_long(),
        "a2": m[a2].as_long(), "c2": m[c2].as_long(), "s2_0": m[s2[0]].as_long(),
    }, elapsed, "sat"


def gen_xor(seed1, seed2, a1, c1, a2, c2, N, n):
    M = 1 << N
    s1, s2 = seed1, seed2
    out = []
    for _ in range(n):
        s1 = (a1 * s1 + c1) % M
        s2 = (a2 * s2 + c2) % M
        out.append(s1 ^ s2)
    return out


def trial(N, K, future_K, seed_for_rng):
    """One random trial: pick params, run attack, verify operational equivalence."""
    rng = random.Random(seed_for_rng)
    M = 1 << N
    a1 = (rng.randrange(1, M) | 1)
    a2 = (rng.randrange(1, M) | 1)
    while a1 == a2:
        a2 = (rng.randrange(1, M) | 1)
    c1 = rng.randrange(M); c2 = rng.randrange(M)
    s1_0 = rng.randrange(M); s2_0 = rng.randrange(M)
    full = gen_xor(s1_0, s2_0, a1, c1, a2, c2, N, K + future_K)
    observed = full[:K]; future_truth = full[K:]
    res, elapsed, status = attack(observed, N, timeout_s=300)
    if res is None:
        return {
            "N": N, "K": K, "elapsed": elapsed, "status": status,
            "observed_match": False, "future_match": False, "trial_seed": seed_for_rng,
        }
    pred = gen_xor(res["s1_0"], res["s2_0"], res["a1"], res["c1"],
                    res["a2"], res["c2"], N, K + future_K)
    return {
        "N": N, "K": K, "elapsed": elapsed, "status": "sat",
        "observed_match": pred[:K] == observed,
        "future_match": pred[K:] == future_truth,
        "trial_seed": seed_for_rng,
    }


def summarize(results):
    elapsed = [r["elapsed"] for r in results if r["status"] == "sat" and r["future_match"]]
    sats = sum(1 for r in results if r["status"] == "sat")
    full = sum(1 for r in results if r.get("future_match"))
    n = len(results)
    if elapsed:
        elapsed.sort()
        p50 = elapsed[len(elapsed) // 2]
        p90 = elapsed[min(int(len(elapsed) * 0.9), len(elapsed) - 1)]
        p99 = elapsed[min(int(len(elapsed) * 0.99), len(elapsed) - 1)]
        emax = elapsed[-1]
    else:
        p50 = p90 = p99 = emax = float('nan')
    return {
        "trials": n, "sat": sats, "full_crack": full,
        "median_s": p50, "p90_s": p90, "p99_s": p99, "max_s": emax,
        "fail_rate": (n - full) / n if n else 0.0,
    }


# ----- run sweep -----
configs = [
    # (N, K_obs, future_K, n_trials)
    (32, 24, 10, 50),
    (48, 32, 10, 30),
    (64, 48, 10, 20),
]

print(f"{'config':30s}  {'trials':>6s}  {'sat':>6s}  {'full':>6s}  {'p50':>8s}  {'p90':>8s}  {'p99':>8s}  {'max':>8s}  {'fail%':>6s}")
print("-" * 110)

import os
out_jsonl = "/tmp/dual_xor_breadth_results.jsonl"
fail_log = "/tmp/dual_xor_breadth_failures.jsonl"
if os.path.exists(out_jsonl): os.remove(out_jsonl)
if os.path.exists(fail_log): os.remove(fail_log)

for N, K, future_K, n_trials in configs:
    label = f"N={N}, K={K}, n={n_trials}"
    results = []
    for t in range(n_trials):
        r = trial(N, K, future_K, seed_for_rng=10_000 * N + t)
        results.append(r)
        with open(out_jsonl, "a") as f:
            f.write(json.dumps(r) + "\n")
        if not r.get("future_match"):
            with open(fail_log, "a") as f:
                f.write(json.dumps(r) + "\n")
        # Live progress: print every 10 trials
        if (t + 1) % 5 == 0 or t == n_trials - 1:
            stats = summarize(results)
            print(f"  {label:28s}  {stats['trials']:>6d}  {stats['sat']:>6d}  {stats['full_crack']:>6d}  "
                  f"{stats['median_s']:>7.2f}s  {stats['p90_s']:>7.2f}s  {stats['p99_s']:>7.2f}s  "
                  f"{stats['max_s']:>7.2f}s  {100*stats['fail_rate']:>5.1f}%", flush=True)
    s = summarize(results)
    print(f"FINAL {label:28s}  {s['trials']:>6d}  {s['sat']:>6d}  {s['full_crack']:>6d}  "
          f"{s['median_s']:>7.2f}s  {s['p90_s']:>7.2f}s  {s['p99_s']:>7.2f}s  "
          f"{s['max_s']:>7.2f}s  {100*s['fail_rate']:>5.1f}%", flush=True)

print(f"\nResults: {out_jsonl}")
print(f"Failures: {fail_log}")
