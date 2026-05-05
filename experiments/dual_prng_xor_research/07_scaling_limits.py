"""How far does Z3 scale? Sweep N = 32, 40, 48, 56, 64. Find the breakpoint.

Also: try Mersenne-prime moduli (2^31 - 1, 2^61 - 1) by adding modular-reduction
constraints. This is the "real" LCG case — most published LCGs use Mersenne primes.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, unsat, ULT


def attack_z3_pow2(out_seq, N, timeout_s=120):
    K = len(out_seq)
    s = Solver(); s.set("timeout", timeout_s * 1000)
    a1 = BitVec("a1", N); c1 = BitVec("c1", N)
    a2 = BitVec("a2", N); c2 = BitVec("c2", N)
    s1 = [BitVec(f"s1_{k}", N) for k in range(K + 1)]
    s2 = [BitVec(f"s2_{k}", N) for k in range(K + 1)]
    for k in range(K):
        s.add(s1[k + 1] == a1 * s1[k] + c1)
        s.add(s2[k + 1] == a2 * s2[k] + c2)
        s.add(s1[k + 1] ^ s2[k + 1] == BitVecVal(out_seq[k], N))
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


def gen_xor_pow2(seed1, seed2, a1, c1, a2, c2, N, n):
    M = 1 << N
    s1, s2 = seed1, seed2
    out = []
    for _ in range(n):
        s1 = (a1 * s1 + c1) % M
        s2 = (a2 * s2 + c2) % M
        out.append(s1 ^ s2)
    return out


# Common canonical LCG params at various widths
def lcg_params_at_n(N):
    """Return (a1, c1, seed1, a2, c2, seed2) for a given N."""
    # Truncate well-known LCG constants to N bits, force odd
    a1 = (1103515245) & ((1 << N) - 1) | 1
    a2 = (22695477) & ((1 << N) - 1) | 1
    c1 = 12345
    c2 = 1
    seed1 = 1234
    seed2 = 5678
    if N >= 30:  # use bigger constants for bigger N to avoid trivial degenerate behavior
        a1 = (6364136223846793005) & ((1 << N) - 1) | 1
        a2 = (1442695040888963407) & ((1 << N) - 1) | 1
    return a1, c1, seed1, a2, c2, seed2


def verify_predictions(out_observed, future_truth, recovered, N):
    """Check recovered params reproduce observed AND predict future."""
    total_n = len(out_observed) + len(future_truth)
    pred = gen_xor_pow2(recovered["s1_0"], recovered["s2_0"],
                       recovered["a1"], recovered["c1"],
                       recovered["a2"], recovered["c2"], N, total_n)
    K = len(out_observed)
    return (pred[:K] == out_observed, pred[K:] == future_truth)


print(f"{'N':>3s}  {'K':>4s}  {'status':>7s}  {'elapsed':>9s}  {'observed-match':>14s}  {'future-match'}")
print("-" * 65)

for N in [32, 40, 48, 56, 64]:
    a1, c1, s1, a2, c2, s2 = lcg_params_at_n(N)
    if a1 >= a2:
        a1, a2 = a2, a1
        c1, c2 = c2, c1
        s1, s2 = s2, s1
    K = 32 if N <= 48 else 48  # bigger N needs more obs for unique recovery
    n_total = K + 10
    full = gen_xor_pow2(s1, s2, a1, c1, a2, c2, N, n_total)
    observed = full[:K]; future_truth = full[K:]
    print(f"{N:>3d}  {K:>4d}  ", end="", flush=True)
    res, elapsed, status = attack_z3_pow2(observed, N, timeout_s=300)
    if res is None:
        print(f"{status:>7s}  {elapsed:>9.2f}s  —  —")
        continue
    obs_match, fut_match = verify_predictions(observed, future_truth, res, N)
    print(f"{status:>7s}  {elapsed:>9.2f}s  {'✓' if obs_match else '✗':>14s}  {'✓ FULL CRACK' if fut_match else '✗ ambiguous'}")
