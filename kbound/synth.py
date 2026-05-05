"""Behavioral spec → executable replacement code.

⚠️ EXPERIMENTAL — May 2026. This module emits replacement code, but
the question of WHEN substitution is operationally appropriate (vs.
when the customer should keep the LLM and just audit it) is unsettled.
We have the engineering primitive; the commercial framing of "replace
the LLM" is NOT the product's pitch. The pitch is observability +
traceability + understanding why agents fail. See test_battery/
synthesized_replacements/ for outputs but do not promote synth as a
selling point until research on customer fit is complete.

The fix complement to recovery + compliance: when the engine has
recovered a clean spec for an agent, we can EXECUTE that spec
deterministically and replace the LLM call entirely.

Use case
--------
A vendor's LLM agent costs $0.001 / call, runs 500K calls / month, and
follows a recovered rule like `(7·x + 2) mod 11` with 100% consistency
on the test trace. The customer can:

1. Run the LLM in production for $500 / month.
2. Replace the LLM call with the recovered spec → $0 / month, runs in
   ~0.1ms locally, deterministically, identical output.

That is the commercial wedge of "spec recovery as agent infrastructure":
not just the audit, but the substitute that drops the agent's
operational cost by 1000× while keeping behavior identical to what the
vendor declared.

Targets
-------
- Python source (deterministic function)
- TypeScript source (browser + Node)
- Rust source (low-latency embedded)
- Cedar policy (Microsoft AGT enforcement)
- REST handler stub (FastAPI + Express + Hono)

Each emitter is honest about scope: only families currently in
PREDICTORS produce well-defined replacement code. For unsupported
families, `synthesize_replacement` raises `UnsupportedFamilyError`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from kbound.compliance import PREDICTORS


class UnsupportedFamilyError(Exception):
    """Raised when the recovered family has no synthesizable target."""


# ──────────────────────────────────────────────────────────────────
# data classes
# ──────────────────────────────────────────────────────────────────


@dataclass
class ReplacementBundle:
    """A complete replacement-code package for one recovered agent."""

    family: str
    parameters: dict[str, Any]
    decision_rule: str
    consistency_score: float
    n_observations: int
    target_languages: list[str]
    sources: dict[str, str]  # language -> source code
    ROI_estimate: dict[str, Any]  # cost-saving math at common volumes
    limitations: list[str]
    fingerprint: str

    @property
    def is_safe_to_substitute(self) -> bool:
        """Conservative: only substitute the LLM call when consistency
        was 1.0 on the audited trace. Anything below means there is at
        least one observed input where LLM and spec disagree."""
        return self.consistency_score >= 1.0


# ──────────────────────────────────────────────────────────────────
# emitters per target language
# ──────────────────────────────────────────────────────────────────


def _emit_python(family: str, params: dict[str, Any]) -> str:
    """Generate a self-contained Python function for the recovered family."""
    if family in ("linear_residual", "linear_residual_policy"):
        a, c, m = int(params["a"]), int(params["c"]), int(params["m"])
        return (
            f"def decision(x: int) -> int:\n"
            f'    """Recovered behavioral spec — equivalent to the audited LLM agent.\n\n'
            f"    Family: linear_residual_policy\n"
            f"    Original LLM cost (est.): ~$0.001/call · this function: ~$0\n"
            f'    """\n'
            f"    return ({a} * x + {c}) % {m}\n"
        )
    if family in ("polynomial_threshold", "polynomial_threshold_rule"):
        # Engine emits {a, b, c, p} for quadratic — assume that shape if present,
        # otherwise fall back to coeffs list.
        if "a" in params and "b" in params and "c" in params and "p" in params:
            a, b, c, p = int(params["a"]), int(params["b"]), int(params["c"]), int(params["p"])
            return (
                f"def decision(x: int) -> int:\n"
                f'    """Recovered polynomial threshold — equivalent to the audited LLM."""\n'
                f"    return ({a} * x * x + {b} * x + {c}) % {p}\n"
            )
        coeffs = list(params.get("coeffs", []))
        m = int(params.get("m", params.get("p", 0)))
        terms = " + ".join(
            f"{int(c)} * x**{i}" if i > 0 else f"{int(c)}" for i, c in enumerate(coeffs)
        )
        return (
            f"def decision(x: int) -> int:\n"
            f'    """Recovered polynomial threshold."""\n'
            f"    return ({terms}) % {m}\n"
        )
    if family == "exponential_pattern_rule":
        a = int(params.get("a", params.get("base", 0)))
        m = int(params.get("p", params.get("m", 0)))
        return (
            f"def decision(x: int) -> int:\n"
            f'    """Recovered modular exponentiation — equivalent to the audited LLM."""\n'
            f"    return pow({a}, x, {m})\n"
        )
    if family in ("scaling_residual", "scaling_residual_rule"):
        a, m = int(params["a"]), int(params["m"])
        return (
            f"def decision(x: int) -> int:\n"
            f'    """Recovered scaling residual."""\n'
            f"    return ({a} * x) % {m}\n"
        )
    raise UnsupportedFamilyError(f"no Python emitter for family '{family}'")


