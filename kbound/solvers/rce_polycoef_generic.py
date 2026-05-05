"""RCE-Polycoef-Generic — Vandermonde-determinant-gcd attack on polynomials of unknown modulus.

Recovers (a_0, ..., a_d, p) for f(x) = (a_d * x^d + ... + a_0) mod p with unknown
p of arbitrary size, given K >= d+2 observations.

Method (analogous to Boyar's LCG attack):
    For a degree-d polynomial, take d+2 points (x_j, y_j). The augmented
    Vandermonde matrix [[1, x_j, ..., x_j^d, y_j]] has linearly-dependent columns
    over Z/p (since y_j ≡ f(x_j) mod p), so its determinant is 0 mod p — i.e.
    the determinant computed in Z is a multiple of p.

    gcd of determinants from many (d+2)-subsets recovers p (up to a small
    spurious cofactor we strip by trying small divisors).

    Once p is known, solve the (d+1)x(d+1) Vandermonde system mod p for the
    coefficients via standard Gaussian elimination.
"""

from __future__ import annotations

from itertools import combinations
from math import gcd

from kbound.solvers._modular import divisors as _divisors
from kbound.solvers._modular import modinv as _modinv


def _det_int(M: list[list[int]]) -> int:
    """Integer determinant via cofactor expansion (n <= 5 in practice — degree <= 3)."""
    n = len(M)
    if n == 1:
        return M[0][0]
    if n == 2:
        return M[0][0] * M[1][1] - M[0][1] * M[1][0]
    total = 0
    for j in range(n):
        minor = [row[:j] + row[j + 1 :] for row in M[1:]]
        total += ((-1) ** j) * M[0][j] * _det_int(minor)
    return total


def _augmented_vandermonde(pts: list[tuple[int, int]], degree: int) -> list[list[int]]:
    return [[x**i for i in range(degree + 1)] + [y] for x, y in pts]


def _solve_vandermonde_mod_p(pts: list[tuple[int, int]], degree: int, p: int) -> list[int] | None:
    """Solve for coefficients (a_0, ..., a_degree) mod p using d+1 points.

    Builds (d+1) x (d+1) Vandermonde [[1, x_j, ..., x_j^d]] and solves for
    coefficient vector against y mod p.
    """
    if len(pts) < degree + 1:
        return None
    sub = pts[: degree + 1]
    n = degree + 1
    A = [[(x**i) % p for i in range(n)] for x, _ in sub]
    b = [y % p for _, y in sub]
    # Gaussian elimination mod p
    for col in range(n):
        # Find a pivot row with non-zero entry in this column
        pivot = None
        for r in range(col, n):
            if A[r][col] % p != 0:
                pivot = r
                break
        if pivot is None:
            return None
        if pivot != col:
            A[col], A[pivot] = A[pivot], A[col]
            b[col], b[pivot] = b[pivot], b[col]
        inv = _modinv(A[col][col], p)
        if inv is None:
            return None
        # Scale row to have leading 1
        A[col] = [(v * inv) % p for v in A[col]]
        b[col] = (b[col] * inv) % p
        # Eliminate this column from all other rows
        for r in range(n):
            if r == col:
                continue
            factor = A[r][col]
            if factor == 0:
                continue
            A[r] = [(A[r][k] - factor * A[col][k]) % p for k in range(n)]
            b[r] = (b[r] - factor * b[col]) % p
    return b  # b is now the coefficient vector


def _verify_poly(coeffs: list[int], p: int, pts: list[tuple[int, int]]) -> bool:
    for x, y in pts:
        pred = sum(c * (x**i) for i, c in enumerate(coeffs)) % p
        if pred != y % p:
            return False
    return True


def crack_polycoef(
    pts: list[tuple[int, int]], degree: int, max_subsets: int = 40
) -> tuple[list[int], int] | None:
    """Recover (coeffs, p) for a polynomial of given degree from K >= degree+2 points.

    Returns (coeffs_low_to_high, p) or None if the data does not match.
    """
    n_needed = degree + 2  # for the augmented-Vandermonde determinant trick
    if len(pts) < n_needed:
        return None

    # Compute determinants from disjoint (or random) (d+2)-subsets
    # Take the first max_subsets combinations to keep runtime bounded.
    det_values: list[int] = []
    for sub_idx, sub in enumerate(combinations(range(len(pts)), n_needed)):
        if sub_idx >= max_subsets:
            break
        M = _augmented_vandermonde([pts[i] for i in sub], degree)
        d = _det_int(M)
        if d != 0:
            det_values.append(abs(d))

    if not det_values:
        return None

    # gcd recovers p up to a small spurious cofactor
    g = det_values[0]
    for v in det_values[1:]:
        g = gcd(g, v)
    if g < 2:
        return None

    # The true p divides g. Enumerate divisors of g and pick the smallest one
    # > y_max that yields a coefficient vector consistent with all points.
    # We factor g by trial division through small primes, then build all divisors.
    y_max = max(y for _, y in pts)
    candidates = sorted(_divisors(g))

    for p in candidates:
        if p <= y_max:
            continue
        coeffs = _solve_vandermonde_mod_p(pts, degree, p)
        if coeffs is None:
            continue
        if _verify_poly(coeffs, p, pts):
            return (coeffs, p)

    return None


def solve_polycoef_generic(examples: list[tuple], query) -> dict:
    """Solver entrypoint. Tries degree=2 then degree=3."""
    if not examples or len(examples) < 4:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "need at least 4 observations",
        }

    pts: list[tuple[int, int]] = []
    for x, y in examples:
        xi = int(x) if not isinstance(x, (list, tuple)) else int(x[0])
        pts.append((xi, int(y)))

    for degree in (2, 3):
        if len(pts) < degree + 2:
            continue
        cracked = crack_polycoef(pts, degree)
        if cracked is None:
            continue
        coeffs, p = cracked
        # Apply to query
        qx = int(query) if not isinstance(query, (list, tuple)) else int(query[0])
        predicted = sum(c * (qx**i) for i, c in enumerate(coeffs)) % p
        # Build params dict in the same shape as small-mod polycoef solver
        params = {"p": p, "degree": degree}
        for i, c in enumerate(coeffs):
            params[f"coeff_{i}"] = c
        # Common labels: a (highest), b, c, d (lowest) for d<=3
        if degree == 2:
            params.update({"a": coeffs[2], "b": coeffs[1], "c": coeffs[0]})
        elif degree == 3:
            params.update({"a": coeffs[3], "b": coeffs[2], "c": coeffs[1], "d": coeffs[0]})
        return {
            "predicted_y": predicted,
            "consistency_score": 1.0,
            "form": "vandermonde_det_gcd",
            "degree": degree,
            **params,
        }

    return {
        "predicted_y": None,
        "consistency_score": 0.0,
        "reason": "Vandermonde-determinant-gcd attack did not recover a consistent polynomial",
    }
