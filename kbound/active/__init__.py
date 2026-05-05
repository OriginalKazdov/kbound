"""Active rule-recovery layer.

Public surface:

    ActiveSession              — stateful session over a candidate pool
    LCGCandidate / PolycoefCandidate / ModMulCandidate / ModExpCandidate
                               — typed candidates implementing predict(x)
    build_initial_pool         — enumerate consistent candidates from observations
    reduce_to_unique_or_lower  — collapse functionally-equivalent candidates
    best_query                 — pick next-best query that maximizes info gain
    entropy                    — Shannon entropy helper
"""

from kbound.active.info_gain import best_query, entropy, expected_info_gain
from kbound.active.posterior import (
    Candidate,
    LCGCandidate,
    ModExpCandidate,
    ModMulCandidate,
    PolycoefCandidate,
    build_initial_pool,
    reduce_to_unique_or_lower,
)
from kbound.active.state import ActiveSession

__all__ = [
    "ActiveSession",
    "Candidate",
    "LCGCandidate",
    "PolycoefCandidate",
    "ModMulCandidate",
    "ModExpCandidate",
    "build_initial_pool",
    "reduce_to_unique_or_lower",
    "best_query",
    "entropy",
    "expected_info_gain",
]