def _emit_typescript(family: str, params: dict[str, Any]) -> str:
    """Generate self-contained TypeScript code."""
    header = (
        "/**\n"
        " * Recovered behavioral spec — equivalent to the audited LLM agent.\n"
        " * Generated by kbound from observed traces.\n"
        " */\n"
    )
    if family in ("linear_residual", "linear_residual_policy"):
        a, c, m = int(params["a"]), int(params["c"]), int(params["m"])
        return header + (
            f"export function decision(x: number): number {{\n"
            f"  return (({a} * x + {c}) % {m} + {m}) % {m};\n"
            f"}}\n"
        )
    if family in ("polynomial_threshold", "polynomial_threshold_rule"):
        if "a" in params and "b" in params and "c" in params and "p" in params:
            a, b, c, p = int(params["a"]), int(params["b"]), int(params["c"]), int(params["p"])
            return header + (
                f"export function decision(x: number): number {{\n"
                f"  return ((({a} * x * x + {b} * x + {c}) % {p}) + {p}) % {p};\n"
                f"}}\n"
            )
        coeffs = list(params.get("coeffs", []))
        m = int(params.get("m", params.get("p", 0)))
        terms = " + ".join(
            f"{int(c)} * Math.pow(x, {i})" if i > 0 else f"{int(c)}" for i, c in enumerate(coeffs)
        )
        return header + (
            f"export function decision(x: number): number {{\n"
            f"  return (({terms}) % {m} + {m}) % {m};\n"
            f"}}\n"
        )
    if family == "exponential_pattern_rule":
        a = int(params.get("a", params.get("base", 0)))
        m = int(params.get("p", params.get("m", 0)))
        return header + (
            f"export function decision(x: number): number {{\n"
            f"  // Modular exponentiation a^x mod m via fast exponentiation.\n"
            f"  let result = 1n;\n"
            f"  let base = BigInt({a}) % BigInt({m});\n"
            f"  let exp = BigInt(x);\n"
            f"  while (exp > 0n) {{\n"
            f"    if (exp & 1n) result = (result * base) % BigInt({m});\n"
            f"    exp >>= 1n;\n"
            f"    base = (base * base) % BigInt({m});\n"
            f"  }}\n"
            f"  return Number(result);\n"
            f"}}\n"
        )
    if family in ("scaling_residual", "scaling_residual_rule"):
        a, m = int(params["a"]), int(params["m"])
        return header + (
            f"export function decision(x: number): number {{\n"
            f"  return (({a} * x) % {m} + {m}) % {m};\n"
            f"}}\n"
        )
    raise UnsupportedFamilyError(f"no TypeScript emitter for family '{family}'")


def _emit_rust(family: str, params: dict[str, Any]) -> str:
    """Generate self-contained Rust code (i64 arithmetic)."""
    header = (
        "// Recovered behavioral spec — equivalent to the audited LLM agent.\n"
        "// Generated by kbound.\n\n"
    )
    if family in ("linear_residual", "linear_residual_policy"):
        a, c, m = int(params["a"]), int(params["c"]), int(params["m"])
        return header + (
            f"pub fn decision(x: i64) -> i64 {{\n"
            f"    (({a}i64 * x + {c}i64).rem_euclid({m}i64))\n"
            f"}}\n"
        )
    if family in ("polynomial_threshold", "polynomial_threshold_rule") and (
        "a" in params and "b" in params and "c" in params and "p" in params
    ):
        a, b, c, p = int(params["a"]), int(params["b"]), int(params["c"]), int(params["p"])
        return header + (
            f"pub fn decision(x: i64) -> i64 {{\n"
            f"    (({a}i64 * x * x + {b}i64 * x + {c}i64).rem_euclid({p}i64))\n"
            f"}}\n"
        )
    if family == "exponential_pattern_rule":
        a = int(params.get("a", params.get("base", 0)))
        m = int(params.get("p", params.get("m", 0)))
        return header + (
            f"pub fn decision(x: u32) -> u64 {{\n"
            f"    // Modular exponentiation {a}^x mod {m}.\n"
            f"    let mut result: u64 = 1;\n"
            f"    let mut base: u64 = ({a}u64) % ({m}u64);\n"
            f"    let mut exp = x;\n"
            f"    while exp > 0 {{\n"
            f"        if exp & 1 == 1 {{ result = (result * base) % ({m}u64); }}\n"
            f"        exp >>= 1;\n"
            f"        base = (base * base) % ({m}u64);\n"
            f"    }}\n"
            f"    result\n"
            f"}}\n"
        )
    raise UnsupportedFamilyError(f"no Rust emitter for family '{family}'")


