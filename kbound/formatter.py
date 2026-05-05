"""Composition → spec.md (English) + spec.yaml (machine-checkable).

The recovered policy is rendered in two forms:
  - spec.md: auditor reads in <60 seconds, English IF/THEN
  - spec.yaml: deterministic, re-runnable against the same traces (round-trip)

The K-bound block is included in both. Margin is reported as multiplier
(K_used / K_lower_bound). Proof status is "empirical" or "proven" depending
on whether paper #3's theorem covers this operator family.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from kbound.operators import OperatorMeta, operator_for


@dataclass
class SpecBundle:
    """Renderable bundle of a recovered spec.

    When `operator is None` (no deterministic rule recovered), `k_lower_bound`
    and `margin` are None. Emitting an audit-grade margin claim on an
    unrecovered run would be dishonest.
    """

    operator: OperatorMeta | None
    parameters: dict[str, Any]
    decision_rule: str
    k_used: int
    k_lower_bound: int | None
    margin: float | None
    proof_status: str  # "empirical" | "proven" | "no_recovery"
    answer_for_query: Any | None
    query_input: Any | None
    n_observations: int
    consistency_score: float


def build_bundle(
    backend_response: dict,
    n_observations: int,
    query_input: Any | None = None,
) -> SpecBundle:
    """Build a SpecBundle from a backend /induce-style response."""
    family_id = backend_response.get("final", {}).get("family") or backend_response.get("family")
    operator = operator_for(family_id) if family_id else None

    # Extract parameters from the backend trace
    params: dict[str, Any] = {}
    trace = backend_response.get("trace") or {}
    solver_block = (trace.get("solver") or {}).get("params") or {}
    if isinstance(solver_block, dict):
        params = {k: v for k, v in solver_block.items() if v is not None}

    # If trace not present, look in stages (explain endpoint format)
    if not params:
        for stage in backend_response.get("stages", []):
            if stage.get("step") == 3:  # solver invocation
                d = stage.get("details") or {}
                pr = d.get("params_recovered") or {}
                if isinstance(pr, dict):
                    params = {k: v for k, v in pr.items() if v is not None}
                break

    decision_rule = _render_decision_rule(operator, params)
    k_used = n_observations
    if operator is not None:
        k_lower: int | None = operator.typical_k_lower_bound
        margin: float | None = round(k_used / max(k_lower, 1), 2) if k_lower > 0 else None
        proof_status = "empirical"  # upgraded to "proven" once paper #3 lands per-operator
    else:
        # No rule recovered — do not emit audit claims about a non-existent fit.
        k_lower = None
        margin = None
        proof_status = "no_recovery"

    confidence = backend_response.get("confidence")
    if confidence is None:
        confidence = (trace.get("verification") or {}).get("consistency_score") or 0.0

    return SpecBundle(
        operator=operator,
        parameters=params,
        decision_rule=decision_rule,
        k_used=k_used,
        k_lower_bound=k_lower,
        margin=margin,
        proof_status=proof_status,
        answer_for_query=backend_response.get("answer"),
        query_input=query_input,
        n_observations=n_observations,
        consistency_score=float(confidence) if confidence is not None else 0.0,
    )


def _render_decision_rule(operator: OperatorMeta | None, params: dict[str, Any]) -> str:
    """Produce a one-line English/math description of the recovered rule."""
    if operator is None:
        return "No deterministic rule recovered (insufficient signal or family outside library)."
    fam = operator.internal_id

    a = params.get("a")
    b = params.get("b")
    c = params.get("c")
    d = params.get("d")
    m = params.get("m")
    p = params.get("p")
    params.get("n")
    params.get("k")
    op = params.get("operator")

    if fam == "lcg" and a is not None and c is not None and m is not None:
        return f"decision(x) = ({a}·x + {c}) mod {m}"
    if fam == "polycoef" and all(v is not None for v in (a, b, c, p)):
        return f"decision(x) = ({a}·x² + {b}·x + {c}) mod {p}"
    if fam == "cubic" and all(v is not None for v in (a, b, c, d, p)):
        return f"decision(x) = ({a}·x³ + {b}·x² + {c}·x + {d}) mod {p}"
    if fam == "modmul" and a is not None and p is not None:
        return f"decision(x) = ({a}·x) mod {p}"
    if fam == "modinv" and p is not None:
        return f"decision(x) = x⁻¹ mod {p}"
    if fam == "modexp" and a is not None and p is not None:
        return f"decision(x) = {a}^x mod {p}"
    if fam == "mod_p_add" and p is not None:
        return f"decision(x₁, x₂) = (x₁ + x₂) mod {p}"
    if fam == "recurrence_fib" and a is not None and b is not None and m is not None:
        return f"decision(n) = ({a}·decision(n−1) + {b}·decision(n−2)) mod {m}"
    if fam == "boolean_2input":
        return (
            f"decision(x₁, x₂) = boolean operator '{op}'"
            if op
            else "decision = boolean truth-table"
        )
    if fam == "parity_kbit":
        return "decision = XOR over k binary inputs (parity)"
    if fam == "glibc":
        return "decision_n = (1103515245·decision_{n-1} + 12345) mod 2³¹"
    if fam == "java_random":
        return "decision_n = top 32 bits of (5DEECE66D·s_{n-1} + B) mod 2⁴⁸"
    if fam == "mt19937":
        return (
            "decision = MT19937 stateful pattern (state recovered from K consecutive observations)"
        )
    return f"{operator.business_name} (params: {json.dumps(params, default=str)})"


def to_markdown(bundle: SpecBundle) -> str:
    """Render the bundle as auditor-readable Markdown."""
    op_name = bundle.operator.business_name if bundle.operator else "Unrecovered"
    op_desc = bundle.operator.description if bundle.operator else ""

    lines = [
        "# Recovered Policy Specification",
        "",
        f"**Operator family**: {op_name}",
    ]
    if op_desc:
        lines.append(f"_{op_desc}_")
    lines += [
        "",
        "## Decision rule",
        "",
        f"> `{bundle.decision_rule}`",
        "",
    ]
    if bundle.parameters:
        lines += ["## Parameters recovered", ""]
        for k, v in bundle.parameters.items():
            lines.append(f"- `{k}` = `{v}`")
        lines.append("")

    if bundle.operator is not None:
        lines += [
            "## Audit certificate",
            "",
            f"- **K used**: {bundle.k_used} observations",
            f"- **K theoretical lower bound**: {bundle.k_lower_bound} (operator-specific)",
            f"- **Margin**: {bundle.margin}× over lower bound",
            f"- **Proof status**: `{bundle.proof_status}`",
            f"- **Support set consistency**: {bundle.consistency_score:.0%}",
            "",
        ]
    else:
        lines += [
            "## Audit status",
            "",
            f"- **K observed**: {bundle.k_used}",
            "- **Outcome**: no deterministic rule from the operator library matched these observations.",
            "- No certificate emitted. Possible causes: insufficient sample, non-algebraic decision policy, or noisy traces.",
            "",
        ]

    if bundle.query_input is not None:
        lines += [
            "## Query result",
            "",
            f"- Input: `{bundle.query_input}`",
            f"- Predicted output: `{bundle.answer_for_query}`",
            "",
        ]

    lines += [
        "---",
        "",
        "_Generated by kbound — Behavioral Specification Recovery for AI Agents._",
    ]
    return "\n".join(lines)


def to_yaml(bundle: SpecBundle) -> str:
    """Render the bundle as deterministic YAML for machine re-checking."""
    op_label = bundle.operator.family_label if bundle.operator else "unrecovered"
    op_name = bundle.operator.business_name if bundle.operator else "Unrecovered"

    # Custom YAML emission to keep deterministic key order without taking PyYAML dep
    out: list[str] = []
    out.append("recovered_spec:")
    out.append(f'  operator: "{op_name}"')
    out.append(f'  family_label: "{op_label}"')
    out.append("  parameters:")
    if bundle.parameters:
        for k, v in bundle.parameters.items():
            out.append(f"    {k}: {_yaml_value(v)}")
    else:
        out.append("    {}")
    out.append(f'  decision_rule: "{bundle.decision_rule}"')
    out.append("certificate:")
    out.append(f"  k_used: {bundle.k_used}")
    if bundle.operator is not None:
        out.append(f"  k_lower_bound: {bundle.k_lower_bound}")
        out.append(f"  margin: {bundle.margin}")
    else:
        out.append("  k_lower_bound: null")
        out.append("  margin: null")
    out.append(f'  proof_status: "{bundle.proof_status}"')
    out.append(f"  consistency_score: {bundle.consistency_score:.4f}")
    out.append(f"  n_observations: {bundle.n_observations}")
    if bundle.query_input is not None:
        out.append("query:")
        out.append(f"  input: {_yaml_value(bundle.query_input)}")
        out.append(f"  predicted_output: {_yaml_value(bundle.answer_for_query)}")
    return "\n".join(out) + "\n"


def _yaml_value(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_yaml_value(x) for x in v) + "]"
    return f'"{v}"'
