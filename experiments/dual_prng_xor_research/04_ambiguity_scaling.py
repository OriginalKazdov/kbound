"""How does factorization ambiguity scale with (m, K)?

If ambiguity stays bounded as K grows, recovery is polynomial-bounded
(short-list of candidates, useful for forensics).

If ambiguity collapses to ~2 (truth + swap) as K grows, recovery is
unique up to symmetry — much stronger result.

If ambiguity grows with m polynomially, scalability is feasible to
medium m. If it grows exponentially, only very small m is attackable.
"""
from __future__ import annotations

import sys
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from itertools import product


def lcg_step(s, a, c, m):
    return (a * s + c) % m


def gen_dual_xor(seed1, seed2, a1, c1, a2, c2, m, n):
    s1, s2 = seed1, seed2
    out = []
    for _ in range(n):
        s1 = lcg_step(s1, a1, c1, m)
        s2 = lcg_step(s2, a2, c2, m)
        out.append(s1 ^ s2)
    return out


def is_lcg_seq(seq, m):
    """Check if seq is an LCG over Z/m. Returns (a, c) or None."""
    n = len(seq)
    if n < 4 or any(s >= m or s < 0 for s in seq):
        return None
    diff = [(seq[i + 1] - seq[i]) % m for i in range(n - 1)]
    if diff[0] == 0:
        return None
    from math import gcd
    if gcd(diff[0], m) != 1:
        return None
    # ext gcd inverse
    a_, b_ = diff[0] % m, m
    s_, t_ = 1, 0
    while b_:
        q = a_ // b_
        a_, b_ = b_, a_ - q * b_
        s_, t_ = t_, s_ - q * t_
    inv = s_ % m
    a = (diff[1] * inv) % m
    c = (seq[1] - a * seq[0]) % m
    cur = seq[0]
    for i in range(1, n):
        cur = (a * cur + c) % m
        if cur != seq[i]:
            return None
    return (a, c)


def count_factorizations(out_seq, m):
    """Brute-force enumerate all (s1_0, a1, c1) such that s2 = out XOR s1 is a valid LCG."""
    count = 0
    factorizations = []
    for s1_0 in range(m):
        for a1 in range(1, m):
            for c1 in range(m):
                # Generate s1_seq
                s1 = s1_0
                s1_seq = []
                for _ in range(len(out_seq)):
                    s1 = (a1 * s1 + c1) % m
                    s1_seq.append(s1)
                if any(s >= m for s in s1_seq):
                    continue
                s2_seq = [out_seq[k] ^ s1_seq[k] for k in range(len(out_seq))]
                if any(s >= m for s in s2_seq):
                    continue
                fit = is_lcg_seq(s2_seq, m)
                if fit:
                    count += 1
                    factorizations.append((s1_0, a1, c1, fit[0], fit[1]))
    return count, factorizations


# Sweep small m, varying K
print(f"{'m':>4s}  {'K':>4s}  {'#factorizations':>16s}  {'distinct (a1,c1,a2,c2)':>22s}  {'note'}")
print("-" * 75)

for m in [7, 11, 13, 17, 23]:
    A1, C1, SEED1 = 3, 2, 4 % m
    A2, C2, SEED2 = (5 % m), 1, (7 % m)
    if A1 == 0 or A2 == 0:
        continue
    for K in [8, 16, 32]:
        out = gen_dual_xor(SEED1, SEED2, A1, C1, A2, C2, m, K)
        try:
            n_fact, facts = count_factorizations(out, m)
        except KeyboardInterrupt:
            print("interrupted"); raise
        # Distinct (a1, c1, a2, c2) tuples (parameter-set ambiguity)
        param_sets = set()
        for (s1_0, a1, c1, a2, c2) in facts:
            # Canonicalize: sort (a, c) pair so swap symmetry counts once
            p1 = (a1, c1)
            p2 = (a2, c2)
            param_sets.add(tuple(sorted([p1, p2])))
        note = ""
        if n_fact == 0: note = "MISS — sanity check failed"
        elif n_fact == 1: note = "unique"
        elif len(param_sets) == 1: note = "unique up to swap"
        print(f"{m:>4d}  {K:>4d}  {n_fact:>16d}  {len(param_sets):>22d}  {note}")
