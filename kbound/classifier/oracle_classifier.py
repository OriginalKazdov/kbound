"""Oracle (geometry) classifier — Python port of the TS oracle in kazdov-oracle-public.

Mirrors the same logic: extract 6 features, classify geometry, lookup calibration.
"""

from __future__ import annotations

from collections import Counter

# Calibration table — empirical from paper #1 (Dovzak 2026)
CAL = {
    "spatial": {
        "≤4": {
            "haiku-4-5": 0.84,
            "sonnet-4-6": 1.00,
            "opus-4-7": 0.96,
            "gpt-4o-mini": 0.80,
            "llama-3-3": 0.78,
        },
        "≤50": {
            "haiku-4-5": 1.00,
            "sonnet-4-6": 1.00,
            "opus-4-7": 1.00,
            "gpt-4o-mini": 0.70,
            "llama-3-3": 0.65,
        },
        ">50": {
            "haiku-4-5": 0.85,
            "sonnet-4-6": 0.90,
            "opus-4-7": 0.90,
            "gpt-4o-mini": 0.55,
            "llama-3-3": 0.50,
        },
    },
    "algebraic": {
        "≤4": {
            "haiku-4-5": 0.22,
            "sonnet-4-6": 0.34,
            "opus-4-7": 0.30,
            "gpt-4o-mini": 0.18,
            "llama-3-3": 0.20,
        },
        "≤50": {
            "haiku-4-5": 0.00,
            "sonnet-4-6": 0.04,
            "opus-4-7": 0.05,
            "gpt-4o-mini": 0.04,
            "llama-3-3": 0.03,
        },
        ">50": {
            "haiku-4-5": 0.18,
            "sonnet-4-6": 0.20,
            "opus-4-7": 0.20,
            "gpt-4o-mini": 0.20,
            "llama-3-3": 0.15,
        },
    },
}

COSTS = {
    "haiku-4-5": 0.005,
    "sonnet-4-6": 0.025,
    "opus-4-7": 0.080,
    "gpt-4o-mini": 0.001,
    "llama-3-3": 0.000,
}


def _to_vec(x):
    """Normalize input to list of ints."""
    if isinstance(x, (int, float)):
        return [int(x)]
    return [int(v) for v in x]


def _detect_modular_wrap(xs: list[int], ys: list[int]) -> int:
    """Try y = ((a*x + c) mod m) mod K for small (a, c, m). 1 if any fit > 85%."""
    if len(xs) < 8:
        return 0
    K = len(set(ys))
    if K < 2:
        return 0
    best = 0.0
    for m in range(4, 50):
        for a in range(1, min(m, 30)):
            for c in range(0, min(m, 30)):
                preds = [((a * x + c) % m) % K for x in xs]
                acc = sum(p == y for p, y in zip(preds, ys, strict=False)) / len(xs)
                if acc > best:
                    best = acc
                    if best > 0.95:
                        return 1
    return 1 if best > 0.85 else 0


def _detect_recurrence(xs: list[int], ys: list[int]) -> int:
    """y_i appears as x_{i+1} more than 50% of time."""
    if len(xs) < 4:
        return 0
    matches = sum(1 for i in range(len(xs) - 1) if ys[i] == xs[i + 1])
    return 1 if matches >= 0.5 * (len(xs) - 1) else 0


def _detect_spatial_separable(X: list[list[int]], ys: list[int]) -> int:
    """Path 1: 1D + monotone => separable.
    Path 2: depth-3 axis-aligned tree ≥90% — restricted to low-cardinality (K ≤ 3)
    classification tasks, since for K > 3 a depth-3 tree can over-fit any small dataset.
    """
    n = len(X)
    if n < 8:
        return 0
    arity = len(X[0])
    K = len(set(ys))

    if arity == 1 and K > 4:
        order = sorted(range(n), key=lambda i: X[i][0])
        ys_sorted = [ys[i] for i in order]
        non_dec = all(ys_sorted[i] >= ys_sorted[i - 1] for i in range(1, n))
        non_inc = all(ys_sorted[i] <= ys_sorted[i - 1] for i in range(1, n))
        if non_dec or non_inc:
            return 1

    # Depth-3 tree fit — only meaningful when K is small (binary/ternary classification).
    # Modular-arithmetic rules can have K up to m which would over-fit here.
    if K > 3:
        return 0

    def fit(idx: list[int], depth: int) -> int:
        if not idx:
            return 0
        local_y = [ys[i] for i in idx]
        if depth == 0 or len(set(local_y)) == 1:
            modal = Counter(local_y).most_common(1)[0][0]
            return sum(1 for y in local_y if y == modal)
        best = max(Counter(local_y).values())
        for d in range(arity):
            vals = sorted(set(X[i][d] for i in idx))
            for s in range(len(vals) - 1):
                T = vals[s]
                left = [i for i in idx if X[i][d] <= T]
                right = [i for i in idx if X[i][d] > T]
                if not left or not right:
                    continue
                total = fit(left, depth - 1) + fit(right, depth - 1)
                if total > best:
                    best = total
        return best

    correct = fit(list(range(n)), 3)
    return 1 if correct / n >= 0.9 else 0


def _bucket(c: int) -> str:
    if c <= 4:
        return "≤4"
    if c <= 50:
        return "≤50"
    return ">50"


def classify_geometry(examples: list[tuple]) -> dict:
    """Classify geometry of an in-context task.

    Returns dict with: geometry, features, per_model_accuracy, recommended_model.
    """
    xs_raw = [e[0] for e in examples]
    ys = [int(e[1]) for e in examples]

    arity = len(_to_vec(xs_raw[0]))
    X = [_to_vec(x) for x in xs_raw]
    K = len(set(ys))

    if arity == 1:
        xs1 = [row[0] for row in X]
        has_mod = _detect_modular_wrap(xs1, ys)
        has_rec = _detect_recurrence(xs1, ys)
    else:
        has_mod = 0
        has_rec = 0
    separable = _detect_spatial_separable(X, ys)

    # Classify (priority: spatial > algebraic > borderline)
    if separable:
        geometry = "spatial"
    elif has_mod or has_rec or K > 2:
        geometry = "algebraic"
    else:
        geometry = "borderline"

    bucket = _bucket(K)
    cal_key = geometry if geometry != "borderline" else "algebraic"
    per_model = CAL[cal_key][bucket].copy()

    # Cheapest model above threshold
    sorted_models = sorted(COSTS.items(), key=lambda kv: kv[1])
    rec_model = None
    rec_acc = None
    for m, _ in sorted_models:
        if per_model.get(m, 0) >= 0.80:
            rec_model = m
            rec_acc = per_model[m]
            break

    return {
        "geometry": geometry,
        "features": {
            "output_cardinality": K,
            "input_arity": arity,
            "has_modular_wrap": has_mod,
            "has_recurrence": has_rec,
            "is_spatial_separable": separable,
        },
        "output_cardinality_bucket": bucket,
        "per_model_accuracy": per_model,
        "recommended_model": rec_model,
        "recommended_accuracy": rec_acc,
    }
