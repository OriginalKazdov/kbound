"""3-LCG XOR composition — Marsaglia-KISS-style ensemble.

Real-world deployed RNGs combine 3-4 generators (KISS, SuperKISS, MRG32k3a).
The classical KISS uses addition mod 2^32; some "improved" variants use XOR
under the (mistaken) belief that XOR mixing is harder to invert.

Our 2-LCG attack scaled mild-superlinear in N up to 64-bit. How does adding
a THIRD LCG affect Z3's solve time?

Out_k = state1_k XOR state2_k XOR state3_k

12 unknowns: 3 × (a, c, seed) all of width N.
Tied output bits: still N per observation.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT


def attack_3lcg_xor(out_seq, N, timeout_s=600):
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

    # Symmetry-breaking: lex-order a1 < a2 < a3 to remove 6-fold permutation symmetry
    s.add(ULT(a1, a2)); s.add(ULT(a2, a3))
    # Full-period: odd a
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


def gen_xor_3(seeds, params, N, n):
    M = 1 << N
    s = list(seeds)
    out = []
    for _ in range(n):
        for i in range(3):
            a, c = params[i]
            s[i] = (a * s[i] + c) % M
        out.append(s[0] ^ s[1] ^ s[2])
    return out


# Sweep: 3-LCG XOR at increasing N
print(f"{'N':>3s}  {'K':>4s}  {'status':>7s}  {'elapsed':>10s}  {'observed':>9s}  {'future':>7s}")
print("-" * 60)

# Marsaglia-style canonical params (3 LCGs, distinct multipliers)
configs = [
    (16, [(21845, 1, 4321), (25173, 13849, 6789), (29241, 7, 2049)]),
    (24, [(1664525, 1013904223, 12345),
          (1103515245, 12345, 6789),
          (22695477, 1, 9999)]),
    (32, [(1664525, 1013904223, 12345),
          (1103515245, 12345, 6789),
          (22695477, 1, 9999)]),
    (40, [(6364136223846793005 & ((1 << 40) - 1), 1442695040888963407 & ((1 << 40) - 1), 12345),
          (1103515245, 12345, 6789),
          (22695477, 1, 9999)]),
    (48, [(6364136223846793005 & ((1 << 48) - 1), 1442695040888963407 & ((1 << 48) - 1), 12345),
          (1103515245, 12345, 6789),
          (22695477, 1, 9999)]),
]

for N, lcgs in configs:
    # Force a's odd, sort by a
    lcgs = [(a | 1, c, s) for (a, c, s) in lcgs]
    lcgs.sort(key=lambda t: t[0])
    params = [(a, c) for (a, c, s) in lcgs]
    seeds = [s for (a, c, s) in lcgs]
    K = max(48, 8 * 3)  # 3 LCGs need more obs
    n_total = K + 10
    full = gen_xor_3(seeds, params, N, n_total)
    observed = full[:K]; future_truth = full[K:]
    print(f"{N:>3d}  {K:>4d}  ", end="", flush=True)
    res, elapsed, status = attack_3lcg_xor(observed, N, timeout_s=900)
    if res is None:
        print(f"{status:>7s}  {elapsed:>9.2f}s  —  —")
        continue
    pred = gen_xor_3([res["s1_0"], res["s2_0"], res["s3_0"]],
                     [(res["a1"], res["c1"]), (res["a2"], res["c2"]), (res["a3"], res["c3"])],
                     N, n_total)
    obs_match = pred[:K] == observed
    fut_match = pred[K:] == future_truth
    print(f"{status:>7s}  {elapsed:>9.2f}s  {'✓' if obs_match else '✗':>9s}  {'✓ FULL' if fut_match else '✗':>7s}")
