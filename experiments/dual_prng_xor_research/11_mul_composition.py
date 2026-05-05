"""Z3 attack on dual-LCG MUL composition (out = s1 * s2 mod 2^N).

Companion to the XOR attack. MUL is also non-linear over Z/m (bilinear in s1, s2)
and was shown to fail Hankel-det-gcd in script 02. Z3 BitVec handles native
multiplication, so the same SMT framework applies.

Hypothesis: same attack, similar performance scaling.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT


def attack_mul(out_seq, N, timeout_s=300):
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
        s.add(s1[k + 1] * s2[k + 1] == BitVecVal(out_seq[k], N))
    s.add(ULT(a1, a2))
    s.add((a1 & 1) == 1); s.add((a2 & 1) == 1)
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


def gen_mul(seed1, seed2, a1, c1, a2, c2, N, n):
    M = 1 << N
    s1, s2 = seed1, seed2
    out = []
    for _ in range(n):
        s1 = (a1 * s1 + c1) % M
        s2 = (a2 * s2 + c2) % M
        out.append((s1 * s2) % M)
    return out


# Sweep
print(f"{'N':>3s}  {'K':>4s}  {'status':>7s}  {'elapsed':>10s}  {'observed':>9s}  {'future':>7s}")
print("-" * 60)

configs = [
    (16, 1103515245 & 0xFFFF | 1, 12345 & 0xFFFF, 4321,
        22695477 & 0xFFFF | 1, 1, 6789, 24),
    (24, 1103515245 & 0xFFFFFF | 1, 12345, 1234,
        22695477 & 0xFFFFFF | 1, 1, 5678, 32),
    (32, 1103515245 | 1, 12345, 1234, 22695477 | 1, 1, 5678, 32),
    (48, 6364136223846793005 & ((1<<48)-1) | 1, 12345, 1234,
        22695477 | 1, 1, 5678, 40),
    (64, 6364136223846793005 | 1, 1442695040888963407, 1234,
        22695477 | 1, 1, 5678, 48),
]

for cfg in configs:
    N, a1, c1, s1, a2, c2, s2, K = cfg
    if a1 > a2:
        a1, a2 = a2, a1
        c1, c2 = c2, c1
        s1, s2 = s2, s1
    n_total = K + 10
    full = gen_mul(s1, s2, a1, c1, a2, c2, N, n_total)
    observed = full[:K]; future_truth = full[K:]
    print(f"{N:>3d}  {K:>4d}  ", end="", flush=True)
    timeout = 60 if N <= 24 else (180 if N <= 48 else 600)
    res, elapsed, status = attack_mul(observed, N, timeout_s=timeout)
    if res is None:
        print(f"{status:>7s}  {elapsed:>9.2f}s  —  —")
        continue
    pred = gen_mul(res["s1_0"], res["s2_0"], res["a1"], res["c1"],
                   res["a2"], res["c2"], N, n_total)
    obs_match = pred[:K] == observed
    fut_match = pred[K:] == future_truth
    print(f"{status:>7s}  {elapsed:>9.2f}s  {'✓' if obs_match else '✗':>9s}  {'✓ FULL' if fut_match else '✗':>7s}")
