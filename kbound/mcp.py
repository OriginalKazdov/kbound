"""kbound MCP server — exposes inductive rule recovery as tools that any
MCP-aware AI agent (Claude Desktop, Claude Code, Cursor, Cline, …) can call.

Why this matters
================
Frontier LLMs fail at K-shot induction over algebraically-coupled rules
(see Dovzak 2026: spatial 0.88 vs algebraic 0.02 in-context accuracy at
K=16). Wrapping kbound as an MCP server gives those agents a deterministic
side-channel: instead of guessing the rule from K observations, they call
`recover_rule_from_observations` and get back the closed-form rule plus a
sample-complexity certificate.

Run as a stdio MCP server (the standard for Claude Desktop / Cursor):

    kbound-mcp                # console script entrypoint
    python -m kbound.mcp      # equivalent

Add to Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`
on macOS):

    {
      "mcpServers": {
        "kbound": {
          "command": "kbound-mcp"
        }
      }
    }

Requires the `mcp` extra: `pip install kbound[mcp]`.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from kbound import (
    OPERATORS,
    ClaimedSpec,
    check_compliance,
    classify_geometry,
    identify_family,
    recover_rule,
)

mcp = FastMCP("kbound")


def _normalize_observations(observations: list[list]) -> list[tuple]:
    """Convert JSON-shaped observations into the (input, output) tuples kbound expects.

    JSON has no tuple type, so multi-input families arrive as nested lists:
        [[0, 7], [1, 10], [2, 13], ...]                          # arity-1 (LCG, polycoef, …)
        [[[0, 0], 0], [[0, 1], 1], [[1, 0], 1], [[1, 1], 0], ...] # arity-2 (mod_p_add, boolean)

    We coerce the nested list inputs into tuples; outputs are forced to int.
    """
    pairs = []
    for obs in observations:
        if len(obs) != 2:
            raise ValueError(
                f"each observation must be a 2-element [input, output] pair, got {obs!r}"
            )
        x, y = obs[0], obs[1]
        if isinstance(x, list):
            x = tuple(x)
        pairs.append((x, int(y)))
    return pairs


# ─── Tools ─────────────────────────────────────────────────────────


@mcp.tool()
def recover_rule_from_observations(observations: list[list]) -> dict[str, Any]:
    """Recover the deterministic rule a system follows from K input/output observations.

    Use this when you have K examples of a deterministic system's behavior and
    want to know the closed-form rule it follows — for example, an AI agent's
    routing policy, a scoring formula, a modular-arithmetic decision rule, or
    a PRNG state. K must be at least 4.

    Args:
        observations: List of [input, output] pairs. Input is a scalar integer
            for arity-1 rules (LCG, polynomial, threshold, …) or a nested list
            for multi-input rules (modular addition, boolean truth tables,
            k-bit parity). Output is always an integer.

    Returns:
        A dict with the recovered rule (English string), the family ID
        (e.g., "lcg", "polycoef"), the operator's business name, the recovered
        parameters, a sample-complexity certificate, and `verified: True` if
        the rule reproduces every observation exactly. Returns `family: null`
        if no operator family in the catalog matches the observations.
    """
    pairs = _normalize_observations(observations)
    r = recover_rule(pairs)
    return {
        "rule": r.rule,
        "family": r.family,
        "operator": r.operator,
        "parameters": r.parameters,
        "verified": r.verified,
        "confidence": r.confidence,
        "geometry": r.geometry,
        "k_used": r.k_used,
        "k_lower_bound": r.k_lower_bound,
        "margin": r.margin,
        "certificate": r.certificate,
    }


@mcp.tool()
def predict_under_recovered_rule(
    observations: list[list],
    query_input: Any,
) -> dict[str, Any]:
    """Recover the rule from observations and apply it to predict a held-out input.

    One-shot: this is `recover_rule_from_observations` followed by `.predict(query)`.
    Use this when the agent has K observations and needs the system's output
    for a fresh input it has not seen.

    Args:
        observations: List of [input, output] pairs (same shape as
            `recover_rule_from_observations`).
        query_input: A new input not in the observation set. Scalar int for
            arity-1 rules, a list of ints for multi-input rules.

    Returns:
        A dict with the predicted output, the recovered rule, family, and
        certificate. If no rule was recovered with high confidence, returns
        `prediction: null` and a `reason` field. If the rule was recovered
        but the family does not yet support symbolic prediction (rare —
        mostly stateful PRNGs and recurrences), returns `prediction: null`
        with the reason.
    """
    pairs = _normalize_observations(observations)
    r = recover_rule(pairs)
    base = {
        "rule": r.rule,
        "family": r.family,
        "verified": r.verified,
        "certificate": r.certificate,
    }
    if not r.verified or r.family is None:
        return {**base, "prediction": None, "reason": "no rule recovered with high confidence"}
    try:
        q = tuple(query_input) if isinstance(query_input, list) else query_input
        prediction = r.predict(q)
    except (ValueError, NotImplementedError) as e:
        return {**base, "prediction": None, "reason": str(e)}
    return {**base, "prediction": int(prediction)}


@mcp.tool()
def list_supported_rule_families() -> list[dict[str, Any]]:
    """List the operator families kbound can recover from observations.

    Use this to understand the catalog of rules kbound supports before calling
    `recover_rule_from_observations`. Each family has a `k_lower_bound` (the
    minimum K observations needed for recovery) and a `validation_status`:
    "validated" means tested end-to-end against real-world traces;
    "experimental" means the recovery math works but customer-fit on
    production data has not been measured.

    Returns:
        List of dicts, one per operator family.
    """
    return [
        {
            "family": meta.family_label,
            "name": meta.business_name,
            "description": meta.description,
            "k_lower_bound": meta.typical_k_lower_bound,
            "validation_status": meta.validation_status,
        }
        for meta in OPERATORS.values()
    ]


@mcp.tool()
def verify_compliance_against_claimed_rule(
    observations: list[list],
    claimed_family: str,
    claimed_params: dict[str, Any],
) -> dict[str, Any]:
    """Verify how often observations match a claimed rule.

    Use this when a vendor or system has DECLARED a rule and you want to check
    whether the actual observed behavior matches. Returns the agreement rate
    (0.0-1.0) plus the first ten counterexamples for inspection.

    Common `claimed_family` values:
        "linear_residual" / "linear_residual_policy" / "lcg" — for `(a*x + c) mod m` rules
        "polynomial_threshold" / "polycoef"                  — for polynomial rules
        "scaling_residual" / "modmul"                        — for `(a*x) mod m` rules

    Args:
        observations: List of [input, output] pairs from the agent's actual trace.
        claimed_family: The family ID the vendor declared.
        claimed_params: The parameters the vendor declared (e.g., {"a": 3, "c": 7, "m": 17}).

    Returns:
        A dict with agreement_pct, n_total, n_violations, is_compliant_at_95pct,
        the first 10 counterexamples, agreement bucketed by input range, and
        any diagnostic notes (unknown family, predictor errors, etc.).
    """
    pairs = _normalize_observations(observations)
    spec = ClaimedSpec(family=claimed_family, params=claimed_params)
    report = check_compliance(pairs, spec)
    return {
        "agreement_pct": round(report.agreement_pct, 4),
        "n_total": report.n_total,
        "n_violations": report.n_violations,
        "is_compliant_at_95pct": report.is_compliant(),
        "counterexamples": [
            {"input": ce.x, "observed": ce.y_observed, "predicted_by_claim": ce.y_predicted}
            for ce in report.counterexamples
        ],
        "by_input_bucket": {b: round(p, 4) for b, p in report.by_input_bucket.items()},
        "notes": report.notes,
    }


@mcp.tool()
def classify_observation_geometry(observations: list[list]) -> dict[str, Any]:
    """Classify the geometric structure of a set of observations.

    Returns "spatial" (e.g., axis-aligned thresholds, conjunctive rules —
    LLMs handle these well in-context), "algebraic" (modular arithmetic,
    polynomials, recurrences — LLMs hit chance accuracy in-context, kbound
    recovers them), or "borderline".

    Use this as a CHEAP pre-check before calling `recover_rule_from_observations`
    when you want to know whether kbound is the right tool for these
    observations or whether to just trust the LLM's in-context induction.

    Returns:
        A dict with the geometry verdict, the classifier features (input arity,
        output cardinality, modular wrap detection, recurrence detection,
        spatial separability), the output-cardinality bucket, and a
        recommended LLM model with calibrated accuracy estimate.
    """
    pairs = _normalize_observations(observations)
    g = classify_geometry(pairs)
    fam = None
    if g["geometry"] in ("algebraic", "borderline"):
        fam = identify_family(pairs, g)
    return {
        "geometry": g["geometry"],
        "features": g["features"],
        "output_cardinality_bucket": g["output_cardinality_bucket"],
        "recommended_model": g.get("recommended_model"),
        "recommended_model_accuracy": g.get("recommended_accuracy"),
        "detected_family": fam,
    }


def main() -> None:
    """Console-script entrypoint — runs the MCP server over stdio.

    Invoked by the `kbound-mcp` console script (registered via pyproject's
    [project.scripts]) and by `python -m kbound.mcp`.
    """
    mcp.run()


if __name__ == "__main__":
    main()
