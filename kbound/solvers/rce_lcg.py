"""RCE-LCG symbolic solver — adapted from geometry-of-induction/src/eval_lcg_solvernet_v2.py.

Pure symbolic version (no neural prior) for v0. Searches over (m, a, c) candidates
ranked by support consistency. Works for LCG-style rules y = (a*x + c) mod m where
m belongs to a small pool of candidates (default: small primes).

If we want neural prior later, swap in the trained IterativeXattnLCG model from GCS.
"""

from __future__ import annotations

from collections import Counter

# Default prime pool — covers most common LCG moduli used in synthetic benchmarks
DEFAULT_PRIME_POOL = [
    2,
    3,
    5,
    7,
    11,
    13,
    17,
    19,
    23,
    29,
    31,
    37,
    41,
    43,
    47,
    53,
    59,
    61,
    67,
    71,
    73,
    79,
    83,
    89,
    97,
    101,
    103,
    107,
    109,
    113,
    127,
    131,
    137,
    139,
    149,
    151,
    157,
    163,
    167,
    173,
    179,
    181,
    191,
    193,
    197,
    199,
    211,
    223,
    227,
    229,
    233,
    239,
    241,
    251,
    257,
    263,
    269,
    271,
    277,
    281,
    283,
    293,
    307,
    311,
    313,
    317,
    331,
    337,
    347,
    349,
    353,
    359,
    367,
    373,
    379,
    383,
    389,
    397,
    401,
    409,
    419,
    421,
    431,
    433,
    439,
    443,
    449,
    457,
    461,
    463,
    467,
    479,
    487,
    491,
    499,
    503,
    509,
    521,
    523,
    541,
    547,
    557,
    563,
    569,
    571,
    577,
    587,
    593,
    599,
    601,
    607,
    613,
    617,
    619,
    631,
    641,
    643,
    647,
    653,
    659,
    661,
    673,
    677,
    683,
    691,
    701,
    709,
    719,
    727,
    733,
    739,
    743,
    751,
    757,
    761,
    769,
    773,
    787,
    797,
    809,
    811,
    821,
    823,
    827,
    829,
    839,
    853,
    857,
    859,
    863,
    877,
    881,
    883,
    887,
    907,
    911,
    919,
    929,
    937,
    941,
    947,
    953,
    967,
    971,
    977,
    983,
    991,
    997,
    1009,
]


def solve_lcg_symbolic(
    examples: list[tuple],
    query,
    prime_pool: list[int] | None = None,
    top_k_m: int = 8,
) -> dict:
    """Pool-aware symbolic LCG solver.

    1. Filter primes that exceed max(observed values).
    2. For each candidate m, sweep (a, c) and score by support consistency.
    3. Pick best (m, a, c) and apply to query.

    Returns: dict with predicted_y, m, a, c, consistency_score.
    """
    if prime_pool is None:
        prime_pool = DEFAULT_PRIME_POOL

    xs = [int(e[0]) if not isinstance(e[0], (list, tuple)) else int(e[0][0]) for e in examples]
    ys = [int(e[1]) for e in examples]

    # m only constrains ys (outputs are mod m), not xs (inputs can be anything)
    y_max = max(ys)
    compatible = [p for p in prime_pool if p > y_max]
    if not compatible:
        compatible = list(prime_pool)
    # Sort by smallest first (will hit small primes typical of synthetic LCGs)
    compatible.sort()
    m_candidates = compatible[:top_k_m]

    K = len(xs)
    best = None
    for m in m_candidates:
        for a in range(1, m):
            cs = [(ys[i] - a * xs[i]) % m for i in range(K)]
            counts = Counter(cs)
            c_mode, mode_count = counts.most_common(1)[0]
            score = mode_count / K
            if best is None or score > best["consistency_score"]:
                best = {"m": m, "a": a, "c": c_mode, "consistency_score": score}
            if score == 1.0:
                break
        if best and best["consistency_score"] == 1.0:
            break

    if best is None:
        return {
            "predicted_y": None,
            "m": None,
            "a": None,
            "c": None,
            "consistency_score": 0.0,
            "error": "No candidate m worked",
        }

    # Apply to query
    qx = int(query) if not isinstance(query, (list, tuple)) else int(query[0])
    predicted_y = (best["a"] * qx + best["c"]) % best["m"]

    return {
        "predicted_y": predicted_y,
        "m": best["m"],
        "a": best["a"],
        "c": best["c"],
        "consistency_score": best["consistency_score"],
    }
