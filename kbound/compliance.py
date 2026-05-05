"""Spec compliance verification.

Given a trace + a CLAIMED behavioral specification (the rule the vendor
declared), compute the agreement rate and surface counterexamples.

This is the primitive that converts the "no_recovery" failure of the
recovery engine into a positive audit finding: the vendor said the agent
follows rule X; we measure how often it actually does.

Usage:
    from kbound.compliance import check_compliance, ClaimedSpec

    spec = ClaimedSpec(family="linear_residual", params={"a": 7, "c": 13, "m": 11})
    report = check_compliance(observations, spec)
    print(f"{report.agreement_pct:.0%} compliance")

Render outputs:
    render_compliance_report_md(report)        — Markdown for embedding in spec.md
    render_legal_counterexample_csv(report)    — CSV procurement / legal can paste
                                                  into a vendor breach notice
    render_remediation_sla(report, vendor)     — SLA template that closes the
                                                  EU AI Act "willful violation"
                                                  liability gap (per Sophie /
                                                  EU compliance officer council)
    render_ai_bom_section(report, vendor, sys) — AI Bill of Materials section
                                                  per Cisco AI Defense convention
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Rule predictors keyed by family name. Each predictor takes the spec
# parameters dict + an input value, returns the predicted output.
RulePredictor = Callable[[dict[str, Any], int], int]


def _linear_residual(params: dict[str, Any], x: int) -> int:
    return (int(params["a"]) * int(x) + int(params["c"])) % int(params["m"])


def _polynomial_threshold(params: dict[str, Any], x: int) -> int:
    """Polynomial mod m. Accepts two parameter shapes:

    1. {coeffs: [c0, c1, c2, ...], m: M}  — coeffs in ascending power order
    2. {a, b, c, p}                       — engine convention for quadratics:
                                            a = leading (x²), b = linear, c = constant, p = modulus
    """
    if "coeffs" in params:
        coeffs = params["coeffs"]
        m = int(params["m"])
        return sum(int(coef) * (int(x) ** i) for i, coef in enumerate(coeffs)) % m
    # Engine quadratic convention: a*x² + b*x + c, modulus p
    if "a" in params and "b" in params and "c" in params and "p" in params:
        a, b, c, p = int(params["a"]), int(params["b"]), int(params["c"]), int(params["p"])
        xi = int(x)
        return (a * xi * xi + b * xi + c) % p
    raise KeyError(
        f"polynomial predictor: expected either {{coeffs, m}} or {{a, b, c, p}}, "
        f"got keys {sorted(params.keys())}"
    )


def _scaling_residual(params: dict[str, Any], x: int) -> int:
    # Accept both "m" (compliance convention) and "p" (recovery engine convention).
    modulus = params.get("m", params.get("p"))
    if modulus is None:
        raise KeyError("scaling_residual predictor: expected modulus key 'm' or 'p'")
    return (int(params["a"]) * int(x)) % int(modulus)


PREDICTORS: dict[str, RulePredictor] = {
    # Compliance-vocab keys (declared by humans/vendors)
    "linear_residual": _linear_residual,
    "linear_residual_policy": _linear_residual,
    "polynomial_threshold": _polynomial_threshold,
    "polynomial_threshold_rule": _polynomial_threshold,
    "scaling_residual": _scaling_residual,
    "scaling_residual_rule": _scaling_residual,
    # Engine-vocab aliases (so `result.family` from recover_rule plugs in directly).
    # Without these, `ClaimedSpec(family=result.family, params=result.parameters)`
    # would silently return 0% agreement with an "unknown family" note.
    "lcg": _linear_residual,
    "lcg_generic": _linear_residual,
    "linear_residual_large_modulus": _linear_residual,
    "glibc": _linear_residual,
    "glibc_windowed": _linear_residual,
    "java_random": _linear_residual,
    "polycoef": _polynomial_threshold,
    "polycoef_generic": _polynomial_threshold,
    "polynomial_threshold_large_modulus": _polynomial_threshold,
    "modmul": _scaling_residual,
}


@dataclass(frozen=True)
class ClaimedSpec:
    """A behavioral spec the vendor claims the agent follows.

    `family` matches one of the registered predictors. `params` are the
    family-specific parameters (e.g. {"a": 7, "c": 13, "m": 11}).
    `source` records who/what attested the claim (vendor, system prompt,
    contract clause). `source` flows through into the audit report.
    """

    family: str
    params: dict[str, Any]
    source: str = "vendor-declared"


@dataclass
class Counterexample:
    x: int
    y_observed: int
    y_predicted: int


@dataclass
class ComplianceReport:
    """Output of check_compliance.

    `agreement_pct` is the fraction of trace observations where the
    agent's output matched the predicted output. `n_total` is the count
    used. `counterexamples` are the first ~10 mismatches, included for
    auditor inspection. `by_input_bucket` groups agreement by ranges of
    input (helps spot e.g. "agent complies on small inputs but not large").
    """

    spec: ClaimedSpec
    n_total: int
    n_agree: int
    agreement_pct: float
    counterexamples: list[Counterexample]
    by_input_bucket: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def n_violations(self) -> int:
        return self.n_total - self.n_agree

    def is_compliant(self, threshold: float = 0.95) -> bool:
        """True iff the agent meets the agreement threshold (default 95%)."""
        return self.agreement_pct >= threshold


def check_compliance(
    observations: list[tuple[int, int]],
    claimed: ClaimedSpec,
    *,
    max_counterexamples: int = 10,
) -> ComplianceReport:
    """Measure how often `observations` match the rule predicted by `claimed`.

    Parameters
    ----------
    observations : list[(int, int)]
        Pairs of (input, observed_output) drawn from the agent's trace.
    claimed : ClaimedSpec
        The behavioral specification the vendor (or operator) declared.
    max_counterexamples : int
        Cap on the number of mismatches to record; the report's
        `n_violations` is the true total regardless.

    Returns
    -------
    ComplianceReport with agreement_pct, counterexamples, and bucket
    breakdown. Honest output: if the family is unknown, the report
    surfaces that as a note and returns 0% agreement (no false claim).
    """
    notes: list[str] = []
    if claimed.family not in PREDICTORS:
        notes.append(f"unknown family '{claimed.family}'; cannot evaluate compliance")
        return ComplianceReport(
            spec=claimed,
            n_total=len(observations),
            n_agree=0,
            agreement_pct=0.0,
            counterexamples=[],
            notes=notes,
        )

    predictor = PREDICTORS[claimed.family]
    n_agree = 0
    counterexamples: list[Counterexample] = []
    bucket_agree: dict[str, list[int]] = {"low": [], "mid": [], "high": []}
    if observations:
        xs = [x for x, _ in observations]
        x_min, x_max = min(xs), max(xs)
        span = max(x_max - x_min, 1)

    for x, y in observations:
        try:
            y_pred = predictor(claimed.params, x)
        except (KeyError, TypeError, ValueError) as e:
            notes.append(f"predictor error on x={x}: {e}; counted as violation")
            if len(counterexamples) < max_counterexamples:
                counterexamples.append(Counterexample(x, y, -1))
            continue
        agree = y_pred == y
        if agree:
            n_agree += 1
        elif len(counterexamples) < max_counterexamples:
            counterexamples.append(Counterexample(x, y, y_pred))
        # bucket assignment
        rel = (x - x_min) / span
        bucket = "low" if rel < 0.33 else ("mid" if rel < 0.66 else "high")
        bucket_agree[bucket].append(int(agree))

    agreement_pct = n_agree / len(observations) if observations else 0.0
    by_input_bucket = {b: (sum(v) / len(v) if v else 0.0) for b, v in bucket_agree.items()}
    return ComplianceReport(
        spec=claimed,
        n_total=len(observations),
        n_agree=n_agree,
        agreement_pct=agreement_pct,
        counterexamples=counterexamples,
        by_input_bucket=by_input_bucket,
        notes=notes,
    )


def render_compliance_report_md(report: ComplianceReport) -> str:
    """Render a ComplianceReport as audit-grade Markdown."""
    spec = report.spec
    lines = [
        "# Spec Compliance Report",
        "",
        f"**Claimed specification** ({spec.source}): "
        f"`family={spec.family}`, `params={spec.params}`",
        "",
        "## Agreement",
        "",
        f"- Observations evaluated: **{report.n_total}**",
        f"- Matched the claimed rule: **{report.n_agree}**",
        f"- Violations: **{report.n_violations}**",
        f"- Agreement rate: **{report.agreement_pct:.1%}**",
        f"- Compliant at 95% threshold: **{report.is_compliant()}**",
        "",
    ]
    if report.by_input_bucket:
        lines.append("## Agreement by input range")
        lines.append("")
        for bucket, pct in report.by_input_bucket.items():
            lines.append(f"- {bucket}: {pct:.1%}")
        lines.append("")
    if report.counterexamples:
        lines.append(f"## Counterexamples (first {len(report.counterexamples)})")
        lines.append("")
        lines.append("| input | observed | predicted by claim |")
        lines.append("|---:|---:|---:|")
        for ce in report.counterexamples:
            lines.append(f"| {ce.x} | {ce.y_observed} | {ce.y_predicted} |")
        lines.append("")
    if report.notes:
        lines.append("## Notes")
        lines.append("")
        for n in report.notes:
            lines.append(f"- {n}")
        lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────
# Legal-ready counterexample export (Markdown table + CSV)
#
# Procurement & vendor risk teams asked for an artifact they can paste
# directly into a vendor breach notice or contract renewal renegotiation.
# Format includes timestamp + reproducibility hash so the artifact is
# self-evidencing under discovery.
# ──────────────────────────────────────────────────────────────────


def _trace_fingerprint(report: ComplianceReport) -> str:
    """SHA-256 over the spec + counterexamples — short prefix for citing."""
    payload = {
        "spec": {
            "family": report.spec.family,
            "params": report.spec.params,
            "source": report.spec.source,
        },
        "n_total": report.n_total,
        "n_agree": report.n_agree,
        "counterexamples": [
            {"x": ce.x, "y_observed": ce.y_observed, "y_predicted": ce.y_predicted}
            for ce in report.counterexamples
        ],
    }
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return h[:16]


def render_legal_counterexample_csv(report: ComplianceReport) -> str:
    """CSV of counterexamples, suitable for direct paste into a vendor
    breach notice or contract-renewal renegotiation document.

    Columns: row, input, observed_output, vendor_predicted_output,
    delta, fingerprint. Header is RFC-4180-quoted.
    """
    fp = _trace_fingerprint(report)
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [
        "# kbound — vendor compliance counterexamples",
        f"# generated_utc: {iso}",
        f"# fingerprint: {fp}",
        f"# spec_source: {report.spec.source}",
        f"# claimed_family: {report.spec.family}",
        f"# claimed_params: {json.dumps(report.spec.params, sort_keys=True)}",
        f"# total_observations: {report.n_total}",
        f"# total_violations: {report.n_violations}",
        f"# agreement_pct: {report.agreement_pct:.4f}",
        '"row","input","observed_output","vendor_predicted_output","delta","fingerprint"',
    ]
    for i, ce in enumerate(report.counterexamples, start=1):
        try:
            delta = int(ce.y_observed) - int(ce.y_predicted)
            delta_s = str(delta)
        except (TypeError, ValueError):
            delta_s = ""
        lines.append(f'"{i}","{ce.x}","{ce.y_observed}","{ce.y_predicted}","{delta_s}","{fp}"')
    return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────────────────────────
# Remediation SLA template
#
# Per the EU AI Act compliance officer council lens: a customer that
# holds Kazdov evidence of vendor non-compliance and continues
# deployment escalates from negligence to willful violation (4% → 7%
# global turnover fines under Art. 99). Shipping a remediation SLA
# template alongside the audit closes that liability gap.
# ──────────────────────────────────────────────────────────────────


def render_remediation_sla(
    report: ComplianceReport,
    vendor_name: str,
    customer_name: str = "[Customer]",
    threshold_pct: float = 0.95,
) -> str:
    """Markdown SLA template the customer can attach to the vendor's MSA
    or breach notice. Threshold defaults to 95% agreement, in line with
    typical SR 11-7 effective-challenge tolerances.
    """
    fp = _trace_fingerprint(report)
    iso = time.strftime("%Y-%m-%d", time.gmtime())
    short_id = f"KZD-{iso.replace('-', '')}-{fp[:6].upper()}"
    return f"""# Remediation SLA — Vendor Compliance Finding

