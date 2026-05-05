"""Z3 attack on dual-LCG XOR with Mersenne-prime modulus.

Real LCGs use Mersenne-prime moduli — m = 2^31 - 1 (BSD random, glibc TYPE_0,
old Numerical Recipes), m = 2^61 - 1 (high-quality MMIX-style). BitVec doesn't
natively model Mersenne-mod arithmetic; we encode it via:

    For x in [0, 2 * m):  x mod m = (x & m) + (x >> bit_width)
    For x in [0, m^2):     iterate the above 1-2 times until result < m

Encoding choice for Z3:
  - Use BitVec of width 2N (so a*s + c fits without overflow before reduction)
  - Add explicit constraints: result < m AND result = (intermediate) mod m
  - The mod-m operation is encoded as a function applied at each LCG step

Alternative: use Z3 Int theory directly with `(x mod m)` constraints.
Int is more general but slower than BitVec. We test both.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import (BitVec, BitVecVal, Solver, sat, ULT,
                Int, IntVal, Function, Distinct, And, Or)


# ============================================================
# Approach 1: Z3 Int theory (more general, possibly slower)
# ============================================================

def attack_int(out_seq, m, bit_width, timeout_s=300):
    """Use Z3 Int theory with explicit `mod m` constraints.

    bit_width: needed only for casting `XOR` — Int doesn't have native XOR,
    but we can encode it via bitwise constraints for fixed bit-width values.
    """
    K = len(out_seq)
    s = Solver()
    s.set("timeout", timeout_s * 1000)

    a1 = Int("a1"); c1 = Int("c1")
    a2 = Int("a2"); c2 = Int("c2")
    s1 = [Int(f"s1_{k}") for k in range(K + 1)]
    s2 = [Int(f"s2_{k}") for k in range(K + 1)]

    # Range constraints
    M = IntVal(m)
    for v in [a1, c1, a2, c2] + s1 + s2:
        s.add(v >= 0, v < M)
    s.add(a1 > 0, a2 > 0)
    s.add(a1 < a2)  # break swap symmetry
    s.add(a1 % 2 == 1, a2 % 2 == 1)  # full-period needs odd a (proxy)

    # LCG transitions modulo m
    for k in range(K):
        s.add(s1[k + 1] == (a1 * s1[k] + c1) % M)
        s.add(s2[k + 1] == (a2 * s2[k] + c2) % M)

    # XOR constraint via BitVec coercion: extract bits
    # Z3 supports converting Int to BitVec, then XOR, then comparing.
    # Cleanest way: declare a bv version of each state and link to int.
    # But this is fragile. Use a BitVec-based attack instead (approach 2).
    return None, 0.0, "INT_NOT_IMPLEMENTED"  # Skip — go straight to BitVec


# ============================================================
# Approach 2: Z3 BitVec with Mersenne reduction encoded
# ============================================================

def attack_mersenne_bv(out_seq, p_bits, timeout_s=300):
    """BitVec-based attack on dual-LCG XOR with Mersenne modulus m = 2^p_bits - 1.

    The state lives in [0, m), so we use BitVec of width p_bits. The product
    a * s might overflow p_bits, so we use 2*p_bits BitVec for intermediate.

    Mersenne reduction: x mod (2^p - 1) = (x & m) + (x >> p), iterate twice.
    """
    K = len(out_seq)
    p = p_bits
    M = (1 << p) - 1  # Mersenne prime / pseudoprime

    # Use 2p-bit BitVec for arithmetic, p-bit results
    W = 2 * p  # working width

    s = Solver()
    s.set("timeout", timeout_s * 1000)

    def mersenne_reduce(x_bv, w):
        """Encode x mod (2^p - 1) as constraint-friendly BitVec ops."""
        # x mod m = (x & m) + (x >> p), iterate
        from z3 import LShR, Concat, Extract, ZeroExt, BV2Int, simplify
        m_bv = BitVecVal(M, w)
        # First reduction
        low = x_bv & m_bv
        high = LShR(x_bv, p)
        r1 = low + high
        # Second reduction (in case r1 >= m)
        low2 = r1 & m_bv
        high2 = LShR(r1, p)
        r2 = low2 + high2
        # If r2 == m, reduce to 0 (Mersenne special case: m mod m = 0)
        from z3 import If
        result = If(r2 == m_bv, BitVecVal(0, w), r2)
        return result

    a1 = BitVec("a1", W); c1 = BitVec("c1", W)
    a2 = BitVec("a2", W); c2 = BitVec("c2", W)
    s1 = [BitVec(f"s1_{k}", W) for k in range(K + 1)]
    s2 = [BitVec(f"s2_{k}", W) for k in range(K + 1)]

    M_bv = BitVecVal(M, W)
    # All values < m
    for v in [a1, c1, a2, c2] + s1 + s2:
        s.add(ULT(v, M_bv))
    s.add(ULT(BitVecVal(0, W), a1))
    s.add(ULT(a1, a2))  # break swap
    s.add((a1 & 1) == 1)
    s.add((a2 & 1) == 1)

    # LCG step: s_next = (a * s + c) mod m
    for k in range(K):
        prod1 = a1 * s1[k] + c1  # may overflow; that's OK in 2p bitwidth as long as p < W
        prod2 = a2 * s2[k] + c2
        s.add(s1[k + 1] == mersenne_reduce(prod1, W))
        s.add(s2[k + 1] == mersenne_reduce(prod2, W))

    # Output: out_k = s1[k+1] XOR s2[k+1] (lower p bits XOR; upper bits 0 because reduced)
    for k in range(K):
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


# Test 1: m = 2^7 - 1 = 127 (very small Mersenne, sanity check)
print("=" * 60)
print("Test 1: m = 2^7 - 1 = 127 (sanity)")
print("=" * 60)
p = 7
M = (1 << p) - 1
A1, C1, S1 = 5, 11, 13
A2, C2, S2 = 17, 7, 19
total = gen_xor_mersenne(S1, S2, A1, C1, A2, C2, p, 32)
observed = total[:24]; future_truth = total[24:]
print(f"  truth: a1={A1}, c1={C1}, s1={S1}, a2={A2}, c2={C2}, s2={S2}")
res, elapsed, status = attack_mersenne_bv(observed, p, timeout_s=60)
if res:
    pred = gen_xor_mersenne(res["s1_0"], res["s2_0"], res["a1"], res["c1"],
                              res["a2"], res["c2"], p, len(total))
    obs_match = pred[:24] == observed
    fut_match = pred[24:] == future_truth
    print(f"  recovered: a1={res['a1']}, c1={res['c1']}, s1={res['s1_0']}, "
          f"a2={res['a2']}, c2={res['c2']}, s2={res['s2_0']}")
    print(f"  elapsed: {elapsed:.2f}s, observed: {'✓' if obs_match else '✗'}, "
          f"future: {'✓' if fut_match else '✗'}")
else:
    print(f"  status: {status}, elapsed: {elapsed:.2f}s")

# Test 2: m = 2^17 - 1 = 131071
print("\n" + "=" * 60)
print("Test 2: m = 2^17 - 1 = 131071")
print("=" * 60)
p = 17
M = (1 << p) - 1
A1, C1, S1 = 1103515245 % M, 12345, 1234
A2, C2, S2 = 22695477 % M, 1, 5678
if A1 % 2 == 0: A1 |= 1
if A2 % 2 == 0: A2 |= 1
total = gen_xor_mersenne(S1, S2, A1, C1, A2, C2, p, 36)
observed = total[:28]; future_truth = total[28:]
print(f"  truth: a1={A1}, c1={C1}, s1={S1}, a2={A2}, c2={C2}, s2={S2}")
res, elapsed, status = attack_mersenne_bv(observed, p, timeout_s=300)
if res:
    pred = gen_xor_mersenne(res["s1_0"], res["s2_0"], res["a1"], res["c1"],
                              res["a2"], res["c2"], p, len(total))
    obs_match = pred[:28] == observed
    fut_match = pred[28:] == future_truth
    print(f"  recovered: a1={res['a1']}, c1={res['c1']}, s1={res['s1_0']}, "
          f"a2={res['a2']}, c2={res['c2']}, s2={res['s2_0']}")
    print(f"  elapsed: {elapsed:.2f}s, observed: {'✓' if obs_match else '✗'}, "
          f"future: {'✓' if fut_match else '✗'}")
else:
    print(f"  status: {status}, elapsed: {elapsed:.2f}s")

# Test 3: m = 2^31 - 1 = 2147483647 (the BIG one — real LCG modulus)
print("\n" + "=" * 60)
print("Test 3: m = 2^31 - 1 = 2147483647 (BSD random / glibc TYPE_0 modulus)")
print("=" * 60)
p = 31
M = (1 << p) - 1
A1, C1, S1 = 1103515245 % M, 12345, 1234
A2, C2, S2 = 22695477 % M, 1, 5678
if A1 % 2 == 0: A1 |= 1
if A2 % 2 == 0: A2 |= 1
total = gen_xor_mersenne(S1, S2, A1, C1, A2, C2, p, 42)
observed = total[:32]; future_truth = total[32:]
print(f"  truth: a1={A1}, c1={C1}, s1={S1}, a2={A2}, c2={C2}, s2={S2}")
res, elapsed, status = attack_mersenne_bv(observed, p, timeout_s=600)
if res:
    pred = gen_xor_mersenne(res["s1_0"], res["s2_0"], res["a1"], res["c1"],
                              res["a2"], res["c2"], p, len(total))
    obs_match = pred[:32] == observed
    fut_match = pred[32:] == future_truth
    print(f"  recovered: a1={res['a1']}, c1={res['c1']}, s1={res['s1_0']}, "
          f"a2={res['a2']}, c2={res['c2']}, s2={res['s2_0']}")
    print(f"  elapsed: {elapsed:.2f}s, observed: {'✓' if obs_match else '✗'}, "
          f"future: {'✓' if fut_match else '✗'}")
else:
    print(f"  status: {status}, elapsed: {elapsed:.2f}s")
