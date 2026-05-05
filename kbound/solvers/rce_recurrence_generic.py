"""RCE-Recurrence-Generic — Hankel-det-gcd attack on linear recurrences with unknown modulus.

Recovers (c_1, c_2, m) for an order-2 linear recurrence
    y_n = (c_1 * y_{n-1} + c_2 * y_{n-2}) mod m
from K >= 5 consecutive observations of arbitrary modulus size.

Method (analogous to Boyar's LCG attack and the polynomial Vandermonde-det attack):
    For an order-k linear recurrence over Z/m, the (k+1)x(k+1) Hankel matrix
    H = [[y_i, y_{i+1}, ..., y_{i+k}] for i in 0..k] has rank <= k mod m
    (because the columns satisfy the recurrence). So det(H) computed in Z is
    a multiple of m.

    gcd of determinants across many sliding windows recovers m. Then a 2x2
    linear system mod m yields (c_1, c_2). Order-3 extension in the
    same shape (4x4 Hankel det -> 3x3 system).
"""

from __future__ import annotations

from math import gcd

from kbound.solvers._modular import modinv as _modinv
from kbound.solvers.rce_polycoef_generic import _divisors


def _det_int(M: list[list[int]]) -> int:
    """Integer determinant via cofactor expansion."""
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


def _solve_2x2_mod_p(M: list[list[int]], rhs: list[int], p: int) -> list[int] | None:
    """Solve M @ x = rhs mod p for 2x2 M."""
    det = (M[0][0] * M[1][1] - M[0][1] * M[1][0]) % p
    inv = _modinv(det, p)
    if inv is None:
        return None
    x0 = (rhs[0] * M[1][1] - rhs[1] * M[0][1]) * inv % p
    x1 = (rhs[1] * M[0][0] - rhs[0] * M[1][0]) * inv % p
    return [x0, x1]


def _solve_3x3_mod_p(M: list[list[int]], rhs: list[int], p: int) -> list[int] | None:
    """Solve M @ x = rhs mod p for 3x3 M via Gaussian elimination."""
    n = 3
    A = [row[:] + [rhs[i]] for i, row in enumerate(M)]
    for col in range(n):
        pivot = None
        for r in range(col, n):
            if A[r][col] % p != 0:
                pivot = r
                break
        if pivot is None:
            return None
        if pivot != col:
            A[col], A[pivot] = A[pivot], A[col]
        inv = _modinv(A[col][col], p)
        if inv is None:
            return None
        A[col] = [(v * inv) % p for v in A[col]]
        for r in range(n):
            if r == col:
                continue
            factor = A[r][col]
            if factor == 0:
                continue
            A[r] = [(A[r][k] - factor * A[col][k]) % p for k in range(n + 1)]
    return [row[n] for row in A]


def crack_recurrence(seq: list[int], order: int = 2) -> tuple[list[int], int] | None:
    """Recover ([c_1, ..., c_order], m) from K consecutive recurrence outputs."""
    n = len(seq)
    needed = 2 * order + 1
    if n < needed:
        return None

    # Build (order+1) x (order+1) Hankel matrices from sliding windows.
    det_values: list[int] = []
    for start in range(n - 2 * order):
        H = [[seq[start + i + j] for j in range(order + 1)] for i in range(order + 1)]
        d = _det_int(H)
        if d != 0:
            det_values.append(abs(d))
    if not det_values:
        return None

    g = det_values[0]
    for v in det_values[1:]:
        g = gcd(g, v)
    if g < 2:
        return None

    y_max = max(seq)
    candidates = sorted(_divisors(g))

    for m in candidates:
        if m <= y_max:
            continue
        # Solve for coefficients: y_{order} = c_1 * y_{order-1} + c_2 * y_{order-2} + ... mod m
        # System: M @ c = rhs where row i is [y_{i+order-1}, y_{i+order-2}, ..., y_i]
        # and rhs[i] = y_{i+order}, for i in 0..order-1.
        coeffs: list[int] | None = None
        if order == 2:
            M = [[seq[1], seq[0]], [seq[2], seq[1]]]
            rhs = [seq[2], seq[3]]
            coeffs = _solve_2x2_mod_p(M, rhs, m)
        elif order == 3:
            M = [[seq[2], seq[1], seq[0]], [seq[3], seq[2], seq[1]], [seq[4], seq[3], seq[2]]]
            rhs = [seq[3], seq[4], seq[5]]
            coeffs = _solve_3x3_mod_p(M, rhs, m)
        if coeffs is None:
            continue
        # Verify on the full sequence
        if _verify_recurrence(seq, coeffs, m, order):
            return (coeffs, m)
    return None


def _verify_recurrence(seq: list[int], coeffs: list[int], m: int, order: int) -> bool:
    for i in range(order, len(seq)):
        pred = sum(coeffs[j] * seq[i - 1 - j] for j in range(order)) % m
        if pred != seq[i] % m:
            return False
    return True


def solve_recurrence_generic(examples: list[tuple], query) -> dict:
    """Solver entrypoint. Examples must be (position, value) consecutive pairs."""
    if not examples:
        return {"predicted_y": None, "consistency_score": 0.0, "reason": "no examples"}

    sorted_ex = sorted(
        examples, key=lambda e: int(e[0]) if not isinstance(e[0], (list, tuple)) else int(e[0][0])
    )
    ns = [int(e[0]) if not isinstance(e[0], (list, tuple)) else int(e[0][0]) for e in sorted_ex]
    vals = [int(e[1]) for e in sorted_ex]

    # Need consecutive positions starting at some n_0
    if not all(ns[i + 1] - ns[i] == 1 for i in range(len(ns) - 1)):
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "non-consecutive positions",
        }

    # Try order 2, then order 3
    for order in (2, 3):
        cracked = crack_recurrence(vals, order=order)
        if cracked is None:
            continue
        coeffs, m = cracked
        # Project forward to query
        qn = int(query) if not isinstance(query, (list, tuple)) else int(query[0])
        cur_n = ns[-1]
        # If query is in observed range, look it up
        if qn <= ns[-1] and qn >= ns[0]:
            return {
                "predicted_y": vals[qn - ns[0]],
                "consistency_score": 1.0,
                "coefficients": coeffs,
                "m": m,
                "order": order,
                "form": "hankel_det_gcd",
            }
        # Otherwise extend forward
        seq = list(vals)
        for _ in range(qn - cur_n):
            nxt = sum(coeffs[j] * seq[-1 - j] for j in range(order)) % m
            seq.append(nxt)
        return {
            "predicted_y": seq[-1],
            "consistency_score": 1.0,
            "coefficients": coeffs,
            "m": m,
            "order": order,
            "form": "hankel_det_gcd",
        }

    return {
        "predicted_y": None,
        "consistency_score": 0.0,
        "reason": "Hankel-determinant-gcd attack did not recover a consistent recurrence",
    }
