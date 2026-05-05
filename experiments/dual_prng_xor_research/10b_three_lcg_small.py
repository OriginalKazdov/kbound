"""3-LCG XOR composition at SMALL N — does it scale at all?

Earlier 3-LCG attempt at N=16 hung past 5 min. Try N=8, 10, 12 to find
the regime where Z3 can converge on the harder 9-unknown system.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT


def attack_3lcg_xor(out_seq, N, timeout_s=300):
    K = len(out_seq)
    s = Solver()
    s.set("timeout", timeout_s * 1000)
    a1 = BitVec("a1", N); c1 = BitVec("c1", N)
    a2 = BitVec("a2", N); c2 = BitVec("c2", N)
    a3 = BitVec("a3", N); c3 = BitVec("c3", N)
    s1 = [BitVec(f"s1_{k}", N) for k in range(K + 1)]
    s2 = [BitVec(f"s2_{k}", N) for k in range(K + 1)]
    s3 = [BitVec(f"s3_{k}", N) for k in range(K + 1)]
    for k in range(K):
        s.add(s1[k + 1] == a1 * s1[k] + c1)
        s.add(s2[k + 1] == a2 * s2[k] + c2)
        s.add(s3[k + 1] == a3 * s3[k] + c3)
        s.add(s1[k + 1] ^ s2[k + 1] ^ s3[k + 1] == BitVecVal(out_seq[k], N))
    s.add(ULT(a1, a2)); s.add(ULT(a2, a3))
    s.add((a1 & 1) == 1); s.add((a2 & 1) == 1); s.add((a3 & 1) == 1)
    t0 = time.time()
    res = s.check()
    elapsed = time.time() - t0
    if res != sat:
        return None, elapsed, str(res)
    m = s.model()
    return {
        "a1": m[a1].as_long(), "c1": m[c1].as_long(), "s1_0": m[s1[0]].as_long(),
        "a2": m[a2].as_long(), "c2": m[c2].as_long(), "s2_0": m[s2[0]].as_long(),
        "a3": m[a3].as_long(), "c3": m[c3].as_long(), "s3_0": m[s3[0]].as_long(),
    }, elapsed, "sat"


def gen3(seeds, params, N, n):
    M = 1 << N
    s = list(seeds)
    out = []
    for _ in range(n):
        for i in range(3):
            a, c = params[i]
            s[i] = (a * s[i] + c) % M
        out.append(s[0] ^ s[1] ^ s[2])
    return out


print(f"{'N':>3s}  {'K':>4s}  {'status':>7s}  {'elapsed':>10s}  {'observed':>9s}  {'future':>7s}")
print("-" * 60)

# Smaller N, K growing with N
configs = [
    (8,  [(17, 7, 3), (29, 11, 5), (53, 13, 7)], 32),
    (10, [(101, 7, 3), (227, 11, 5), (419, 13, 7)], 40),
    (12, [(1103515245 & 4095 | 1, 7, 3),
          (22695477 & 4095 | 1, 11, 5),
          (1664525 & 4095 | 1, 13, 7)], 48),
    (14, [(1103515245 & 16383 | 1, 7, 3),
          (22695477 & 16383 | 1, 11, 5),
          (1664525 & 16383 | 1, 13, 7)], 56),
    (16, [(1103515245 & 65535 | 1, 7, 3),
          (22695477 & 65535 | 1, 11, 5),
          (1664525 & 65535 | 1, 13, 7)], 64),
]

for N, lcgs, K in configs:
    lcgs = [(a | 1, c, s) for (a, c, s) in lcgs]
    lcgs.sort(key=lambda t: t[0])
    params = [(a, c) for (a, c, s) in lcgs]
    seeds = [s for (a, c, s) in lcgs]
    n_total = K + 10
    full = gen3(seeds, params, N, n_total)
    observed = full[:K]; future_truth = full[K:]
    print(f"{N:>3d}  {K:>4d}  ", end="", flush=True)
    timeout = 60 if N <= 10 else (300 if N <= 12 else (600 if N <= 14 else 1200))
    res, elapsed, status = attack_3lcg_xor(observed, N, timeout_s=timeout)
    if res is None:
        print(f"{status:>7s}  {elapsed:>9.2f}s  —  —")
        continue
    pred = gen3([res["s1_0"], res["s2_0"], res["s3_0"]],
                 [(res["a1"], res["c1"]), (res["a2"], res["c2"]), (res["a3"], res["c3"])],
                 N, n_total)
    obs_match = pred[:K] == observed
    fut_match = pred[K:] == future_truth
    print(f"{status:>7s}  {elapsed:>9.2f}s  {'✓' if obs_match else '✗':>9s}  {'✓ FULL' if fut_match else '✗ ambig':>7s}")
