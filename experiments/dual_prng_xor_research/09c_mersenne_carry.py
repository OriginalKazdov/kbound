"""Mersenne attack with explicit carry-bit encoding.

For LCG step over Z/m (m = 2^p - 1), we have:
    raw = a * s + c   (in 2*p+2 bit BitVec, always < 2 * m^2 ~= 2^(2p+1))
    s_next = raw mod m

Since s, a, c < m, raw < m * (a + 1) <= m^2 + ... but tractable carries:
We encode `s_next = raw - m * q` where q is unknown integer in [0, raw/m].
For small constants this is hard. But we can use a 2-step Mersenne reduction:

    Step 1 reduce: r1 = (raw & m) + (raw >> p)    # in [0, 2m]
    Step 2 reduce: s_next = r1 if r1 < m else (r1 - m)  # in [0, m)

Encoded as Z3 BitVec with If(ULT(r1, m), r1, r1 - m).

This avoids URem (Z3 expensive for non-pow-2) and uses only shift/add/cond
which are cheap.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT, LShR, If


def attack_mersenne_carry(out_seq, p_bits, timeout_s=600):
    K = len(out_seq)
    p = p_bits
    M = (1 << p) - 1
    W = 2 * p + 4

    s = Solver()
    s.set("timeout", timeout_s * 1000)

    M_bv = BitVecVal(M, W)
    a1 = BitVec("a1", W); c1 = BitVec("c1", W)
    a2 = BitVec("a2", W); c2 = BitVec("c2", W)
    s1 = [BitVec(f"s1_{k}", W) for k in range(K + 1)]
    s2 = [BitVec(f"s2_{k}", W) for k in range(K + 1)]

    for v in [a1, c1, a2, c2] + s1 + s2:
        s.add(ULT(v, M_bv))
    s.add(ULT(BitVecVal(0, W), a1))
    s.add(ULT(a1, a2))
    s.add((a1 & 1) == 1); s.add((a2 & 1) == 1)

    def step(prev_s, a, c):
        raw = a * prev_s + c
        # Mersenne reduction: r1 = (raw & m) + (raw >> p)  ∈ [0, 2m]
        r1 = (raw & M_bv) + LShR(raw, p)
        # r1 might be 0..2m. Reduce one more time:
        # If r1 < m, result = r1; else result = r1 - m
        # Special case r1 == m: m mod m = 0
        result = If(ULT(r1, M_bv),
                    r1,
                    If(r1 == M_bv, BitVecVal(0, W), r1 - M_bv))
        return result

    for k in range(K):
        s.add(s1[k + 1] == step(s1[k], a1, c1))
        s.add(s2[k + 1] == step(s2[k], a2, c2))
        s.add(s1[k + 1] ^ s2[k + 1] == BitVecVal(out_seq[k], W))

    t0 = time.time()
    res = s.check()
    elapsed = time.time() - t0
    if res != sat:
        return None, elapsed, str(res)
    m_model = s.model()
    return {
        "a1": m_model[a1].as_long(), "c1": m_model[c1].as_long(),
        "s1_0": m_model[s1[0]].as_long(),
        "a2": m_model[a2].as_long(), "c2": m_model[c2].as_long(),
        "s2_0": m_model[s2[0]].as_long(),
    }, elapsed, "sat"


def gen_xor_mersenne(seed1, seed2, a1, c1, a2, c2, p_bits, n):
    M = (1 << p_bits) - 1
    s1, s2 = seed1 % M, seed2 % M
    out = []
    for _ in range(n):
        s1 = (a1 * s1 + c1) % M
        s2 = (a2 * s2 + c2) % M
        out.append(s1 ^ s2)
    return out


# Sweep
print(f"{'p':>3s}  {'m':>14s}  {'K':>4s}  {'status':>7s}  {'elapsed':>10s}  {'observed':>9s}  {'future':>7s}")
print("-" * 70)

configs = [
    (7,  [(5, 11, 13), (17, 7, 19)],   24),
    (11, [(43, 11, 137), (89, 13, 211)], 24),
    (17, [(43213, 12345, 1234), (28657, 1, 5678)], 28),
    (23, [(2147481649, 12345, 1234), (8388607, 1, 5678)], 32),
    (31, [(1103515245, 12345, 1234), (22695477, 1, 5678)], 36),
]

for p, lcgs, K in configs:
    M = (1 << p) - 1
    lcgs = [(a | 1, c, s) for (a, c, s) in lcgs]
    lcgs = [(a % M, c % M, s % M) for (a, c, s) in lcgs]
    lcgs = [(a | 1, c, s) for (a, c, s) in lcgs]  # re-force odd after mod
    lcgs.sort(key=lambda t: t[0])
    a1, c1, s1 = lcgs[0]
    a2, c2, s2 = lcgs[1]
    n_total = K + 10
    full = gen_xor_mersenne(s1, s2, a1, c1, a2, c2, p, n_total)
    observed = full[:K]; future_truth = full[K:]
    print(f"{p:>3d}  {M:>14d}  {K:>4d}  ", end="", flush=True)
    timeout = 60 if p <= 11 else (300 if p <= 23 else 900)
    res, elapsed, status = attack_mersenne_carry(observed, p, timeout_s=timeout)
    if res is None:
        print(f"{status:>7s}  {elapsed:>9.2f}s  —  —")
        continue
    pred = gen_xor_mersenne(res["s1_0"], res["s2_0"], res["a1"], res["c1"],
                              res["a2"], res["c2"], p, n_total)
    obs_match = pred[:K] == observed
    fut_match = pred[K:] == future_truth
    print(f"{status:>7s}  {elapsed:>9.2f}s  {'✓' if obs_match else '✗':>9s}  {'✓ FULL' if fut_match else '✗':>7s}")
