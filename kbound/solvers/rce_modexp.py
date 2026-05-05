"""RCE-ModExp symbolic solver — y = a^x mod p.

Modular exponentiation. Critical RSA primitive. Inverting this (finding x given y, a, p)
is the discrete log problem — hard in general but tractable for small p via brute force.

Detection: for each candidate (a, p), check if a^x ≡ y (mod p) for support pairs.
"""

from __future__ import annotations

from kbound.solvers.rce_lcg import DEFAULT_PRIME_POOL


def solve_modexp_symbolic(
    examples: list[tuple], query, prime_pool: list[int] | None = None, top_k_p: int = 10, max_a: int = 30
) -> dict:
    """Try y = a^x mod p over candidate (a, p) pairs."""
    if prime_pool is None:
        prime_pool = DEFAULT_PRIME_POOL

    xs = [int(e[0]) if not isinstance(e[0], (list, tuple)) else int(e[0][0]) for e in examples]
    ys = [int(e[1]) for e in examples]
    K = len(xs)

    y_max = max(ys)
    candidates = sorted([p for p in prime_pool if p > y_max])[:top_k_p]
    if not candidates:
        return {"predicted_y": None, "consistency_score": 0.0, "error": "No candidate p"}

    best = None
    for p in candidates:
        for a in range(2, min(p, max_a)):
            preds = [pow(a, x, p) for x in xs]
            score = sum(1 for pp, y in zip(preds, ys, strict=False) if pp == y) / K
            if best is None or score > best["score"]:
                best = {"a": a, "p": p, "score": score}
            if score == 1.0:
                break
        if best and best["score"] == 1.0:
            break

    if best is None or best["score"] < 0.85:
        return {
            "predicted_y": None,
            "consistency_score": 0.0 if best is None else best["score"],
            "error": "No fit",
        }

    qx = int(query) if not isinstance(query, (list, tuple)) else int(query[0])
    predicted_y = pow(best["a"], qx, best["p"])

    return {
        "predicted_y": predicted_y,
        "a": best["a"],
        "p": best["p"],
        "consistency_score": best["score"],
    }
