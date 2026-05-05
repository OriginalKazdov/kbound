"""Active query over COMPOSITIONS — the genuine novelty.

Existing active learning works over single-rule posteriors. Existing composition
discovery works passively over a fixed K. We combine: maintain a posterior over
*compositions* (depth ≤ 2 typed atom chains), and pick the next query that
maximally disambiguates candidate compositions.

To my knowledge, no published or open-source system does this. The core theory
(Bayesian experimental design) is textbook, but applying it to typed
compositional cryptanalytic primitives is — as far as I have surveyed — new.

The recipe:
  1. Enumerate ALL compositions (atomic + depth-2 fused) consistent with the
     initial K observations.
  2. Functional-equivalence reduction: collapse compositions that produce
     identical outputs across a probe set.
  3. For each candidate query x in a pool, group remaining compositions by
     predicted y. Entropy of this grouping = info gain.
  4. Pick the x that maximizes info gain.
  5. User runs x, returns y. Filter candidates. Loop.

Termination: |candidates| == 1, or no further info gain, or K-bound exceeded.
"""

from __future__ import annotations

import math
import time

from kbound.compositional.atoms import ATOMS, SMALL_PRIMES
from kbound.compositional.search import (
    ALL_ATOMS,
    _format_expression,
)

# ============================================================
# Composition object: a uniform representation of single-atom + depth-2 forms
# ============================================================


class Composition:
    """Represents a depth-1 or depth-2 composition with concrete params.

    forward(x) → applies the chain.
    """

    def __init__(self, atoms: list[str], params: list[dict]):
        assert len(atoms) == len(params)
        assert 1 <= len(atoms) <= 3
        self.atoms = atoms
        self.params = params

    def forward(self, x):
        z = x
        for atom_name, p in zip(self.atoms, self.params, strict=False):
            z = ATOMS[atom_name].forward(z, p)
        return z

    def __repr__(self):
        if len(self.atoms) == 1:
            return f"{self.atoms[0]}({self.params[0]})"
        # depth-2: render as nested
        inner = self.atoms[0]
        outer = self.atoms[1]
        ip = self.params[0]
        op = self.params[1]
        return _format_expression(inner, ip, outer, op)


# ============================================================
# Enumerate candidate compositions consistent with observations
# ============================================================


def enumerate_consistent_compositions(
    observations: list[tuple[int, int]],
    max_depth: int = 2,
    max_per_family: int = 200,
) -> list[Composition]:
    """Build the candidate pool of compositions consistent with K observations.

    Strategy: for each atom and each common composition family, brute-force over
    the parameter grid and keep params that match all observations.
    """
    if not observations:
        return []
    ys = [y for _, y in observations]
    ymax = max(ys)

    candidates: list[Composition] = []

    # Depth-1: each atom alone
    for atom_name in ALL_ATOMS:
        atom = ATOMS[atom_name]
        param_candidates = atom.param_search(observations)
        for params, score in param_candidates[:max_per_family]:
            if score >= 0.999:
                candidates.append(Composition([atom_name], [params]))

    if max_depth < 2:
        return _reduce_equivalent(candidates)

    # Depth-2 fused — direct joint enumeration
    # Pattern A: y = ((a·x + c) mod m) mod n
    for m in SMALL_PRIMES:
        for n in range(2, m):
            if n <= ymax:
                continue
            for a in range(1, m):
                for c in range(0, m):
                    if all((((a * x + c) % m) % n) == y for x, y in observations):
                        candidates.append(
                            Composition(
                                ["affine_mod", "mod_reduce"],
                                [{"a": a, "c": c, "m": m}, {"n": n}],
                            )
                        )

    # Pattern B: y = (a · x^k + c) mod p
    for k in (2, 3, 4, 5):
        for p in SMALL_PRIMES:
            if p <= ymax:
                continue
            for a in range(1, p):
                for c in range(0, p):
                    if all((a * (x**k) + c) % p == y for x, y in observations):
                        candidates.append(
                            Composition(
                                ["power", "affine_mod"],
                                [{"k": k}, {"a": a, "c": c, "m": p}],
                            )
                        )

    # Pattern C: y = (a·(x + offset) + c) mod m
    for m in SMALL_PRIMES:
        if m <= ymax:
            continue
        for offset in range(-15, 16):
            if offset == 0:
                continue
            for a in range(1, m):
                for c in range(0, m):
                    if all((a * (x + offset) + c) % m == y for x, y in observations):
                        candidates.append(
                            Composition(
                                ["const_add", "affine_mod"],
                                [{"c": offset}, {"a": a, "c": c, "m": m}],
                            )
                        )

    # Pattern D: y = (a·(x ^ const) + c) mod m  (XOR + AffineMod)
    for m in SMALL_PRIMES:
        if m <= ymax:
            continue
        for xor_const in range(0, 64):
            if xor_const == 0:
                continue
            for a in range(1, m):
                for c in range(0, m):
                    if all((a * (x ^ xor_const) + c) % m == y for x, y in observations):
                        candidates.append(
                            Composition(
                                ["xor_const", "affine_mod"],
                                [{"c": xor_const}, {"a": a, "c": c, "m": m}],
                            )
                        )

    return _reduce_equivalent(candidates)


