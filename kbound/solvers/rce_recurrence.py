"""RCE-Recurrence symbolic solver — for linear recurrences over finite fields.

Handles:
  - Fibonacci-like:  y_n = (y_{n-1} + y_{n-2}) mod m
  - General linear:  y_n = (a*y_{n-1} + b*y_{n-2}) mod m

Input format: examples are (n, value) pairs where n is the position and value is
the sequence element. The full sequence is determined by initial conditions + (a, b, m).

Method:
  1. Sort examples by n.
  2. For each candidate (a, b, m), reconstruct sequence from earliest n forward.
  3. Score by support consistency.
  4. Apply to query position.
"""

from __future__ import annotations

from kbound.solvers.rce_lcg import DEFAULT_PRIME_POOL


def solve_recurrence_symbolic(
    examples: list[tuple], query, prime_pool: list[int] | None = None, fibonacci_only: bool = False
) -> dict:
    """Try y_n = (a*y_{n-1} + b*y_{n-2}) mod m on (n, val) pairs."""
    if prime_pool is None:
        prime_pool = DEFAULT_PRIME_POOL

    # Examples are (position, value)
    sorted_pairs = sorted(
        examples, key=lambda p: int(p[0]) if not isinstance(p[0], (list, tuple)) else int(p[0][0])
    )
    ns = [int(p[0]) if not isinstance(p[0], (list, tuple)) else int(p[0][0]) for p in sorted_pairs]
    vals = [int(p[1]) for p in sorted_pairs]

    # Need at least 2 consecutive positions to seed the recurrence
    K = len(ns)
    if K < 4:
        return {"predicted_y": None, "consistency_score": 0.0, "error": "Need ≥4 examples"}

    y_max = max(vals)
    primes = sorted([p for p in prime_pool if p > y_max])[:10]

    qn = int(query) if not isinstance(query, (list, tuple)) else int(query[0])

    best = None
    a_range = [1] if fibonacci_only else range(1, 10)
    b_range = [1] if fibonacci_only else range(1, 10)

    for m in primes:
        for a in a_range:
            for b in b_range:
                # Try to reconstruct sequence over positions covered + query
                # Find 2 consecutive observed positions to seed
                seeds = None
                for i in range(K - 1):
                    if ns[i + 1] == ns[i] + 1:
                        seeds = (ns[i], vals[i], vals[i + 1])
                        break
                if seeds is None:
                    # No consecutive pair → fall back: assume seq starts at min n
                    # and just iterate from first 2 known
                    pass

                # Build full sequence from min(ns) to max(ns ∪ {qn})
                n_min = min(ns)
                n_max = max(max(ns), qn)
                seq_len = n_max - n_min + 1
                if seq_len < 2:
                    continue

                # Initial conditions: use first 2 observed values that are at consecutive positions
                # If not consecutive, this approach may not converge — skip
                seq = {}
                if seeds is not None:
                    seq[seeds[0]] = seeds[1]
                    seq[seeds[0] + 1] = seeds[2]
                    # Forward-fill
                    for n in range(seeds[0] + 2, n_max + 1):
                        seq[n] = (a * seq[n - 1] + b * seq[n - 2]) % m
                    # Back-fill (if needed): y_{n-2} = (y_n - a*y_{n-1}) * b^{-1} mod m
                    # For simplicity, only forward-fill for v0; require seeds at smallest n
                    # If first seeds not at n_min, skip
                    if seeds[0] > n_min:
                        # Fall through; backward fill is complex w/ b inverses
                        continue
                else:
                    continue

                # Score
                match = 0
                for n, v in zip(ns, vals, strict=False):
                    if seq.get(n) == v:
                        match += 1
                score = match / K

                if best is None or score > best["score"]:
                    best = {"a": a, "b": b, "m": m, "score": score, "qy": seq.get(qn)}
                if score == 1.0:
                    break
            if best and best["score"] == 1.0:
                break
        if best and best["score"] == 1.0:
            break

    if best is None or best["score"] < 0.85:
        return {
            "predicted_y": None,
            "consistency_score": 0.0 if best is None else best["score"],
            "error": "No fit",
        }

    return {
        "predicted_y": best["qy"],
        "a": best["a"],
        "b": best["b"],
        "m": best["m"],
        "consistency_score": best["score"],
    }
