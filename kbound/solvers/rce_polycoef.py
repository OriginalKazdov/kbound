"""RCE-Polycoef symbolic solver — adapted from geometry-of-induction/src/eval_polycoef_solvernet.py.

Task: f(x) = (a*x² + b*x + c) mod p
Method: with p tried from prime pool, 3x3 linear system mod p via Gaussian elimination,
score by consistency on full support, pick best (a, b, c, p) tuple.
"""

from __future__ import annotations

from itertools import combinations

from kbound.solvers._modular import modinv as _modinv

# Same prime pool as RCE-LCG
from kbound.solvers.rce_lcg import DEFAULT_PRIME_POOL


def _solve_3x3_mod_p(M: list[list[int]], y: list[int], p: int) -> list[int] | None:
    """Gaussian elimination mod p on 3x3 system. Returns (a, b, c) or None."""
    A = [[v % p for v in row] for row in M]
    rhs = [v % p for v in y]
    n = 3
    for col in range(n):
        pivot_row = None
        for r in range(col, n):
            if A[r][col] % p != 0:
                pivot_row = r
                break
        if pivot_row is None:
            return None
        if pivot_row != col:
            A[col], A[pivot_row] = A[pivot_row], A[col]
            rhs[col], rhs[pivot_row] = rhs[pivot_row], rhs[col]
        inv = _modinv(A[col][col], p)
        if inv is None:
            return None
        A[col] = [(v * inv) % p for v in A[col]]
        rhs[col] = (rhs[col] * inv) % p
        for r in range(n):
            if r == col:
                continue
            factor = A[r][col] % p
            if factor != 0:
                A[r] = [(A[r][c] - factor * A[col][c]) % p for c in range(n)]
                rhs[r] = (rhs[r] - factor * rhs[col]) % p
    return rhs


def _try_polycoef_for_p(xs: list[int], ys: list[int], p: int, max_triples: int = 20) -> dict | None:
    """Try to fit (a, b, c) for given p via 3x3 mod p Gaussian elimination."""
    K = len(xs)
    best = None
    triples = list(combinations(range(K), 3))[:max_triples]
    for i, j, k in triples:
        triple_xs = [xs[i] % p, xs[j] % p, xs[k] % p]
        if len(set(triple_xs)) < 3:  # need distinct mod p
            continue
        M = [[(x * x) % p, x % p, 1] for x in [xs[i], xs[j], xs[k]]]
        Y = [ys[i], ys[j], ys[k]]
        sol = _solve_3x3_mod_p(M, Y, p)
        if sol is None:
            continue
        a, b, c = sol
        # Validate on full support
        match = sum(1 for n in range(K) if (a * xs[n] ** 2 + b * xs[n] + c) % p == ys[n])
        score = match / K
        if best is None or score > best["score"]:
            best = {"a": a, "b": b, "c": c, "p": p, "score": score}
        if score == 1.0:
            break
    return best


def solve_polycoef_symbolic(
    examples: list[tuple], query, prime_pool: list[int] | None = None, top_k_p: int = 12
) -> dict:
    """Try polycoef fit y = (a*x² + b*x + c) mod p over candidate primes.

    Returns dict with predicted_y, a, b, c, p, consistency_score.
    """
    if prime_pool is None:
        prime_pool = DEFAULT_PRIME_POOL

    xs = [int(e[0]) if not isinstance(e[0], (list, tuple)) else int(e[0][0]) for e in examples]
    ys = [int(e[1]) for e in examples]

    # p must be > max(ys)
    y_max = max(ys)
    candidates = sorted([p for p in prime_pool if p > y_max])[:top_k_p]
    if not candidates:
        return {
            "predicted_y": None,
            "a": None,
            "b": None,
            "c": None,
            "p": None,
            "consistency_score": 0.0,
            "error": "No candidate p",
        }

    best = None
    for p in candidates:
        result = _try_polycoef_for_p(xs, ys, p)
        if result is None:
            continue
        if best is None or result["score"] > best["score"]:
            best = result
        if best and best["score"] == 1.0:
            break

    if best is None:
        return {
            "predicted_y": None,
            "a": None,
            "b": None,
            "c": None,
            "p": None,
            "consistency_score": 0.0,
            "error": "No fit found",
        }

    qx = int(query) if not isinstance(query, (list, tuple)) else int(query[0])
    predicted_y = (best["a"] * qx * qx + best["b"] * qx + best["c"]) % best["p"]

    return {
        "predicted_y": predicted_y,
        "a": best["a"],
        "b": best["b"],
        "c": best["c"],
        "p": best["p"],
        "consistency_score": best["score"],
    }
