"""Info-gain kernel for active query selection.

Core idea: after observing K (input, output) pairs, multiple candidate rules may
remain consistent with the data. The OPTIMAL next query is the input x* that
maximally splits the candidate posterior — i.e. maximizes expected entropy
reduction.

For a discrete posterior over rules {h_1, ..., h_M} with weights p_i:
    H(P) = -sum p_i log p_i

For candidate query x:
    For each predicted output y, compute conditional posterior P(h | obs ∪ {(x,y)})
    Expected entropy after query x = sum_y P(y) * H(P | y)
    Info gain = H(P) - E[H(P|y)]

We pick argmax over a candidate query pool.

This is textbook Bayesian experimental design (Lindley 1956). The novelty in
Kazdov is APPLYING it to cryptanalytic algebraic rule recovery, with K-bound
theory underpinning convergence guarantees.
"""

from __future__ import annotations

import math
from collections.abc import Iterable


def entropy(weights: Iterable[float]) -> float:
    """Shannon entropy of a discrete distribution. Weights need not be normalized."""
    total = sum(weights)
    if total <= 0:
        return 0.0
    H = 0.0
    for w in weights:
        if w <= 0:
            continue
        p = w / total
        H -= p * math.log2(p)
    return H


def filter_candidates(candidates: list, observations: list[tuple]) -> list:
    """Filter candidate rules to those consistent with all observations.

    Each candidate must implement .predict(x) → y. We discard any whose
    prediction disagrees with at least one observation.
    """
    survivors = []
    for cand in candidates:
        ok = True
        for x, y in observations:
            if cand.predict(x) != y:
                ok = False
                break
        if ok:
            survivors.append(cand)
    return survivors


def expected_info_gain(
    candidates: list,
    candidate_query: int,
    weights: list[float] | None = None,
) -> float:
    """Compute expected entropy reduction (info gain) from querying input `candidate_query`.

    For each surviving candidate, predict y = candidate.predict(candidate_query).
    Group candidates by predicted y. The entropy of the y-distribution IS the info gain
    (since after observation, posterior collapses to the matching y-bucket).

    Equivalent formulation: H(Y | x) where Y is the random variable over predicted outputs
    when the rule is sampled from the current posterior.
    """
    if not candidates:
        return 0.0
    if weights is None:
        weights = [1.0] * len(candidates)

    bucket_weights: dict = {}
    for cand, w in zip(candidates, weights, strict=False):
        try:
            y_pred = cand.predict(candidate_query)
        except Exception:
            continue
        bucket_weights[y_pred] = bucket_weights.get(y_pred, 0) + w

    return entropy(bucket_weights.values())


def best_query(
    candidates: list,
    query_pool: Iterable[int],
    weights: list[float] | None = None,
) -> tuple[int, float]:
    """Pick the query that maximizes expected info gain.

    Returns (best_x, info_gain_in_bits).
    """
    best_x = None
    best_gain = -1.0
    for x in query_pool:
        g = expected_info_gain(candidates, x, weights)
        if g > best_gain:
            best_gain = g
            best_x = x
    return best_x, best_gain


# LCGCandidate / enumerate_lcg_candidates lived here as a proof-of-concept and
# duplicated kbound.active.posterior.LCGCandidate. They were never imported
# outside this file, so the duplicate has been removed. The canonical version
# lives in kbound.active.posterior with proper Candidate-base inheritance.
