"""RCE-Boolean symbolic solver — for 2-input Boolean rules over {0,1}.

Tries all 16 truth tables (functions f: {0,1}² → {0,1}) and picks the one matching
the support set perfectly. Covers AND, OR, XOR, NAND, NOR, XNOR, IMP_AB, IMP_BA, etc.

Also handles k-input parity (y = x_1 XOR x_2 XOR ... XOR x_k).
"""

from __future__ import annotations

# All 16 binary truth tables (a, b) in {(0,0), (0,1), (1,0), (1,1)} → output
# We label each by the 4-bit truth table read in this order
TRUTH_TABLES_2INPUT = {
    "FALSE": (0, 0, 0, 0),
    "AND": (0, 0, 0, 1),
    "AND_NB": (0, 0, 1, 0),  # A AND NOT B
    "A": (0, 0, 1, 1),
    "NA_AND": (0, 1, 0, 0),  # NOT A AND B
    "B": (0, 1, 0, 1),
    "XOR": (0, 1, 1, 0),
    "OR": (0, 1, 1, 1),
    "NOR": (1, 0, 0, 0),
    "XNOR": (1, 0, 0, 1),
    "NOT_B": (1, 0, 1, 0),
    "IMP_BA": (1, 0, 1, 1),  # if B then A (NOT B OR A)
    "NOT_A": (1, 1, 0, 0),
    "IMP_AB": (1, 1, 0, 1),
    "NAND": (1, 1, 1, 0),
    "TRUE": (1, 1, 1, 1),
}


def _eval_tt(tt: tuple[int, int, int, int], a: int, b: int) -> int:
    """tt is (f(0,0), f(0,1), f(1,0), f(1,1))."""
    return tt[2 * a + b]


def solve_boolean_2input(examples: list[tuple], query) -> dict:
    """Try all 16 binary truth tables on 2-input Boolean data."""
    pairs = []
    for x, y in examples:
        if not isinstance(x, (list, tuple)) or len(x) != 2:
            return {
                "predicted_y": None,
                "consistency_score": 0.0,
                "error": "Boolean 2-input requires (a, b) → c",
            }
        a, b = int(x[0]), int(x[1])
        if a not in (0, 1) or b not in (0, 1) or int(y) not in (0, 1):
            return {
                "predicted_y": None,
                "consistency_score": 0.0,
                "error": "Boolean requires inputs/outputs in {0,1}",
            }
        pairs.append((a, b, int(y)))

    K = len(pairs)
    best = None
    for name, tt in TRUTH_TABLES_2INPUT.items():
        match = sum(1 for a, b, y in pairs if _eval_tt(tt, a, b) == y)
        score = match / K
        if best is None or score > best["score"]:
            best = {"name": name, "tt": tt, "score": score}
        if score == 1.0:
            break

    if best is None or best["score"] < 0.95:
        return {
            "predicted_y": None,
            "consistency_score": 0.0 if best is None else best["score"],
            "error": "No consistent truth table",
        }

    if not isinstance(query, (list, tuple)) or len(query) != 2:
        return {
            "predicted_y": None,
            "consistency_score": best["score"],
            "error": "Query must be (a, b)",
        }
    qa, qb = int(query[0]), int(query[1])
    predicted_y = _eval_tt(best["tt"], qa, qb)

    return {
        "predicted_y": predicted_y,
        "operator": best["name"],
        "truth_table": list(best["tt"]),
        "consistency_score": best["score"],
    }


def solve_parity_kbit(examples: list[tuple], query) -> dict:
    """Try y = x_1 XOR x_2 XOR ... XOR x_k for k-bit input vectors."""
    pairs = []
    for x, y in examples:
        if not isinstance(x, (list, tuple)):
            return {
                "predicted_y": None,
                "consistency_score": 0.0,
                "error": "Parity requires vector input",
            }
        bits = [int(b) for b in x]
        if any(b not in (0, 1) for b in bits) or int(y) not in (0, 1):
            return {
                "predicted_y": None,
                "consistency_score": 0.0,
                "error": "Parity requires {0,1} bits",
            }
        pairs.append((bits, int(y)))

    K = len(pairs)
    # Compute parity: XOR of all bits
    match = sum(1 for bits, y in pairs if (sum(bits) % 2) == y)
    score = match / K
    if score < 0.95:
        # Try inverted parity
        match_inv = sum(1 for bits, y in pairs if (sum(bits) % 2) == (1 - y))
        score_inv = match_inv / K
        if score_inv > 0.95:
            qbits = [int(b) for b in query] if isinstance(query, (list, tuple)) else [int(query)]
            predicted_y = 1 - (sum(qbits) % 2)
            return {
                "predicted_y": predicted_y,
                "operator": "NOT_PARITY",
                "consistency_score": score_inv,
            }
        return {
            "predicted_y": None,
            "consistency_score": max(score, score_inv),
            "error": "Not parity-like",
        }

    qbits = [int(b) for b in query] if isinstance(query, (list, tuple)) else [int(query)]
    predicted_y = sum(qbits) % 2
    return {"predicted_y": predicted_y, "operator": "PARITY", "consistency_score": score}
