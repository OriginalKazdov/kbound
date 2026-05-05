"""Verify Z3-recovered factorizations are operationally equivalent.

Even if Z3 finds a "mismatched" solution (different parameters from ground truth),
if it reproduces the observed XOR outputs AND predicts future ones correctly,
that's a successful operational state recovery — same outcome as the truth.

This script:
  1. Runs the Z3 attack to recover SOME (a1, c1, s1_0, a2, c2, s2_0)
  2. Generates predictions K+1, K+2, ..., K+10 from the recovered params
  3. Compares against the true continuation
  4. If matches: "operational recovery" succeeded — equivalence class found
  5. If diverges: ambiguity is genuinely problematic for prediction
"""
from __future__ import annotations

import sys
import time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, unsat, ULT


def attack_z3(out_seq, N, timeout_s=60):
    K = len(out_seq)
    s = Solver()
    s.set("timeout", timeout_s * 1000)

    a1 = BitVec("a1", N)
    c1 = BitVec("c1", N)
    a2 = BitVec("a2", N)
    c2 = BitVec("c2", N)
    s1 = [BitVec(f"s1_{k}", N) for k in range(K + 1)]
    s2 = [BitVec(f"s2_{k}", N) for k in range(K + 1)]
    for k in range(K):
        s.add(s1[k + 1] == a1 * s1[k] + c1)
        s.add(s2[k + 1] == a2 * s2[k] + c2)
    for k in range(K):
        s.add(s1[k + 1] ^ s2[k + 1] == BitVecVal(out_seq[k], N))
    s.add(ULT(a1, a2))
    s.add((a1 & 1) == 1)
    s.add((a2 & 1) == 1)

    t0 = time.time()
    res = s.check()
    elapsed = time.time() - t0
    if res != sat:
        return None, elapsed
    m = s.model()
    return {
        "a1": m[a1].as_long(), "c1": m[c1].as_long(), "s1_0": m[s1[0]].as_long(),
        "a2": m[a2].as_long(), "c2": m[c2].as_long(), "s2_0": m[s2[0]].as_long(),
    }, elapsed


def gen_xor_seq(seed1, seed2, a1, c1, a2, c2, N, n):
    M = 1 << N
    s1, s2 = seed1, seed2
    out = []
    for _ in range(n):
        s1 = (a1 * s1 + c1) % M
        s2 = (a2 * s2 + c2) % M
        out.append(s1 ^ s2)
    return out


# Test config: 32-bit, K=32 observations, predict next 10
N = 32
A1, C1, SEED1 = 1103515245, 12345, 1234
A2, C2, SEED2 = 22695477, 1, 5678
M = 1 << N

# Generate K=32 observed + 10 future for verification
total = gen_xor_seq(SEED1, SEED2, A1, C1, A2, C2, N, 42)
observed = total[:32]
future_truth = total[32:42]

print(f"True params: LCG1=(a={A1}, c={C1}, seed={SEED1}), LCG2=(a={A2}, c={C2}, seed={SEED2})")
print(f"Observed (K=32): {observed[:4]}...")
print(f"Future truth (k=32..41): {future_truth}")

# Attack
print("\n--- Z3 attack (K=32, N=32) ---")
res, elapsed = attack_z3(observed, N, timeout_s=120)
if res is None:
    print(f"  Z3 failed in {elapsed:.2f}s")
    sys.exit()

print(f"  Z3 found a solution in {elapsed:.2f}s:")
print(f"    LCG1: a={res['a1']}, c={res['c1']}, seed={res['s1_0']}")
print(f"    LCG2: a={res['a2']}, c={res['c2']}, seed={res['s2_0']}")

# Predict from recovered params
predicted = gen_xor_seq(res["s1_0"], res["s2_0"],
                         res["a1"], res["c1"],
                         res["a2"], res["c2"], N, 42)
predicted_observed = predicted[:32]
predicted_future = predicted[32:42]

print(f"\n  Recovery sanity (first 4 outputs):")
print(f"    Observed:  {observed[:4]}")
print(f"    Predicted: {predicted_observed[:4]}")
match_observed = predicted_observed == observed
print(f"    Match observed: {match_observed}")

print(f"\n  PREDICTION on held-out (k=32..41):")
print(f"    Future truth:     {future_truth}")
print(f"    Predicted future: {predicted_future}")
match_future = predicted_future == future_truth
print(f"    Match future: {match_future}")

print()
if match_observed and match_future:
    print("=" * 60)
    print("  ✅ OPERATIONAL STATE RECOVERY: ✅✅✅")
    print("  Z3 found a parameter set that — despite differing")
    print("  from ground truth — reproduces ALL observed outputs")
    print("  AND PREDICTS HELD-OUT FUTURE outputs correctly.")
    print("  This is a fully successful attack on 2-LCG XOR at 32 bits.")
    print("=" * 60)
elif match_observed and not match_future:
    print("=" * 60)
    print("  ⚠️  Z3 finds an OBSERVATION-CONSISTENT factorization")
    print("  that diverges on prediction. Need additional constraints")
    print("  (longer K, or canonical-c bound) to break the ambiguity.")
    print("=" * 60)
else:
    print("=" * 60)
    print("  ❌ Recovery failed even on observed support — bug somewhere.")
    print("=" * 60)
