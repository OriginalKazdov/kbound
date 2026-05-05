"""RCE-ModInv symbolic solver — y = x^(-1) mod p.

Modular inverse: y is the multiplicative inverse of x in Z/pZ.
Detection: for each candidate prime p, check if x*y ≡ 1 (mod p) for support pairs.

Relevant to: cryptographic signature verification, modular fraction computations,
finite-field linear algebra steps.
"""

from __future__ import annotations

from kbound.solvers.rce_lcg import DEFAULT_PRIME_POOL


def solve_modinv_symbolic(
    examples: list[tuple], query, prime_pool: list[int] | None = None, top_k_p: int = 15
) -> dict:
    """Try y = x^(-1) mod p over candidate primes."""
    if prime_pool is None:
        prime_pool = DEFAULT_PRIME_POOL

    xs = [int(e[0]) if not isinstance(e[0], (list, tuple)) else int(e[0][0]) for e in examples]
    ys = [int(e[1]) for e in examples]
    K = len(xs)

    y_max = max(ys)
    candidates = sorted([p for p in prime_pool if p > y_max])[:top_k_p]
    if not candidates:
        return {"predicted_y": None, "p": None, "consistency_score": 0.0, "error": "No candidate p"}

    best = None
    for p in candidates:
        score = sum(1 for x, y in zip(xs, ys, strict=False) if (x * y) % p == 1) / K
        if best is None or score > best["score"]:
            best = {"p": p, "score": score}
        if score == 1.0:
            break

    if best is None or best["score"] < 0.85:
        return {
            "predicted_y": None,
            "p": None,
            "consistency_score": 0.0 if best is None else best["score"],
            "error": "No fit",
        }

    qx = int(query) if not isinstance(query, (list, tuple)) else int(query[0])
    p = best["p"]

    # Compute x^(-1) mod p via extended Euclidean
    def modinv(a, m):
        a = a % m
        if a == 0:
            return None
        # extended Euclidean
        old_r, r = a, m
        old_s, s = 1, 0
        while r != 0:
            q = old_r // r
            old_r, r = r, old_r - q * r
            old_s, s = s, old_s - q * s
        if old_r != 1:
            return None
        return old_s % m

    predicted_y = modinv(qx, p)
    return {
        "predicted_y": predicted_y,
        "p": p,
        "consistency_score": best["score"],
    }
