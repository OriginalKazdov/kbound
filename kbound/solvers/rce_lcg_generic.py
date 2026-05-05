"""RCE-LCG-Generic — Boyar's attack on an LCG with unknown (a, c, m).

Recovers the full parameter triple from K >= 6 consecutive outputs of any pure
LCG of the form x_{i+1} = (a * x_i + c) mod m, regardless of m. The classic
small-m search (rce_lcg.py) only handles primes <= ~1000; this solver covers
the rest of the space — Numerical Recipes (m=2^32), bespoke 32-bit / 64-bit
generators, leaked random IDs, etc.

Reference: Boyar, "Inferring Sequences Produced by Pseudo-Random Number
Generators" (J. ACM 1989). Recipe:
    Let t_i = x_{i+1} - x_i. Then t_{i+1} = a * t_i mod m.
    Let u_i = t_{i+2} * t_i - t_{i+1}^2 (computed in Z, not mod m).
    Each u_i is a multiple of m (when no wrap occurred its value is 0).
    gcd of |u_i| across multiple i recovers m (with high probability).
    Then a = t_1 * t_0^{-1} mod m, c = x_1 - a * x_0 mod m.
"""

from __future__ import annotations

from math import gcd

from kbound.solvers._modular import divisors, modinv


def crack_lcg(seq: list[int]) -> tuple[int, int, int] | None:
    """Recover (a, c, m) from K >= 6 consecutive LCG outputs.

    Returns None if the sequence does not match any pure LCG, or if the cracker
    cannot disambiguate parameters from the observed window.
    """
    n = len(seq)
    if n < 6:
        return None

    # First differences
    t = [seq[i + 1] - seq[i] for i in range(n - 1)]

    # Cross-product residues — each is a multiple of m
    u = [t[i + 2] * t[i] - t[i + 1] ** 2 for i in range(len(t) - 2)]
    u = [abs(v) for v in u if v != 0]
    if not u:
        return None

    # gcd recovers a multiple of m. The "true" m divides g, possibly with a
    # small spurious cofactor.  Enumerate divisors of g and pick the SMALLEST
    # divisor > max(seq) that yields a consistent (a, c) — that's the true m.
    # (Earlier heuristic of picking max(g, g*small_prime) was unsafe; could
    # return k·m_true silently when k > 1 still passes verification on a short
    # window.  Divisor enumeration is the same recipe used by polycoef_generic.)
    g = u[0]
    for v in u[1:]:
        g = gcd(g, v)
    if g < 2:
        return None

    y_max = max(seq)
    candidates = sorted(divisors(g))

    for m_candidate in candidates:
        if m_candidate <= y_max:
            continue
        # Recover a using the first invertible difference
        a = None
        for i in range(len(t) - 1):
            inv = modinv(t[i], m_candidate)
            if inv is not None:
                a = (t[i + 1] * inv) % m_candidate
                break
        if a is None:
            continue

        c = (seq[1] - a * seq[0]) % m_candidate

        # Verify: recovered triple must reproduce entire observed sequence
        ok = True
        cur = seq[0]
        for i in range(1, n):
            cur = (a * cur + c) % m_candidate
            if cur != seq[i]:
                ok = False
                break
        if ok:
            return (a, c, m_candidate)
    return None


def solve_lcg_generic(examples: list[tuple], query) -> dict:
    """Solver entrypoint. Examples must be (call_index, output) consecutive pairs."""
    if not examples or len(examples) < 6:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "need at least 6 consecutive outputs",
        }

    sorted_ex = sorted(examples, key=lambda e: e[0])
    xs = [int(e[0]) if not isinstance(e[0], (list, tuple)) else int(e[0][0]) for e in sorted_ex]
    ys = [int(e[1]) for e in sorted_ex]

    # Require consecutive call indices for the Boyar attack to apply directly.
    if not all(xs[i + 1] - xs[i] == 1 for i in range(len(xs) - 1)):
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "non-consecutive observation indices (need x = 0,1,2,...)",
        }

    cracked = crack_lcg(ys)
    if cracked is None:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "Boyar attack did not recover consistent (a, c, m)",
        }
    a, c, m = cracked

    # Project forward to query
    qx = int(query) if not isinstance(query, (list, tuple)) else int(query[0])
    cur_idx = xs[-1]
    cur_state = ys[-1]
    steps = qx - cur_idx
    if steps < 0:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "query index < last observed",
            "a": a,
            "c": c,
            "m": m,
        }
    for _ in range(steps):
        cur_state = (a * cur_state + c) % m

    return {
        "predicted_y": cur_state,
        "consistency_score": 1.0,
        "a": a,
        "c": c,
        "m": m,
        "form": "boyar_attack",
    }