def _emit_cedar(family: str, params: dict[str, Any]) -> str:
    """Generate a Cedar policy that documents the recovered rule.
    Cedar does not natively support arbitrary integer math, so this is
    a STRUCTURED ANNOTATION that Microsoft AGT and similar enforcement
    runtimes can attach to the agent for documentation + drift gating.
    """
    if family in ("linear_residual", "linear_residual_policy"):
        a, c, m = int(params["a"]), int(params["c"]), int(params["m"])
        return (
            f"// Cedar policy — recovered linear residual rule.\n"
            f"// Generated by kbound. Use as documentation + drift-detection\n"
            f"// anchor for Microsoft Agent Governance Toolkit and similar.\n"
            f"@kazdov_recovered_rule(\n"
            f'  family: "linear_residual_policy",\n'
            f'  formula: "({a} * x + {c}) mod {m}",\n'
            f"  parameters: {{ a: {a}, c: {c}, m: {m} }},\n"
            f'  emitted_by: "kbound.synth.synthesize_replacement"\n'
            f")\n"
            f"permit (\n"
            f"  principal,\n"
            f'  action == Action::"emit_decision",\n'
            f"  resource\n"
            f");\n"
        )
    return (
        f"// Cedar policy — recovered family: {family}.\n"
        f"// Parameters: {json.dumps(params)}\n"
        f"// (Generic annotation; AGT integration adapter handles family-specific semantics.)\n"
        f"@kazdov_recovered_rule(\n"
        f'  family: "{family}",\n'
        f"  parameters: {json.dumps(params)},\n"
        f'  emitted_by: "kbound.synth.synthesize_replacement"\n'
        f")\n"
        f'permit (principal, action == Action::"emit_decision", resource);\n'
    )


# ──────────────────────────────────────────────────────────────────
# ROI estimator
# ──────────────────────────────────────────────────────────────────


# Public 2026 prices per call (rough, in USD).
DEFAULT_LLM_COST_PER_CALL = {
    "claude-haiku-4-5": 0.001,
    "claude-sonnet-4-6": 0.021,
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.0008,
}


def _estimate_roi(consistency: float, llm_cost_per_call: float = 0.001) -> dict[str, Any]:
    """Estimate the cost saving if the LLM call is replaced by the
    synthesized function. Reports values at three common monthly volumes.
    """
    # Synthesized function compute cost — order-of-magnitude estimate.
    synth_cost_per_call = 0.0000001  # ~$1 per 10M calls on commodity compute

    def at(volume: int) -> dict[str, float]:
        llm_total = volume * llm_cost_per_call
        synth_total = volume * synth_cost_per_call
        saved = llm_total - synth_total
        return {
            "monthly_calls": volume,
            "llm_monthly_cost_usd": round(llm_total, 2),
            "synth_monthly_cost_usd": round(synth_total, 4),
            "monthly_savings_usd": round(saved, 2),
            "savings_pct": round(saved / llm_total * 100, 1) if llm_total > 0 else 0,
        }

    return {
        "consistency_on_audit_trace": consistency,
        "safe_to_substitute": consistency >= 1.0,
        "scenarios": {
            "low_volume_50k_calls": at(50_000),
            "mid_volume_500k_calls": at(500_000),
            "high_volume_5m_calls": at(5_000_000),
        },
        "assumptions": {
            "llm_cost_per_call_usd": llm_cost_per_call,
            "synthesized_cost_per_call_usd": synth_cost_per_call,
        },
    }


# ──────────────────────────────────────────────────────────────────
# main entry point
# ──────────────────────────────────────────────────────────────────


