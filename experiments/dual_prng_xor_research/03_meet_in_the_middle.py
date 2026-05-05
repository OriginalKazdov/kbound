"""Attack approach: brute-force one LCG's state, recover the other via Boyar.

Setup: both LCGs have UNKNOWN params (a1, c1, m1) and (a2, c2, m2), and
unknown seeds. We observe out_k = s1_k XOR s2_k for K consecutive k.

Naive idea: for each candidate s1_0, derive s2_0 = out_0 XOR s1_0; step both
sequences; check consistency. But unknown params makes this hopeless.

Smarter idea: assume m1 = m2 = m (single modulus, common case). Then:
  s2_k = out_k XOR s1_k  (bitwise, valid for any k since both states < m)
  IF s1_k forms a valid LCG sequence over Z/m AND s2_k = (out_k XOR s1_k)
  ALSO forms a valid LCG sequence, we have a candidate.

Brute-force angle 1: guess (m, a1, c1, s1_0).  Each guess defines s1_seq, then
s2_seq, then we check if s2_seq is consistent with a single LCG via Boyar.
Cost: |m| × |a| × |c| × |seed|, way too large.

Brute-force angle 2: SMALL m, exhaustive search.  If m is e.g. 11 or 13, the
search space is tiny — useful as a sanity check that "Boyar after guess" works
in principle.

This script: do exhaustive search at small m to verify the attack pattern works,
then estimate scaling.
"""
from __future__ import annotations

import sys
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from itertools import product
from kbound.solvers.rce_lcg_generic import crack_lcg


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


def is_consistent_lcg(seq, m_known=None):
    """Is the sequence consistent with SOME LCG y_{n+1} = (a*y_n + c) mod m?

    If m_known is given, only check that modulus. Returns (a, c, m) or None.
    """
    n = len(seq)
    if n < 4:
        return None
    if m_known is None:
        # Use Boyar with full unknown params
        return crack_lcg(seq)
    # m known: solve a, c directly from any 2 consecutive transitions
    # s_{k+1} - s_k = a * (s_k - s_{k-1}) mod m
    if all(0 <= s < m_known for s in seq) is False:
        return None
    # Try a from a few transitions
    diff = [(seq[i + 1] - seq[i]) % m_known for i in range(n - 1)]
    if diff[0] == 0:
        return None
    # a * diff[0] = diff[1] mod m_known
    from math import gcd
    g = gcd(diff[0], m_known)
    if g != 1:
        return None
    # modular inverse
    def modinv(a, m):
        # ext gcd
        old_r, r = a, m
        old_s, s = 1, 0
        while r:
            q = old_r // r
            old_r, r = r, old_r - q * r
            old_s, s = s, old_s - q * s
        return old_s % m
    inv = modinv(diff[0], m_known)
    a = (diff[1] * inv) % m_known
    c = (seq[1] - a * seq[0]) % m_known
    # verify
    cur = seq[0]
    for i in range(1, n):
        cur = (a * cur + c) % m_known
        if cur != seq[i]:
            return None
    return (a, c, m_known)


def attack_brute_one_seed(out_seq, m):
    """Try every s1_0 in [0, m). For each, derive s2_seq and check both are LCGs.

    Cost: O(m) Boyar attempts. Only feasible for small m.
    """
    candidates = []
    for s1_0 in range(m):
        # Find a1, c1 such that s1 sequence is LCG with start s1_0 and matches?
        # We don't have s1 directly; we have (s1 XOR s2). We're guessing s1_0,
        # then trying to reconstruct (a1, c1, s1_seq) AND get a valid s2_seq.
        # BUT: we don't know a1, c1 either. So we'd need also to brute-force those.
        # For small m, do it anyway.
        for a1 in range(1, m):
            for c1 in range(m):
                # Generate s1 sequence
                s1 = s1_0
                s1_seq = []
                ok = True
                for k in range(len(out_seq)):
                    s1 = (a1 * s1 + c1) % m
                    s1_seq.append(s1)
                # Derive s2 sequence
                s2_seq = [out_seq[k] ^ s1_seq[k] for k in range(len(out_seq))]
                # Check s2_seq is a valid LCG over Z/m
                if any(s >= m for s in s2_seq):
                    continue
                fit = is_consistent_lcg(s2_seq, m_known=m)
                if fit:
                    candidates.append({
                        "s1_0": s1_0, "a1": a1, "c1": c1,
                        "s1_seq[:5]": s1_seq[:5],
                        "s2_fit (a, c, m)": fit,
                    })
                    if len(candidates) > 5:
                        return candidates  # found enough
    return candidates


# Tiny test: m = 11
print("=" * 60)
print("Brute-one-seed attack on tiny dual-LCG XOR (m=11)")
print("=" * 60)

M = 11
A1, C1, SEED1 = 3, 2, 4
A2, C2, SEED2 = 5, 1, 7

out_seq = gen_dual_xor(SEED1, SEED2, A1, C1, A2, C2, M, n=12)
print(f"  Truth: m={M}, LCG1=({A1},{C1},seed={SEED1}), LCG2=({A2},{C2},seed={SEED2})")
print(f"  Out (first 12): {out_seq}")

# Sanity: confirm Boyar fails on the XOR sequence
boyar_naive = crack_lcg(out_seq)
print(f"  Boyar naive on XOR: {boyar_naive}")

# Brute force attack
print()
print("  Brute-forcing all (s1_0, a1, c1) candidates over Z/11...")
candidates = attack_brute_one_seed(out_seq, M)
print(f"  Found {len(candidates)} candidate(s):")
for c in candidates[:10]:
    print(f"    {c}")

print()
print("Note on scaling: brute force is O(m^3) for (s1_0, a1, c1). At m=11 that's 11^3=1331")
print("attempts. At m=1000003 that's 10^18 — totally infeasible. Need a smarter angle.")
