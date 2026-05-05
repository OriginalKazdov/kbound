"""Z3 / SMT attack on dual-LCG XOR.

Z3 supports BitVec theory which natively expresses XOR + modular arithmetic.
Express the constraints:
    s1_k = (a1 * s1_{k-1} + c1) mod 2^N
    s2_k = (a2 * s2_{k-1} + c2) mod 2^N
    out_k = s1_k XOR s2_k

Then ask Z3 to find (a1, c1, s1_0, a2, c2, s2_0) satisfying all observations.

For Z3 to be efficient, we cast Z/m as Z/2^N (BitVec arithmetic). When the
true modulus is a Mersenne prime m = 2^31 - 1, we need extra constraints
to ensure values stay < m (i.e. modular reduction by Mersenne). For now
test the easier case m = 2^N first (e.g. m = 2^16 or 2^32).
"""
from __future__ import annotations

import sys
import time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, unsat, ULT, And


def attack_dual_lcg_xor_pow2(out_seq: list[int], N: int, timeout_s: int = 30) -> dict | None:
    """Attack 2-LCG XOR composition over Z/2^N.

    out_seq: K consecutive XOR outputs (each fits in N bits).
    N: bit-width of the modulus (m = 2^N).
    Returns dict with recovered params, or None if no solution found.
    """
    K = len(out_seq)
    if K < 4:
        return None

    s = Solver()
    s.set("timeout", timeout_s * 1000)

    # Unknowns
    a1 = BitVec("a1", N)
    c1 = BitVec("c1", N)
    a2 = BitVec("a2", N)
    c2 = BitVec("c2", N)

    # State sequences (s1_0..s1_K) and (s2_0..s2_K)
    # We model "state at step k AFTER applying LCG", matching how outputs are emitted.
    s1 = [BitVec(f"s1_{k}", N) for k in range(K + 1)]
    s2 = [BitVec(f"s2_{k}", N) for k in range(K + 1)]

    # LCG transitions
    for k in range(K):
        s.add(s1[k + 1] == a1 * s1[k] + c1)
        s.add(s2[k + 1] == a2 * s2[k] + c2)

    # Output constraints: out_k = s1[k+1] XOR s2[k+1] (the k-th output is the
    # state after the k-th transition, since gen_dual_xor advances first then records)
    for k in range(K):
        s.add(s1[k + 1] ^ s2[k + 1] == BitVecVal(out_seq[k], N))

    # Break swap-symmetry: WLOG a1 < a2 (lexicographic on the parameter pair)
    s.add(ULT(a1, a2))

    # Force odd a's (LCG full-period over Z/2^N requires gcd(a, m)=1, so a is odd)
    # This is a sanity constraint that prunes the search significantly.
    s.add((a1 & 1) == 1)
    s.add((a2 & 1) == 1)

    t0 = time.time()
    res = s.check()
    elapsed = time.time() - t0

    if res != sat:
        return {"status": str(res), "elapsed_s": elapsed}

    m = s.model()
    return {
        "status": "sat",
        "elapsed_s": elapsed,
        "a1": m[a1].as_long(),
        "c1": m[c1].as_long(),
        "a2": m[a2].as_long(),
        "c2": m[c2].as_long(),
        "s1_0": m[s1[0]].as_long(),
        "s2_0": m[s2[0]].as_long(),
    }


def lcg_step(s, a, c, m):
    return (a * s + c) % m


def gen_dual_xor_pow2(seed1, seed2, a1, c1, a2, c2, N, n):
    m = 1 << N
    s1, s2 = seed1, seed2
    out = []
    for _ in range(n):
        s1 = lcg_step(s1, a1, c1, m)
        s2 = lcg_step(s2, a2, c2, m)
        out.append(s1 ^ s2)
    return out


# ===== Sweep N = 8, 12, 16, 24 (modulus 2^N) =====
# Use canonical LCG params at the right size

print(f"{'N':>3s}  {'m':>12s}  {'K':>4s}  {'status':>6s}  {'elapsed (s)':>12s}  {'recovered? (up to swap)'}")
print("-" * 85)

# Configs: (N, a1, c1, seed1, a2, c2, seed2, K)
configs = [
    # Small bit-width for sanity
    (8,   17,    7,   3,   29,    5,   11,  16),
    (12,  1103, 5,    37,  757,   23,  101, 16),
    (16,  21845,  1,  4321, 25173,  13849, 6789,  20),
    (16,  1103515245 & 0xFFFF, 12345 & 0xFFFF, 1234, 22695477 & 0xFFFF, 1, 5678, 24),
    (24,  1103515245 & 0xFFFFFF, 12345, 1234, 22695477 & 0xFFFFFF, 1, 5678, 32),
    (32,  1103515245, 12345, 1234, 22695477, 1, 5678, 32),
]

for cfg in configs:
    N, a1, c1, seed1, a2, c2, seed2, K = cfg
    # Force odd a (for full period under 2^N) — adjust if needed
    if a1 % 2 == 0: a1 |= 1
    if a2 % 2 == 0: a2 |= 1
    out = gen_dual_xor_pow2(seed1, seed2, a1, c1, a2, c2, N, K)
    print(f"{N:>3d}  {1 << N:>12d}  {K:>4d}  ", end="", flush=True)
    res = attack_dual_lcg_xor_pow2(out, N, timeout_s=60)
    elapsed = res.get("elapsed_s", float("nan"))
    status = res.get("status", "?")
    if status == "sat":
        # Check correctness up to swap
        rec = ((res["a1"], res["c1"], res["s1_0"]), (res["a2"], res["c2"], res["s2_0"]))
        # Truth as sorted pair (since we asked Z3 a1 < a2, the canonical order is (lower, higher))
        truth_pairs = sorted([(a1, c1, seed1), (a2, c2, seed2)])
        rec_pairs = sorted([rec[0], rec[1]])
        ok = "✓" if rec_pairs == truth_pairs else "MISMATCH"
        print(f"{status:>6s}  {elapsed:>12.3f}  {ok}  rec={rec_pairs}, truth={truth_pairs}")
    else:
        print(f"{status:>6s}  {elapsed:>12.3f}  —")