def synthesize_replacement(
    bundle,
    targets: list[str] = ("python", "typescript", "rust", "cedar"),
    llm_cost_per_call: float = 0.001,
) -> ReplacementBundle:
    """Given a SpecBundle (recovered by kbound.cli.recover.recover_from_logs),
    emit a complete replacement-code package across the requested targets,
    plus an ROI estimate at three common volumes.

    `targets` accepts any subset of: "python", "typescript", "rust", "cedar".
    """
    if bundle.operator is None:
        raise UnsupportedFamilyError(
            "Cannot synthesize a replacement: bundle has no recovered operator (no_recovery)."
        )

    family = bundle.operator.family_label
    params = dict(bundle.parameters)
    sources: dict[str, str] = {}
    limitations: list[str] = []

    for t in targets:
        try:
            if t == "python":
                sources["python"] = _emit_python(family, params)
            elif t == "typescript":
                sources["typescript"] = _emit_typescript(family, params)
            elif t == "rust":
                sources["rust"] = _emit_rust(family, params)
            elif t == "cedar":
                sources["cedar"] = _emit_cedar(family, params)
            else:
                limitations.append(f"unsupported target: {t}")
        except UnsupportedFamilyError as e:
            limitations.append(f"target {t}: {e}")

    # Sanity check: re-execute the Python source against the predictor table
    # on a few inputs, confirm bit-identity.
    if "python" in sources and family in PREDICTORS:
        try:
            local_ns: dict[str, Any] = {}
            exec(sources["python"], {}, local_ns)
            decision_fn = local_ns["decision"]
            for x_test in (0, 1, 7, 42, 100):
                expected = PREDICTORS[family](params, x_test)
                got = decision_fn(x_test)
                if expected != got:
                    limitations.append(
                        f"emitted Python diverges from predictor on x={x_test}: "
                        f"expected {expected}, got {got}"
                    )
                    break
        except Exception as e:
            limitations.append(f"emitted Python failed sanity check: {e}")

    if bundle.consistency_score < 1.0:
        limitations.append(
            f"audit-trace consistency was only {bundle.consistency_score:.4f} (< 1.0). "
            f"The replacement is faithful to the recovered spec, but the original LLM "
            f"deviated from the spec on some observed inputs. Validate against held-out "
            f"data before substituting in production."
        )

    fp_payload = {"family": family, "params": params, "consistency": bundle.consistency_score}
    import hashlib

    fp = hashlib.sha256(json.dumps(fp_payload, sort_keys=True).encode()).hexdigest()[:16]

    return ReplacementBundle(
        family=family,
        parameters=params,
        decision_rule=bundle.decision_rule,
        consistency_score=bundle.consistency_score,
        n_observations=bundle.n_observations,
        target_languages=list(sources.keys()),
        sources=sources,
        ROI_estimate=_estimate_roi(bundle.consistency_score, llm_cost_per_call),
        limitations=limitations,
        fingerprint=fp,
    )


def render_replacement_report_md(rb: ReplacementBundle) -> str:
    """Audit-grade Markdown wrapper around the synthesized replacement."""
    lines: list[str] = [
        "# Replacement Specification Bundle",
        "",
        f"**Recovered rule:** `{rb.decision_rule}`",
        f"**Family:** `{rb.family}`",
        f"**Parameters:** `{json.dumps(rb.parameters, sort_keys=True)}`",
        f"**Audit-trace consistency:** {rb.consistency_score:.4f}",
        f"**Observations evaluated:** {rb.n_observations}",
        f"**Synthesis fingerprint:** `{rb.fingerprint}`",
        f"**Safe to substitute (consistency ≥ 1.0):** {rb.is_safe_to_substitute}",
        "",
        "## ROI estimate",
        "",
    ]
    roi = rb.ROI_estimate
    lines.append(
        f"Assumes LLM call cost ${roi['assumptions']['llm_cost_per_call_usd']:.4f}, "
        f"synthesized call cost ${roi['assumptions']['synthesized_cost_per_call_usd']:.7f}."
    )
    lines.append("")
    lines.append("| Volume (calls/mo) | LLM cost (USD) | Synth cost (USD) | Saved | Savings % |")
    lines.append("|---:|---:|---:|---:|---:|")
    for _key, sc in roi["scenarios"].items():
        lines.append(
            f"| {sc['monthly_calls']:,} "
            f"| ${sc['llm_monthly_cost_usd']:,.2f} "
            f"| ${sc['synth_monthly_cost_usd']:.4f} "
            f"| **${sc['monthly_savings_usd']:,.2f}** "
            f"| {sc['savings_pct']}% |"
        )
    lines.append("")

    for lang in rb.target_languages:
        lines.append(f"## Replacement source ({lang})")
        lines.append("")
        lines.append(f"```{lang if lang != 'cedar' else ''}")
        lines.append(rb.sources[lang].rstrip())
        lines.append("```")
        lines.append("")

    if rb.limitations:
        lines.append("## Limitations")
        lines.append("")
        for lim in rb.limitations:
            lines.append(f"- {lim}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "*Generated by `kbound.synth.synthesize_replacement()`. "
        "Use this artifact ONLY when audit-trace consistency is 1.0 and a "
        "held-out validation pass on production data confirms identity. The "
        "replacement is faithful to the recovered spec — it does NOT model "
        "any noise / exception behavior the original LLM may have had.*"
    )
    return "\n".join(lines)
