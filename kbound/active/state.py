"""Active session state machine.

Lifecycle:
    1. session = ActiveSession(initial_observations)
    2. session.candidates → list of consistent rules
    3. session.suggest_query(query_pool) → x* with maximum info gain
    4. user runs x* externally, returns y
    5. session.add_observation(x*, y) → candidates filtered
    6. loop until len(session.candidates) == 1 or pool exhausted

Termination criteria:
    - unique_model: exactly 1 candidate remains → predict the answer
    - exhausted: query pool exhausted but >1 candidate remains
    - bound_reached: K-bound reached (paper #3 lower-bound theory)
"""

from __future__ import annotations

import time

from kbound.active.info_gain import (
    best_query,
    entropy,
)
from kbound.active.posterior import (
    build_initial_pool,
    reduce_to_unique_or_lower,
)


class ActiveSession:
    """Stateful active rule-recovery session."""

    def __init__(
        self,
        observations: list[tuple],
        families: list[str] | None = None,
        max_candidates: int = 50000,
    ):
        self.observations = list(observations)
        self.families = families
        self.max_candidates = max_candidates
        self.history: list[dict] = []  # log of suggested queries + outcomes

        t0 = time.perf_counter()
        self.candidates = build_initial_pool(self.observations, families=self.families)
        # Always reduce to functionally distinct candidates — equivalent rules
        # (different params, same predictions on a probe set) are merged.
        self.candidates = reduce_to_unique_or_lower(self.candidates)
        self.elapsed_ms = (time.perf_counter() - t0) * 1000

    @property
    def n_candidates(self) -> int:
        return len(self.candidates)

    @property
    def is_unique(self) -> bool:
        return len(self.candidates) == 1

    @property
    def is_failed(self) -> bool:
        return len(self.candidates) == 0

    def predict_unique(self, x):
        """If exactly one candidate remains, predict its output for x."""
        if not self.is_unique:
            return None
        return self.candidates[0].predict(x)

    def family_distribution(self) -> dict[str, int]:
        """Count of surviving candidates by family."""
        counts: dict[str, int] = {}
        for c in self.candidates:
            counts[c.family] = counts.get(c.family, 0) + 1
        return counts

    def current_entropy_bits(self) -> float:
        """Shannon entropy over surviving candidates (uniform prior)."""
        return entropy([1.0] * self.n_candidates) if self.n_candidates else 0.0

    def suggest_query(
        self,
        query_pool: list[int] | None = None,
        avoid_already_observed: bool = True,
    ) -> dict:
        """Pick the input that maximizes expected info gain.

        Returns dict with: suggested_x, info_gain_bits, n_candidates, family_split, elapsed_ms.
        """
        if self.is_unique or self.is_failed:
            return {
                "suggested_x": None,
                "info_gain_bits": 0.0,
                "reason": "unique" if self.is_unique else "no candidates",
                "n_candidates": self.n_candidates,
            }

        if query_pool is None:
            # Default: scan inputs 0..200 plus a few large probes
            query_pool = list(range(0, 201)) + [500, 1000, 9999]

        already = {x for x, _ in self.observations}
        if avoid_already_observed:
            query_pool = [x for x in query_pool if x not in already]

        t0 = time.perf_counter()
        best_x, gain = best_query(self.candidates, query_pool)
        elapsed = (time.perf_counter() - t0) * 1000

        # Predict possible outcomes (helpful for the UI)
        outcomes: dict[int, int] = {}
        for c in self.candidates:
            try:
                y_pred = c.predict(best_x)
                outcomes[y_pred] = outcomes.get(y_pred, 0) + 1
            except Exception:
                continue

        return {
            "suggested_x": best_x,
            "info_gain_bits": gain,
            "n_candidates": self.n_candidates,
            "family_split": self.family_distribution(),
            "predicted_outcomes": outcomes,
            "elapsed_ms": elapsed,
        }

    def add_observation(self, x, y):
        """User ran x externally; add the observed y. Filter + reduce candidates."""
        self.observations.append((x, y))
        self.candidates = [c for c in self.candidates if c.predict(x) == y]
        # Re-reduce: filtering may have left equivalent forms, collapse them
        self.candidates = reduce_to_unique_or_lower(self.candidates)
        self.history.append(
            {"step": len(self.history) + 1, "x": x, "y": y, "n_candidates_after": self.n_candidates}
        )

    def k_used(self) -> int:
        return len(self.observations)

    def summary(self) -> dict:
        return {
            "k_used": self.k_used(),
            "n_candidates": self.n_candidates,
            "is_unique": self.is_unique,
            "family_split": self.family_distribution(),
            "entropy_bits": self.current_entropy_bits(),
            "history": self.history,
            "candidates": [repr(c) for c in self.candidates[:10]],
        }
