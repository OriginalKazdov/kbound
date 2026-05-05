"""Gateway test — dual-LCG XOR composition cracking.

Goal of this script: determine whether Boyar's classical attack passes through
on the XOR of two LCGs running in parallel:

    state1_{k+1} = (a1 * state1_k + c1) mod m
    state2_{k+1} = (a2 * state2_k + c2) mod m
    output_k     = state1_k XOR state2_k

Hypothesis (probable): Boyar fails because XOR breaks the geometric structure
of differences that the gcd attack relies on.  The next-difference t_k =
out_{k+1} - out_k is not a*t_{k-1} mod m anymore — XOR mixes the carries
non-linearly with respect to integer subtraction.

Outputs we care about:
  1. Does crack_lcg() return None? (expected yes)
  2. What does the difference / cross-product sequence look like?
  3. Does BMA over GF(2) find a short recurrence?
  4. Does the XOR output satisfy ANY simple closed form?
"""
from __future__ import annotations

import sys
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from math import gcd
from kbound.solvers.rce_lcg_generic import crack_lcg, _modinv


def lcg_step(s: int, a: int, c: int, m: int) -> int:
    return (a * s + c) % m


def gen_dual_xor(seed1: int, seed2: int,
                 a1: int, c1: int, a2: int, c2: int,
                 m: int, n: int) -> tuple[list[int], list[int], list[int]]:
    """Generate n outputs from out_k = s1_k XOR s2_k."""
    s1, s2 = seed1, seed2
    s1_seq, s2_seq, out_seq = [], [], []
    for _ in range(n):
        s1 = lcg_step(s1, a1, c1, m)
        s2 = lcg_step(s2, a2, c2, m)
        s1_seq.append(s1)
        s2_seq.append(s2)
        out_seq.append(s1 ^ s2)
    return s1_seq, s2_seq, out_seq


def boyar_signature(seq: list[int]) -> dict:
    """Inspect what Boyar would compute internally."""
    n = len(seq)
    t = [seq[i + 1] - seq[i] for i in range(n - 1)]
    u = [t[i + 2] * t[i] - t[i + 1] ** 2 for i in range(len(t) - 2)]
    u_abs = [abs(v) for v in u if v != 0]
    g = u_abs[0] if u_abs else 0
    for v in u_abs[1:]:
        g = gcd(g, v)
    return {
        "n_t": len(t),
        "n_u": len(u),
        "n_u_nonzero": len(u_abs),
        "gcd_u": g,
        "first_5_u_abs": u_abs[:5],
    }


# ===========================================================
# Case 1: same modulus m, different (a, c, seed) for the 2 LCGs
# ===========================================================

print("=" * 60)
print("Case 1: out_k = s1_k XOR s2_k, same m, different params")
print("=" * 60)

m = (1 << 31) - 1  # Mersenne prime 2^31 - 1
a1, c1, seed1 = 1103515245, 12345, 1234
a2, c2, seed2 = 22695477, 1, 5678

s1_seq, s2_seq, out_seq = gen_dual_xor(seed1, seed2, a1, c1, a2, c2, m, n=200)

print(f"  m = {m} ({m.bit_length()}-bit)")
print(f"  LCG1: a={a1}, c={c1}, seed={seed1}")
print(f"  LCG2: a={a2}, c={c2}, seed={seed2}")
print(f"  First 5 s1: {s1_seq[:5]}")
print(f"  First 5 s2: {s2_seq[:5]}")
print(f"  First 5 out (s1 XOR s2): {out_seq[:5]}")

# Run Boyar directly on the XOR output
print("\nBoyar.crack_lcg() on XOR output:")
result = crack_lcg(out_seq[:30])
print(f"  -> {result} (None expected)")

# Look at Boyar's internal signature
print("\nBoyar internal signature on XOR sequence (K=30):")
sig = boyar_signature(out_seq[:30])
print(f"  {sig}")

# Compare against Boyar on a SINGLE LCG (sanity check the harness)
print("\nSanity: Boyar on s1 alone (single LCG):")
result_single = crack_lcg(s1_seq[:30])
print(f"  -> a={result_single[0] if result_single else None}, "
      f"c={result_single[1] if result_single else None}, "
      f"m={result_single[2] if result_single else None}")
print(f"  (truth: a={a1}, c={c1}, m={m})")

print("\n" + "=" * 60)
print("Conclusion of Case 1")
print("=" * 60)
print("""
If Boyar returned None on XOR output but recovered s1 alone,
this confirms XOR breaks the gcd attack structure as expected.
The interesting question is: what DOES the XOR sequence satisfy?
That's what we need to characterize next.
""")
