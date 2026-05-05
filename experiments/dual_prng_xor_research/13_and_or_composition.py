"""Z3 attack on dual-LCG AND and OR compositions.

Round out the taxonomy: AND, OR are the remaining non-linear-over-Z/m
compositions tested in script 02. Both failed Hankel-det-gcd. Hypothesis:
they fall to Z3 BitVec too, completing the picture that the SMT-BitVec
attack is universal for the non-linear bitwise composition class.

Note: AND and OR are LOSSY operations (output entropy is < input entropy).
This may make recovery harder than XOR (which preserves entropy modulo
factorization-ambiguity).
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT


def attack(out_seq, op, N, timeout_s=300):
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
        if op == "and":
            s.add(s1[k + 1] & s2[k + 1] == BitVecVal(out_seq[k], N))
        elif op == "or":
            s.add(s1[k + 1] | s2[k + 1] == BitVecVal(out_seq[k], N))
        else:
            raise ValueError(op)
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


def gen(seed1, seed2, a1, c1, a2, c2, op, N, n):
    M = 1 << N
    s1, s2 = seed1, seed2
    out = []
    for _ in range(n):
        s1 = (a1 * s1 + c1) % M
        s2 = (a2 * s2 + c2) % M
        if op == "and":
            out.append(s1 & s2)
        elif op == "or":
            out.append(s1 | s2)
    return out


print(f"{'op':>5s}  {'N':>3s}  {'K':>4s}  {'status':>7s}  {'elapsed':>10s}  {'observed':>9s}  {'future':>7s}")
print("-" * 60)

CONFIGS = [
    # (op, N, K)
    ("and", 16, 32),
    ("and", 24, 40),
    ("and", 32, 48),
    ("or",  16, 32),
    ("or",  24, 40),
    ("or",  32, 48),
]

for op, N, K in CONFIGS:
    a1 = (1103515245 & ((1<<N)-1)) | 1
    a2 = (22695477 & ((1<<N)-1)) | 1
    if a1 > a2: a1, a2 = a2, a1
    c1 = 12345 & ((1<<N)-1)
    c2 = 1
    s1_0 = 1234; s2_0 = 5678
    n_total = K + 10
    full = gen(s1_0, s2_0, a1, c1, a2, c2, op, N, n_total)
    observed = full[:K]; future_truth = full[K:]
    print(f"{op:>5s}  {N:>3d}  {K:>4d}  ", end="", flush=True)
    timeout = 60 if N <= 16 else (180 if N <= 24 else 600)
    res, elapsed, status = attack(observed, op, N, timeout_s=timeout)
    if res is None:
        print(f"{status:>7s}  {elapsed:>9.2f}s  —  —")
        continue
    pred = gen(res["s1_0"], res["s2_0"], res["a1"], res["c1"],
               res["a2"], res["c2"], op, N, n_total)
    obs_match = pred[:K] == observed
    fut_match = pred[K:] == future_truth
    print(f"{status:>7s}  {elapsed:>9.2f}s  {'✓' if obs_match else '✗':>9s}  {'✓ FULL' if fut_match else '✗ ambig':>7s}")
