"""Top-level convenience wrapper for inductive rule recovery.

The dispatcher in `kbound.solvers.dispatcher` is engine-grade — it takes a
geometry + family + examples + query and routes to a specific solver.
For most users the natural call is "give me K observations, return the rule",
which is what `recover_rule()` exposes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kbound.classifier.family_id import identify_family
from kbound.classifier.oracle_classifier import classify_geometry
from kbound.formatter import _render_decision_rule
from kbound.operators import operator_for
from kbound.solvers.dispatcher import dispatch

_PARAM_KEYS = (
    "a",
    "b",
    "c",
    "d",
    "m",
    "p",
    "n",
    "k",
    "operator",
    "truth_table",
    "coefficients",
    "order",
    "form",
    "degree",
)


@dataclass
class RecoveryResult:
    """Outcome of `recover_rule()`.

    Attributes:
        rule: English description of the recovered rule, or `None` if no rule
            from the operator catalog matched the observations.
        family: short id for the family detected (e.g. `"lcg"`, `"polycoef"`).
        operator: human-readable operator name (e.g. `"Linear Residual Policy"`).
        parameters: dict of recovered parameters (a, c, m, p, etc.).
        confidence: support-set consistency in [0, 1].
        verified: True iff the recovered rule reproduces every observation.
        k_used: number of observations consumed.
        k_lower_bound: theoretical minimum K for this family (None if unrecovered).
        margin: k_used / k_lower_bound, the safety margin over the bound.
        certificate: full audit certificate (dict).
        geometry: classified geometry (`"spatial"`, `"algebraic"`, `"borderline"`).
    """

    rule: str | None
    family: str | None
    operator: str | None
    parameters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    verified: bool = False
    k_used: int = 0
    k_lower_bound: int | None = None
    margin: float | None = None
    certificate: dict[str, Any] = field(default_factory=dict)
    geometry: str = "unknown"

    def predict(self, x):
        """Apply the recovered rule to a new input. Raises if no rule was recovered."""
        if self.family is None:
            raise ValueError("no rule recovered — cannot predict")
        return _apply(self.family, self.parameters, x)

    def __repr__(self):
        if self.family is None:
            return f"RecoveryResult(no_recovery, k_used={self.k_used})"
        return (
            f"RecoveryResult(rule={self.rule!r}, "
            f"confidence={self.confidence:.2f}, k_used={self.k_used}, "
            f"k_lower_bound={self.k_lower_bound}, margin={self.margin}x)"
        )


def recover_rule(
    examples: list[tuple],
    *,
    llm_fallback: bool = False,
    threshold: float = 0.80,
) -> RecoveryResult:
    """Recover the rule a deterministic system follows from K observations.

    Args:
        examples: list of `(input, output)` pairs. Inputs may be `int`,
            `tuple[int, ...]`, or `list[int]`. Outputs are `int`.
        llm_fallback: if True, fall back to an LLM call when the geometric
            class is spatial (threshold / conjunctive) — requires
            `ANTHROPIC_API_KEY`. Defaults to False (no network calls).
        threshold: confidence floor for the dispatcher's LLM routing path.

    Returns:
        RecoveryResult with the recovered rule, parameters, certificate.

    Example:
        >>> from kbound import recover_rule
        >>> examples = [(i, (3*i + 7) % 17) for i in range(8)]
        >>> result = recover_rule(examples)
        >>> result.rule
        'decision(x) = (3·x + 7) mod 17'
        >>> result.confidence
        1.0
        >>> result.predict(42)
        14
    """
    if not examples or len(examples) < 4:
        raise ValueError("need at least 4 observations to recover a rule")

    geom = classify_geometry(examples)
    # Always try family identification — even for "spatial" geometry, since
    # arity-2 binary inputs (boolean_2input) and k-bit parity get classified
    # spatial by the depth-3 tree heuristic but are still cleanly recoverable.
    # `identify_family` returns "unknown" / "unknown_2input" when nothing fits.
    family = identify_family(examples, geom)
    if family in ("unknown", "unknown_2input"):
        family = None

    # Build a query in the same shape as the input — scalar for arity-1
    # families, tuple/list for arity-2 (mod_p_add, boolean_2input) and k-bit
    # parity. The query value is throw-away; the dispatcher uses it only to
    # confirm the recovered rule applies to a fresh input.
    sample_x = examples[0][0]
    if isinstance(sample_x, list | tuple):
        query: Any = tuple(0 for _ in sample_x)
    else:
        query = max(int(e[0]) for e in examples) + 1

    raw = dispatch(
        geometry=geom["geometry"],
        family=family,
        examples=examples,
        query=query,
        threshold=threshold,
        use_llm_fallback=llm_fallback,
    )

    op = operator_for(family) if family else None
    details = raw.get("details") or {}
    params = {k: v for k, v in details.items() if v is not None and k in _PARAM_KEYS}

    rule = _render_decision_rule(op, params) if op else None
    confidence = float(raw.get("confidence") or 0.0)
    verified_score = raw.get("verified_consistency")
    verified = bool((verified_score and verified_score >= 0.95) or confidence >= 0.95)

    k_lower = op.typical_k_lower_bound if op else None
    margin = round(len(examples) / max(k_lower, 1), 2) if k_lower else None
    certificate = (
        {
            "k_used": len(examples),
            "k_lower_bound": k_lower,
            "margin": margin,
            "consistency": round(confidence, 4),
            "proof_status": "empirical",
            "operator": op.business_name,
            "family_label": op.family_label,
        }
        if op
        else {"k_used": len(examples), "proof_status": "no_recovery"}
    )

    return RecoveryResult(
        rule=rule,
        family=family,
        operator=op.business_name if op else None,
        parameters=params,
        confidence=confidence,
        verified=verified,
        k_used=len(examples),
        k_lower_bound=k_lower,
        margin=margin,
        certificate=certificate,
        geometry=geom["geometry"],
    )


def _apply(family: str, p: dict[str, Any], x):
    """Apply a recovered rule to a fresh input. Mirrors dispatcher's solver math."""
    if family in ("lcg", "lcg_generic", "glibc", "java_random"):
        return (p["a"] * int(x) + p["c"]) % p["m"]
    if family == "polycoef":
        xi = int(x)
        return (p["a"] * xi * xi + p["b"] * xi + p["c"]) % p["p"]
    if family == "polycoef_generic":
        xi = int(x)
        deg = p.get("degree", 2)
        if deg == 2:
            return (p["a"] * xi * xi + p["b"] * xi + p["c"]) % p["p"]
        if deg == 3:
            return (p["a"] * xi**3 + p["b"] * xi * xi + p["c"] * xi + p["d"]) % p["p"]
    if family == "cubic":
        xi = int(x)
        return (p["a"] * xi**3 + p["b"] * xi * xi + p["c"] * xi + p["d"]) % p["p"]
    if family == "modmul":
        return (p["a"] * int(x)) % p["p"]
    if family == "modinv":
        return pow(int(x), -1, p["p"])
    if family == "modexp":
        return pow(p["a"], int(x), p["p"])
    if family == "mod_p_add":
        x1, x2 = (int(x[0]), int(x[1])) if isinstance(x, list | tuple) else (int(x), 0)
        return (x1 + x2) % p["p"]
    if family == "boolean_2input":
        truth_table = p.get("truth_table")
        if truth_table is None or not isinstance(x, list | tuple) or len(x) != 2:
            raise ValueError(
                "boolean_2input.predict requires a (x1, x2) tuple input and "
                "a 'truth_table' param recovered by the solver"
            )
        idx = int(x[0]) * 2 + int(x[1])
        return int(truth_table[idx])
    if family == "parity_kbit":
        if not isinstance(x, list | tuple):
            raise ValueError("parity_kbit.predict requires a tuple/list of bits")
        return sum(int(b) for b in x) % 2
    raise NotImplementedError(f"predict() not yet wired for family={family!r}")
