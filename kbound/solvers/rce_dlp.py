"""RCE-DLP symbolic solver — discrete logarithm (inverse of ModExp).

Given (a, p) and y, find x such that a^x ≡ y (mod p).
Inverse of modular exponentiation. Critical for cryptanalysis (RSA, ElGamal, DSA).

For our K-shot setup: examples are (y_i, x_i) pairs where y_i = a^{x_i} mod p,
and we recover (a, p), then for the query y_q find x_q.

Brute force is tractable for small p (< 1000) since the discrete log has at most
p-1 distinct values. For larger p, baby-step-giant-step would be needed (TODO).
"""

from __future__ import annotations

from kbound.solvers.rce_lcg import DEFAULT_PRIME_POOL


def solve_dlp_symbolic(
    examples: list[tuple],
    query,
    prime_pool: list[int] | None = None,
    max_a: int = 30,
    max_p_for_dlp: int = 500,
) -> dict:
    """Try to recover (a, p) and solve discrete log a^x ≡ y mod p.

    Examples are (input, output) where input is y, output is x.
    Equivalently: y = a^x mod p, given y, find x.

    For the K-shot setup: examples (y_i, x_i) pairs with shared (a, p).
    """
    if prime_pool is None:
        prime_pool = DEFAULT_PRIME_POOL

    # Examples: (y, x) means y = a^x mod p
    ys = [int(e[0]) if not isinstance(e[0], (list, tuple)) else int(e[0][0]) for e in examples]
    xs = [int(e[1]) for e in examples]
    K = len(xs)

    y_max = max(ys)
    candidates_p = sorted([p for p in prime_pool if p > y_max and p <= max_p_for_dlp])[:8]
    if not candidates_p:
        return {
            "predicted_x": None,
            "consistency_score": 0.0,
            "error": "No tractable p (use Pollard rho for large p)",
        }

    best = None
    for p in candidates_p:
        for a in range(2, min(p, max_a)):
            # Verify a^x_i ≡ y_i for all examples
            score = sum(1 for x, y in zip(xs, ys, strict=False) if pow(a, x, p) == y) / K
            if best is None or score > best["score"]:
                best = {"a": a, "p": p, "score": score}
            if score == 1.0:
                break
        if best and best["score"] == 1.0:
            break

    if best is None or best["score"] < 0.85:
        return {
            "predicted_x": None,
            "consistency_score": 0.0 if best is None else best["score"],
            "error": "No fit",
        }

    # Solve dlog: find x such that a^x ≡ qy mod p
    qy = int(query) if not isinstance(query, (list, tuple)) else int(query[0])
    a, p = best["a"], best["p"]
    # Brute force baby-step
    predicted_x = None
    val = 1
    for x_candidate in range(p):
        if val == qy:
            predicted_x = x_candidate
            break
        val = (val * a) % p

    return {
        "predicted_y": predicted_x,  # the discrete log
        "a": a,
        "p": p,
        "consistency_score": best["score"],
    }
