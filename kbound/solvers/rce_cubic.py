"""RCE-Cubic — recover y = (a·x³ + b·x² + c·x + d) mod p

Extends rce_polycoef to degree 3. Building block for arithmetization-oriented
primitive cryptanalysis: MiMC's permutation step is essentially x ↦ x³ mod p
(plus key + constants), and Poseidon's S-box is x ↦ x⁵.

This is a 4-unknown linear system over GF(p): given K ≥ 4 distinct (x, y) pairs,
solve via Gaussian elimination (Vandermonde matrix).

Coverage:
  - MiMC single-round (degree-3 S-box)
  - Generic cubic recovery for buggy custom RNGs
  - Stepping stone to AO primitive multi-round attacks
"""

from __future__ import annotations

from kbound.solvers._modular import modinv as _modinv_helper


def _modinv(a: int, p: int) -> int:
    """Modular inverse for prime p (matches the original Fermat-based signature)."""
    inv = _modinv_helper(a, p)
    if inv is None:
        # In the cubic solver every call goes through with p prime and a in
        # [1, p-1], so this fallback is unreachable in practice.
        return pow(a, p - 2, p)
    return inv


def _gaussian_solve_mod_p(matrix: list[list[int]], rhs: list[int], p: int) -> list[int] | None:
    """Solve A·x = b over GF(p) via Gaussian elimination. Returns x or None if singular."""
    n = len(matrix)
    A = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]

    for col in range(n):
        # Find pivot
        pivot = None
        for r in range(col, n):
            if A[r][col] % p != 0:
                pivot = r
                break
        if pivot is None:
            return None  # singular
        A[col], A[pivot] = A[pivot], A[col]
        # Normalize
        inv = _modinv(A[col][col] % p, p)
        A[col] = [(v * inv) % p for v in A[col]]
        # Eliminate
        for r in range(n):
            if r == col:
                continue
            factor = A[r][col] % p
            if factor == 0:
                continue
            A[r] = [(A[r][k] - factor * A[col][k]) % p for k in range(n + 1)]
    return [A[i][n] % p for i in range(n)]


def solve_cubic_symbolic(examples: list[tuple], query, p_pool: list[int] | None = None) -> dict:
    """Recover (a, b, c, d, p) for y = (a·x³ + b·x² + c·x + d) mod p.

    Tries candidate primes; for each, builds a 4×4 Vandermonde system from any 4
    distinct examples and verifies on the rest.
    """
    if len(examples) < 4:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "need at least 4 distinct examples for cubic recovery",
            "details": {},
        }

    xs = [int(e[0]) for e in examples]
    ys = [int(e[1]) for e in examples]
    if len(set(xs)) < 4:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "need 4 distinct x values",
            "details": {},
        }

    if p_pool is None:
        from kbound.solvers.rce_lcg import DEFAULT_PRIME_POOL

        max_y = max(ys)
        p_pool = [p for p in DEFAULT_PRIME_POOL if p > max_y][:60]

    best = (0.0, None, None)
    for p in p_pool:
        # Pick 4 distinct examples for the linear system
        used_idx = []
        seen_x = set()
        for i, x in enumerate(xs):
            if x not in seen_x:
                used_idx.append(i)
                seen_x.add(x)
                if len(used_idx) == 4:
                    break
        if len(used_idx) < 4:
            continue

        # Vandermonde matrix [x³, x², x, 1]
        M = [[pow(xs[i], 3, p), pow(xs[i], 2, p), xs[i] % p, 1] for i in used_idx]
        b = [ys[i] % p for i in used_idx]

        coeffs = _gaussian_solve_mod_p(M, b, p)
        if coeffs is None:
            continue
        A, B, C, D = coeffs

        # Verify on ALL examples
        consistent = sum(
            1
            for x, y in zip(xs, ys, strict=False)
            if (A * pow(x, 3, p) + B * pow(x, 2, p) + C * x + D) % p == y % p
        )
        score = consistent / len(xs)
        if score > best[0]:
            best = (score, (A, B, C, D, p), used_idx)
            if score == 1.0:
                break

    if best[0] < 0.85 or best[1] is None:
        return {
            "predicted_y": None,
            "consistency_score": best[0],
            "reason": "no cubic poly fits at >85% consistency",
            "details": {},
        }

    A, B, C, D, p = best[1]
    qx = int(query)
    pred = (A * pow(qx, 3, p) + B * pow(qx, 2, p) + C * qx + D) % p

    return {
        "predicted_y": pred,
        "consistency_score": best[0],
        "a": A,
        "b": B,
        "c": C,
        "d": D,
        "p": p,
        "details": {
            "form": "y = (a·x³ + b·x² + c·x + d) mod p",
            "a": A,
            "b": B,
            "c": C,
            "d": D,
            "p": p,
        },
    }