**Reference ID:** `{short_id}`
**Date issued:** {iso}
**Customer:** {customer_name}
**Vendor:** {vendor_name}
**Trace fingerprint:** `{fp}`

## Finding

The behavioral-specification compliance audit performed on the trace
sample referenced above measured a **{report.agreement_pct:.1%}**
agreement rate between the vendor's stated specification (
`family={report.spec.family}`, source: *{report.spec.source}*) and the
agent's observed behavior over **{report.n_total} observations**.

This falls **{(threshold_pct - report.agreement_pct) * 100:.1f}
percentage points below** the {threshold_pct:.0%} compliance threshold
typically required for production AI under SR 11-7 ongoing-monitoring,
NIST AI RMF Govern-1.2, and EU AI Act Article 13.

## Remediation obligations

1. **Acknowledge** receipt within 5 business days, citing this Reference
   ID and confirming the trace fingerprint.
2. **Root cause analysis** delivered in writing within 21 business days,
   identifying whether the divergence is (a) a system-prompt
   misconfiguration, (b) a model-version drift, (c) a documented but
   undeclared exception, or (d) other.
3. **Remediation plan** with milestones and target compliance ≥
   {threshold_pct:.0%}, delivered within 30 business days.
4. **Re-audit** at vendor expense within 60 business days of remediation
   plan acceptance, run on a fresh sample by the same audit framework
   (kbound or equivalent third-party).