def _reduce_equivalent(candidates: list[Composition]) -> list[Composition]:
    """Collapse functionally equivalent compositions.

    Two compositions producing the same output on a wide probe set are equivalent
    for the auditor's purpose; keep one representative (preferring depth-1 over
    depth-2, smaller params).
    """
    if not candidates:
        return []
    probes = list(range(0, 201)) + [500, 999, 4096, 50000]
    seen: dict = {}
    for c in candidates:
        try:
            sig = tuple(c.forward(x) for x in probes)
        except Exception:
            continue
        if sig not in seen:
            seen[sig] = c
        else:
            # Prefer simpler (shallower depth, smaller modulus)
            existing = seen[sig]
            cur_depth = len(c.atoms)
            ex_depth = len(existing.atoms)
            if cur_depth < ex_depth:
                seen[sig] = c
            elif cur_depth == ex_depth:
                # depth tied: keep one with smaller params (modulus, then absolute coeffs)
                cur_score = _complexity(c)
                ex_score = _complexity(existing)
                if cur_score < ex_score:
                    seen[sig] = c
    return list(seen.values())


def _complexity(c: Composition) -> int:
    """Simple complexity score: smaller = simpler representative."""
    score = 0
    for _atom_name, p in zip(c.atoms, c.params, strict=False):
        m = p.get("m", 0) or p.get("p", 0) or p.get("n", 0)
        score += m * 100 + sum(abs(v) for v in p.values() if isinstance(v, int))
    return score


# ============================================================
# Info-gain over compositions
# ============================================================


def expected_info_gain_compose(
    candidates: list[Composition],
    candidate_query: int,
) -> float:
    """Entropy of the predicted-y distribution at candidate_query, with uniform prior."""
    if not candidates:
        return 0.0
    bucket: dict = {}
    for c in candidates:
        try:
            y_pred = c.forward(candidate_query)
        except Exception:
            continue
        bucket[y_pred] = bucket.get(y_pred, 0) + 1
    total = sum(bucket.values())
    if total == 0:
        return 0.0
    H = 0.0
    for w in bucket.values():
        p = w / total
        if p > 0:
            H -= p * math.log2(p)
    return H


def best_query_compose(candidates: list[Composition], query_pool: list[int]) -> tuple[int, float]:
    best_x = None
    best_g = -1.0
    for x in query_pool:
        g = expected_info_gain_compose(candidates, x)
        if g > best_g:
            best_g = g
            best_x = x
    return best_x, best_g


# ============================================================
# Depth-bound certificate
# ============================================================


def depth_bound_certificate(K: int) -> dict:
    """Heuristic depth bound from K.

    Heuristic: each atom has ≤ 3 unknown params (AffineMod). Depth-D composition
    has ≤ 3D params. For unique recovery with margin, K ≥ 3D + 1 → D ≤ floor((K-1)/3).

    A tighter bound requires paper #3's compiler-theoretic K-bound theory.
    """
    D_safe = max(0, (K - 1) // 3)
    return {
        "K_observed": K,
        "max_depth_safe": D_safe,
        "rule": "K ≥ 3·D + 1 (heuristic, atoms with ≤ 3 params each)",
        "tight_bound": "see paper #3 (Compiler-Theoretic K-bound) for proven version",
    }


# ============================================================
# Active session over compositions
# ============================================================


class ActiveCompositionSession:
    """Stateful active rule recovery — over compositions, not just atoms."""

    def __init__(self, observations: list[tuple[int, int]], max_depth: int = 2):
        self.observations = list(observations)
        self.max_depth = max_depth
        self.history: list[dict] = []

        t0 = time.perf_counter()
        self.candidates = enumerate_consistent_compositions(self.observations, max_depth=max_depth)
        self.elapsed_ms = (time.perf_counter() - t0) * 1000
        self.cert = depth_bound_certificate(len(self.observations))

    @property
    def n_candidates(self) -> int:
        return len(self.candidates)

    @property
    def is_unique(self) -> bool:
        return self.n_candidates == 1

    @property
    def is_failed(self) -> bool:
        return self.n_candidates == 0

    def family_distribution(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in self.candidates:
            key = " ∘ ".join(c.atoms)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def suggest_query(self, query_pool: list[int] | None = None) -> dict:
        if self.is_unique or self.is_failed:
            return {
                "suggested_x": None,
                "info_gain_bits": 0.0,
                "n_candidates": self.n_candidates,
                "reason": "unique" if self.is_unique else "no candidates",
            }
        if query_pool is None:
            query_pool = list(range(0, 201)) + [500, 1000, 9999]
        already = {x for x, _ in self.observations}
        query_pool = [x for x in query_pool if x not in already]

        t0 = time.perf_counter()
        best_x, gain = best_query_compose(self.candidates, query_pool)
        elapsed = (time.perf_counter() - t0) * 1000

        outcomes: dict = {}
        for c in self.candidates:
            try:
                y_pred = c.forward(best_x)
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
        self.observations.append((x, y))
        self.candidates = [c for c in self.candidates if c.forward(x) == y]
        self.candidates = _reduce_equivalent(self.candidates)
        self.history.append(
            {"step": len(self.history) + 1, "x": x, "y": y, "n_candidates_after": self.n_candidates}
        )
        self.cert = depth_bound_certificate(len(self.observations))

    def predict_unique(self, x):
        if not self.is_unique:
            return None
        return self.candidates[0].forward(x)

    def summary(self) -> dict:
        return {
            "k_used": len(self.observations),
            "n_candidates": self.n_candidates,
            "is_unique": self.is_unique,
            "family_split": self.family_distribution(),
            "depth_bound_certificate": self.cert,
            "history": self.history,
            "candidates_preview": [repr(c) for c in self.candidates[:10]],
        }
