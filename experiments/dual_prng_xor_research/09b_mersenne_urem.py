"""Cleaner Mersenne attack using Z3 URem (unsigned remainder) directly.

Z3 supports URem on BitVec natively. Simpler than hand-rolled reduction.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT, URem


def attack_mersenne_urem(out_seq, p_bits, timeout_s=600):
    K = len(out_seq)
    p = p_bits
    M = (1 << p) - 1
    # Use 2p+2 bit BitVec to safely represent a*s + c without overflow
    W = max(2 * p + 2, 32)

    s = Solver()
    s.set("timeout", timeout_s * 1000)

    a1 = BitVec("a1", W); c1 = BitVec("c1", W)
    a2 = BitVec("a2", W); c2 = BitVec("c2", W)
    s1 = [BitVec(f"s1_{k}", W) for k in range(K + 1)]
    s2 = [BitVec(f"s2_{k}", W) for k in range(K + 1)]

    M_bv = BitVecVal(M, W)
    for v in [a1, c1, a2, c2] + s1 + s2:
        s.add(ULT(v, M_bv))
    s.add(ULT(BitVecVal(0, W), a1))
    s.add(ULT(a1, a2))
    s.add((a1 & 1) == 1); s.add((a2 & 1) == 1)

    for k in range(K):
        s.add(s1[k + 1] == URem(a1 * s1[k] + c1, M_bv))
        s.add(s2[k + 1] == URem(a2 * s2[k] + c2, M_bv))
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


# Sweep p = 7, 13, 17, 23, 31
print(f"{'p':>3s}  {'m':>14s}  {'K':>4s}  {'status':>7s}  {'elapsed':>10s}  {'observed':>9s}  {'future':>7s}")
print("-" * 70)

configs = [
    (7,  [(5, 11, 13), (17, 7, 19)],   24),
    (13, [(43, 11, 137), (89, 13, 211)], 24),
    (17, [(43213, 12345, 1234), (28657, 1, 5678)], 28),
    (23, [(1103515245 % ((1<<23)-1) | 1, 12345, 1234),
          (22695477 % ((1<<23)-1) | 1, 1, 5678)], 32),
    (31, [(1103515245, 12345, 1234), (22695477, 1, 5678)], 36),
]

for p, lcgs, K in configs:
    M = (1 << p) - 1
    # Force a's odd, sort
    lcgs = [(a | 1, c, s) for (a, c, s) in lcgs]
    lcgs.sort(key=lambda t: t[0])
    a1, c1, s1 = lcgs[0]
    a2, c2, s2 = lcgs[1]
    n_total = K + 10
    full = gen_xor_mersenne(s1, s2, a1, c1, a2, c2, p, n_total)
    observed = full[:K]; future_truth = full[K:]
    print(f"{p:>3d}  {M:>14d}  {K:>4d}  ", end="", flush=True)
    res, elapsed, status = attack_mersenne_urem(observed, p, timeout_s=600)
    if res is None:
        print(f"{status:>7s}  {elapsed:>9.2f}s  —  —")
        continue
    pred = gen_xor_mersenne(res["s1_0"], res["s2_0"], res["a1"], res["c1"],
                              res["a2"], res["c2"], p, n_total)
    obs_match = pred[:K] == observed
    fut_match = pred[K:] == future_truth
    print(f"{status:>7s}  {elapsed:>9.2f}s  {'✓' if obs_match else '✗':>9s}  {'✓ FULL' if fut_match else '✗':>7s}")
    if not fut_match and obs_match:
        print(f"     (recovered: a1={res['a1']}, c1={res['c1']}, s1={res['s1_0']}, "
              f"a2={res['a2']}, c2={res['c2']}, s2={res['s2_0']})")
