"""MRG32k3a state recovery via Z3 SMT (the L'Ecuyer combined MRG).

MRG32k3a (L'Ecuyer 1999) is the default RNG in:
  - NVIDIA cuRAND (default for `curandStateMRG32k3a`)
  - MATLAB (rng default in some versions)
  - R (one of the available kinds)
  - Mathematica (RandomReal default in some versions)
  - Wide use in scientific simulation, financial Monte Carlo, etc.

Construction (two coupled MRG of order 3):

    s1[n] = (1403580 * s1[n-2] - 810728 * s1[n-3]) mod m1   (m1 = 2^32 - 209 = 4294967087)
    s2[n] = (527612  * s2[n-1] - 1370589 * s2[n-3]) mod m2  (m2 = 2^32 - 22853 = 4294944443)
    output[n] = (s1[n] - s2[n]) mod m1

Martinez (CT-RSA 2022, eprint 2021/1204) cracked this via lattice methods.
Question: does our SMT-BitVec attack also work? Methodology contribution if yes.

The challenge: m1, m2 are NOT powers of 2 — they're "near-Mersenne" primes.
Z3 BitVec doesn't natively handle non-pow-2 modular reduction efficiently.
We try the carry-bit encoding with a 64-bit working width.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT, If


# Constants
A1_2 = 1403580
A1_3 = -810728
A2_1 = 527612
A2_3 = -1370589
M1 = (1 << 32) - 209    # 4294967087
M2 = (1 << 32) - 22853  # 4294944443


def step_mrg(s1_history, s2_history):
    """Advance both MRGs by one step. s_history = [s_n-1, s_n-2, s_n-3]."""
    new_s1 = (A1_2 * s1_history[1] + A1_3 * s1_history[2]) % M1
    new_s2 = (A2_1 * s2_history[0] + A2_3 * s2_history[2]) % M2
    output = (new_s1 - new_s2) % M1
    return new_s1, new_s2, output


def gen_mrg32k3a(s1_init, s2_init, n):
    """Generate n outputs starting from initial 3-word states."""
    s1_h = list(s1_init)  # [s1_-1, s1_-2, s1_-3]
    s2_h = list(s2_init)
    outs = []
    for _ in range(n):
        new_s1, new_s2, out = step_mrg(s1_h, s2_h)
        outs.append(out)
        s1_h = [new_s1, s1_h[0], s1_h[1]]
        s2_h = [new_s2, s2_h[0], s2_h[1]]
    return outs


def attack_mrg32k3a(out_seq, timeout_s=600):
    """SMT attack: 6 unknowns (3 initial s1, 3 initial s2), K equations.

    Use 64-bit BitVec to comfortably hold a*s + c products without overflow,
    encode mod m as `raw == s_next + m*q` with q a quotient bitvec.
    """
    K = len(out_seq)
    W = 64

    s = Solver()
    s.set("timeout", timeout_s * 1000)

    # 3 initial state words for each MRG (the seed)
    s1_init = [BitVec(f"s1i_{i}", W) for i in range(3)]
    s2_init = [BitVec(f"s2i_{i}", W) for i in range(3)]
    # State sequences: s1[n] = nth NEW state. Index: 0..K-1 are computed.
    s1_seq = [BitVec(f"s1_{k}", W) for k in range(K)]
    s2_seq = [BitVec(f"s2_{k}", W) for k in range(K)]
    # Quotients for modular reduction
    q1 = [BitVec(f"q1_{k}", W) for k in range(K)]
    q2 = [BitVec(f"q2_{k}", W) for k in range(K)]
    qo = [BitVec(f"qo_{k}", W) for k in range(K)]

    M1_bv = BitVecVal(M1, W)
    M2_bv = BitVecVal(M2, W)

    # Range constraints
    for v in s1_init: s.add(ULT(v, M1_bv))
    for v in s2_init: s.add(ULT(v, M2_bv))
    for v in s1_seq:  s.add(ULT(v, M1_bv))
    for v in s2_seq:  s.add(ULT(v, M2_bv))

    # MRG transitions over multiple "lookback" indices
    # For step n, we need s1_history = [s1_{n-1}, s1_{n-2}, s1_{n-3}]
    # We pre-pend s1_init so that s1_history[k=0] = [s1_init[2], s1_init[1], s1_init[0]] interpreted as
    # [s1_-1=s1_init[2], s1_-2=s1_init[1], s1_-3=s1_init[0]].
    def s1_at(k):
        # k can be -3, -2, -1 (initial), or 0, 1, ..., K-1 (computed)
        if k == -1:  return s1_init[2]
        if k == -2:  return s1_init[1]
        if k == -3:  return s1_init[0]
        return s1_seq[k]

    def s2_at(k):
        if k == -1:  return s2_init[2]
        if k == -2:  return s2_init[1]
        if k == -3:  return s2_init[0]
        return s2_seq[k]

    # Note: A1_3 = -810728 is negative; over Z/m1 that's m1 - 810728
    A1_2_bv = BitVecVal(A1_2 % M1, W)
    A1_3_bv = BitVecVal((-A1_3) % M1, W)  # use positive coefficient: -A1_3 = 810728
    A2_1_bv = BitVecVal(A2_1 % M2, W)
    A2_3_bv = BitVecVal((-A2_3) % M2, W)

    # Encode: s1[n] = (A1_2 * s1[n-2] - A1_3 * s1[n-3]) mod m1
    # Equivalently: s1[n] + A1_3 * s1[n-3] === A1_2 * s1[n-2] (mod m1)
    # Or simpler: raw = A1_2 * s1[n-2] + (m1 - A1_3) * s1[n-3]; s1[n] = raw - m1*q
    for k in range(K):
        # raw1 = A1_2 * s1[k-2] + (-A1_3 mod m1) * s1[k-3], where (-A1_3) = 810728
        raw1 = A1_2_bv * s1_at(k - 2) - BitVecVal(810728, W) * s1_at(k - 3)
        # s1[k] = raw1 mod m1, encoded as raw1 == s1[k] + m1 * q1[k]
        # But raw1 may be negative-looking in 64-bit (subtraction). Quotient may be 0..A1_2.
        s.add(ULT(q1[k], BitVecVal(A1_2 + 2, W)))
        s.add(raw1 == s1_seq[k] + M1_bv * q1[k])

        raw2 = A2_1_bv * s2_at(k - 1) - BitVecVal(1370589, W) * s2_at(k - 3)
        s.add(ULT(q2[k], BitVecVal(A2_1 + 2, W)))
        s.add(raw2 == s2_seq[k] + M2_bv * q2[k])

        # Output: out[k] = (s1[k] - s2[k]) mod m1
        # = s1[k] - s2[k] + m1 * (carry, 0 or 1)
        s.add(ULT(qo[k], BitVecVal(2, W)))
        s.add(s1_seq[k] - s2_seq[k] + M1_bv * qo[k] == BitVecVal(out_seq[k], W))

    t0 = time.time()
    res = s.check()
    elapsed = time.time() - t0
    if res != sat:
        return {"status": str(res), "elapsed_s": elapsed}
    m = s.model()
    return {
        "status": "sat",
        "elapsed_s": elapsed,
        "s1_init": tuple(m[s1_init[i]].as_long() for i in range(3)),
        "s2_init": tuple(m[s2_init[i]].as_long() for i in range(3)),
    }


# Test
S1_INIT = (12345, 67890, 11111)  # interpreted as (s1_-3, s1_-2, s1_-1)
S2_INIT = (22222, 33333, 44444)

print(f"True state:")
print(f"  s1_init = {S1_INIT}")
print(f"  s2_init = {S2_INIT}")
print(f"  m1 = {M1}, m2 = {M2}")

for K in [6, 8, 12, 16, 24]:
    outs = gen_mrg32k3a(S1_INIT, S2_INIT, K + 5)
    observed = outs[:K]
    future = outs[K:K + 5]
    print(f"\n=== K={K} observations ===")
    print(f"  obs[:3] = {observed[:3]}")
    res = attack_mrg32k3a(observed, timeout_s=300 if K <= 12 else 900)
    if res["status"] != "sat":
        print(f"  status: {res['status']}, elapsed: {res['elapsed_s']:.2f}s")
        continue
    print(f"  recovered s1_init = {res['s1_init']}")
    print(f"  recovered s2_init = {res['s2_init']}")
    print(f"  elapsed: {res['elapsed_s']:.2f}s")
    pred = gen_mrg32k3a(res["s1_init"], res["s2_init"], K + 5)
    obs_match = pred[:K] == observed
    fut_match = pred[K:K + 5] == future
    print(f"  observed: {'✓' if obs_match else '✗'}, future: {'✓ FULL CRACK' if fut_match else '✗ ambiguous'}")
    if obs_match and fut_match:
        print(f"\n  Minimum K for full crack: {K}")
        break
