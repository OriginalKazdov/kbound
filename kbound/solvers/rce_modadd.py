"""RCE-ModAdd symbolic solver — for 2-input modular addition: y = (x1 + x2) mod p.

Method: try p from prime pool, score by exact match on full support, pick best p.
Pure symbolic, no neural component.
"""

from __future__ import annotations

from kbound.solvers.rce_lcg import DEFAULT_PRIME_POOL


def solve_modadd_symbolic(examples: list[tuple], query, prime_pool: list[int] | None = None) -> dict:
    """Try y = (x1 + x2) mod p for candidate primes."""
    if prime_pool is None:
        prime_pool = DEFAULT_PRIME_POOL

    pairs = []
    for x, y in examples:
        if not isinstance(x, (list, tuple)) or len(x) != 2:
            return {
                "predicted_y": None,
                "p": None,
                "consistency_score": 0.0,
                "error": "ModAdd requires 2-input examples",
            }
        pairs.append((int(x[0]), int(x[1]), int(y)))

    K = len(pairs)
    y_max = max(y for _, _, y in pairs)

    best = None
    for p in sorted([pp for pp in prime_pool if pp > y_max])[:20]:
        match = sum(1 for a, b, y in pairs if (a + b) % p == y)
        score = match / K
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

    if not isinstance(query, (list, tuple)) or len(query) != 2:
        return {
            "predicted_y": None,
            "p": best["p"],
            "consistency_score": best["score"],
            "error": "Query must be 2-input",
        }

    qx1, qx2 = int(query[0]), int(query[1])
    predicted_y = (qx1 + qx2) % best["p"]

    return {
        "predicted_y": predicted_y,
        "p": best["p"],
        "consistency_score": best["score"],
    }