5. **Continuation conditions:** this customer reserves the right to
   suspend production traffic, withhold renewal payments, or invoke
   contractual termination if (i) acknowledgement is not delivered
   within 5 days, (ii) the re-audit fails to reach the threshold, or
   (iii) the vendor disputes the methodology without proposing an
   independent audit framework.

## Customer obligations

By documenting this finding and proceeding with the remediation
process above, the customer demonstrates good-faith compliance with
ongoing-monitoring obligations under their applicable regime and
preserves all defenses against allegations of willful continuation.

## Provenance & reproducibility

This SLA is bound to the trace fingerprint `{fp}` and the agreement
metrics computed above. The same fingerprint can be regenerated from
the original JSONL trace by re-running kbound on the same input
and the same claimed specification. Any divergence in the regenerated
fingerprint invalidates the basis of this SLA.

---

*Generated by kbound — `kbound.compliance.render_remediation_sla()`.
This is a template, not legal advice. Final wording subject to customer
counsel review.*
"""


# ──────────────────────────────────────────────────────────────────
# AI Bill of Materials (AI BOM) section
#
# Cisco AI Defense introduced the term in early 2026; procurement teams
# at banks and enterprise are now starting to treat AI BOM as a required
# artifact (analogous to SBOM for software supply chain). The compliance
# report can render a short AI-BOM section that lists the audited agent
# + the audit framework + the spec (when recovered) + provenance.
# ──────────────────────────────────────────────────────────────────


def render_ai_bom_section(
    report: ComplianceReport,
    vendor_name: str,
    system_name: str,
    model_name: str = "(undisclosed by vendor)",
) -> str:
    """AI Bill of Materials section — minimal but fileable. Output is
    Markdown for inclusion in spec.md.
    """
    fp = _trace_fingerprint(report)
    iso = time.strftime("%Y-%m-%d", time.gmtime())
    return f"""## AI Bill of Materials (AI BOM)

| Field | Value |
|---|---|
| System name              | {system_name} |
| Vendor                   | {vendor_name} |
| Underlying model         | {model_name} |
| Audited spec source      | {report.spec.source} |
| Spec family (claimed)    | `{report.spec.family}` |
| Spec parameters (claimed)| `{json.dumps(report.spec.params, sort_keys=True)}` |
| Observations evaluated   | {report.n_total} |
| Agreement rate           | {report.agreement_pct:.1%} |
| Compliant @ 95% threshold| {report.is_compliant()} |
| Trace fingerprint        | `{fp}` |
| Audit date (UTC)         | {iso} |
| Audit framework          | kbound — behavioral spec recovery + compliance verification |
| Methodology reference    | github.com/OriginalKazdov/kbound |

This AI Bill of Materials follows the convention introduced in early
2026 by Cisco AI Defense for AI-system supply-chain documentation. It
is intended as a minimal procurement-grade artifact: the vendor identity,
the system name, the model substrate (when disclosed), the audited
spec, the agreement metric, and a fingerprint for reproducibility.
"""
