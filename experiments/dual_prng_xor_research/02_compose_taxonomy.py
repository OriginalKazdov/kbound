"""Compose taxonomy — characterize which 2-LCG compositions our existing tools crack.

Hypothesis:
  - s1 + s2 mod m: should fall to Hankel det gcd (order-2 linear recurrence over Z/m)
  - s1 XOR s2: bitwise op, NOT a Z/m linear combination — should fail Hankel
  - s1 * s2 mod m: not a linear combination, should fail
  - s1 - s2 mod m: same shape as addition, should fall to Hankel
  - concat(s1, s2): two interleaved LCGs, recoverable by separating odd/even

Why this matters: XOR being structurally distinct from + mod m is the entire
research question. If even our generic-recurrence engine cracks it, there is
no novelty. If only addition falls and XOR doesn't, we've localized the gap.
"""
from __future__ import annotations

import sys
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from kbound.solvers.rce_lcg_generic import crack_lcg
from kbound.solvers.rce_recurrence_generic import crack_recurrence


def lcg_step(s: int, a: int, c: int, m: int) -> int:
    return (a * s + c) % m


def gen_dual(seed1, seed2, a1, c1, a2, c2, m, n, op):
    """Generate n outputs from out_k = op(s1_k, s2_k)."""
    s1, s2 = seed1, seed2
    out_seq = []
    for _ in range(n):
        s1 = lcg_step(s1, a1, c1, m)
        s2 = lcg_step(s2, a2, c2, m)
        out_seq.append(op(s1, s2, m))
    return out_seq


COMPOSITIONS = [
    ("ADD mod m", lambda s1, s2, m: (s1 + s2) % m),
    ("SUB mod m", lambda s1, s2, m: (s1 - s2) % m),
    ("MUL mod m", lambda s1, s2, m: (s1 * s2) % m),
    ("XOR (bitwise)", lambda s1, s2, m: s1 ^ s2),
    ("AND (bitwise)", lambda s1, s2, m: s1 & s2),
    ("OR (bitwise)", lambda s1, s2, m: s1 | s2),
]

# Use a manageable modulus for the recurrence solver (Hankel det grows fast)
M = 1000003  # 7-digit prime
A1, C1, SEED1 = 5, 11, 17
A2, C2, SEED2 = 7, 3, 23

print(f"m = {M}, LCG1=({A1},{C1},{SEED1}), LCG2=({A2},{C2},{SEED2})")
print()
print(f"{'Composition':20s} | {'Boyar-LCG':12s} | {'Hankel order-2':16s} | {'Hankel order-3':16s}")
print("-" * 75)

for name, op in COMPOSITIONS:
    seq = gen_dual(SEED1, SEED2, A1, C1, A2, C2, M, n=20, op=op)
    boyar = crack_lcg(seq)
    hankel2 = crack_recurrence(seq, order=2)
    hankel3 = crack_recurrence(seq, order=3)
    boyar_str = f"a={boyar[0]},m={boyar[2]}" if boyar else "FAIL"
    h2_str = f"c={hankel2[0]},m={hankel2[1]}" if hankel2 else "FAIL"
    h3_str = f"c={hankel3[0]},m={hankel3[1]}" if hankel3 else "FAIL"
    print(f"{name:20s} | {boyar_str:12s} | {h2_str:16s} | {h3_str:16s}")

print()
print("Key reads:")
print(" - ADD/SUB should be cracked by Hankel order-2 (linear combination of 2 LCG states).")
print(" - XOR/AND/OR are non-linear over Z/m and should fail Boyar AND Hankel.")
print(" - MUL is bilinear; might or might not have a clean linear-recurrence shape.")
