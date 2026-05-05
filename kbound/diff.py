"""Behavioral spec diff between two traces.

Given two JSONL trace files captured at different times (or against different
agent versions), recover the behavioral specification of each, then report:

1. Structural diff between the two recovered specs (which parameters
   changed, family changed, recoverability changed).
2. Behavioral divergence — over the union of inputs from both traces, how
   often does spec_v1 predict a different output than spec_v2.
3. K-bound certificates from each side, side-by-side.

The CLI surface is:
    kbound diff --v1 trace_v1.jsonl --v2 trace_v2.jsonl

The Python surface is:
    from kbound.diff import diff_traces, render_diff_report_md
    diff = diff_traces("trace_v1.jsonl", "trace_v2.jsonl")
    print(render_diff_report_md(diff))

This is the "git-blame for agent behavior" primitive: tell me WHAT RULE
changed between two trace captures, not just whether the score moved.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from kbound.cli import recover_from_logs
from kbound.compliance import PREDICTORS

# ──────────────────────────────────────────────────────────────────
# data classes
# ──────────────────────────────────────────────────────────────────


@dataclass
class SideRecovery:
    """One side of a diff: the recovery output for a single trace."""

    label: str  # "v1" or "v2"
    trace_path: str
    n_observations: int
    operator_family: str | None  # None if no_recovery
    parameters: dict[str, Any]  # {} if no_recovery
    decision_rule: str  # human-readable form
    k_used: int
    k_lower_bound: int | None
    margin: float | None
    consistency_score: float
    proof_status: str  # "empirical" | "no_recovery"

    @property
    def recovered(self) -> bool:
        return self.operator_family is not None and bool(self.parameters)


@dataclass
class ParamDelta:
    name: str
    v1_value: Any
    v2_value: Any
    changed: bool


@dataclass
class BehavioralDivergence:
    """How many predictions disagree between the two specs over the union
    of trace inputs. Only computed when both sides recovered a spec.
    """

    inputs_compared: int
    predictions_matching: int
    predictions_diverging: int

    @property
    def divergence_rate(self) -> float:
        if self.inputs_compared == 0:
            return 0.0
        return self.predictions_diverging / self.inputs_compared


@dataclass
class SpecDiff:
    """The full drift report bundle."""

    v1: SideRecovery
    v2: SideRecovery
    family_changed: bool
    family_v1: str | None
    family_v2: str | None
    parameter_deltas: list[ParamDelta]
    behavioral_divergence: BehavioralDivergence | None  # None if either side did not recover
    fingerprint: str
    notes: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────


def _bundle_to_side(label: str, path: str, raw: dict) -> SideRecovery:
    """Lift a recover_from_logs() result into a SideRecovery row."""
    bundle = raw["bundle"]
    return SideRecovery(
        label=label,
        trace_path=path,
        n_observations=bundle.n_observations,
        operator_family=bundle.operator.family_label if bundle.operator else None,
        parameters=dict(bundle.parameters) if bundle.parameters else {},
        decision_rule=bundle.decision_rule,
        k_used=bundle.k_used,
        k_lower_bound=bundle.k_lower_bound,
        margin=bundle.margin,
        consistency_score=bundle.consistency_score,
        proof_status=bundle.proof_status,
    )


def _trace_inputs(path: str) -> list[int]:
    """Pull the observed input values out of a JSONL trace file."""
    inputs: list[int] = []
    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            rec = json.loads(line)
            meta = rec.get("_meta") or {}
            if "x" in meta:
                try:
                    inputs.append(int(meta["x"]))
                except (TypeError, ValueError):
                    continue
    return inputs


def _predict(side: SideRecovery, x: int) -> int | None:
    """Apply the recovered spec from `side` to predict an output for `x`.
    Returns None if the side did not recover a spec or the family is
    unsupported by the compliance predictor table."""
    if not side.recovered:
        return None
    fam = side.operator_family
    if fam is None or fam not in PREDICTORS:
        return None
    try:
        return PREDICTORS[fam](side.parameters, x)
    except (KeyError, TypeError, ValueError):
        return None


def _diff_fingerprint(v1: SideRecovery, v2: SideRecovery) -> str:
    payload = {
        "v1": {"family": v1.operator_family, "params": v1.parameters},
        "v2": {"family": v2.operator_family, "params": v2.parameters},
    }
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return h[:16]


# ──────────────────────────────────────────────────────────────────
# public API
# ──────────────────────────────────────────────────────────────────


def diff_traces(trace_v1: str, trace_v2: str) -> SpecDiff:
    """Recover specs from two trace files and emit a structured diff."""
    raw1 = recover_from_logs(trace_v1)
    raw2 = recover_from_logs(trace_v2)
    v1 = _bundle_to_side("v1", trace_v1, raw1)
    v2 = _bundle_to_side("v2", trace_v2, raw2)

    notes: list[str] = []

    # Parameter-level diff.
    param_keys = sorted(set(v1.parameters) | set(v2.parameters))
    deltas: list[ParamDelta] = []
    for k in param_keys:
        a = v1.parameters.get(k)
        b = v2.parameters.get(k)
        deltas.append(ParamDelta(name=k, v1_value=a, v2_value=b, changed=(a != b)))

    family_changed = v1.operator_family != v2.operator_family

    # Behavioral divergence — only when both sides recovered.
    divergence: BehavioralDivergence | None = None
    if v1.recovered and v2.recovered:
        # Use the union of inputs from both traces. If both families are
        # in the predictor table, compute predictions and compare.
        combined = sorted(set(_trace_inputs(trace_v1)) | set(_trace_inputs(trace_v2)))
        match = 0
        diverge = 0
        for x in combined:
            p1 = _predict(v1, x)
            p2 = _predict(v2, x)
            if p1 is None or p2 is None:
                # one side's family not in predictor table
                continue
            if p1 == p2:
                match += 1
            else:
                diverge += 1
        n = match + diverge
        if n > 0:
            divergence = BehavioralDivergence(
                inputs_compared=n,
                predictions_matching=match,
                predictions_diverging=diverge,
            )
        else:
            notes.append(
                "Cannot compute behavioral divergence: predictor "
                f"unavailable for one of the families "
                f"({v1.operator_family!r}, {v2.operator_family!r})."
            )
    elif not v1.recovered and v2.recovered:
        notes.append(
            "v1 returned no_recovery; v2 was recoverable. Agent appears to have simplified into a known rule class."
        )
    elif v1.recovered and not v2.recovered:
        notes.append(
            "v2 returned no_recovery; v1 was recoverable. Agent appears to have departed from a known rule class — investigate model update, prompt drift, or context corruption."
        )
    else:
        notes.append(
            "Both sides returned no_recovery. Cannot determine spec drift; recover-side fallbacks (compliance check against a stated spec) recommended."
        )

    return SpecDiff(
        v1=v1,
        v2=v2,
        family_changed=family_changed,
        family_v1=v1.operator_family,
        family_v2=v2.operator_family,
        parameter_deltas=deltas,
        behavioral_divergence=divergence,
        fingerprint=_diff_fingerprint(v1, v2),
        notes=notes,
    )


def render_diff_report_md(diff: SpecDiff) -> str:
    """Render a SpecDiff as audit-grade Markdown — the human-facing
    drift report."""
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines: list[str] = [
        "# Behavioral Specification Drift Report",
        "",
        f"**Generated (UTC):** {iso}",
        f"**Diff fingerprint:** `{diff.fingerprint}`",
        "",
        "## Recovered specifications",
        "",
        "| Side | Trace | Observations | Recovered rule | Status |",
        "|---|---|---:|---|---|",
        f"| v1 | `{diff.v1.trace_path}` | {diff.v1.n_observations} | `{diff.v1.decision_rule}` | {diff.v1.proof_status} |",
        f"| v2 | `{diff.v2.trace_path}` | {diff.v2.n_observations} | `{diff.v2.decision_rule}` | {diff.v2.proof_status} |",
        "",
    ]

    # Family / structure change
    lines.append("## Structural diff")
    lines.append("")
    if diff.family_changed:
        lines.append(f"- **Family changed**: `{diff.family_v1}` → `{diff.family_v2}`")
    else:
        lines.append(f"- Family unchanged: `{diff.family_v1}`")
    lines.append("")

    # Parameter-level
    if diff.parameter_deltas:
        lines.append("### Parameter deltas")
        lines.append("")
        lines.append("| Parameter | v1 | v2 | Changed |")
        lines.append("|---|---:|---:|---|")
        for d in diff.parameter_deltas:
            mark = "✗" if d.changed else "✓"
            lines.append(f"| `{d.name}` | `{d.v1_value}` | `{d.v2_value}` | {mark} |")
        lines.append("")

    # Behavioral divergence
    if diff.behavioral_divergence is not None:
        bd = diff.behavioral_divergence
        lines.append("## Behavioral divergence")
        lines.append("")
        lines.append(
            f"Over the union of {bd.inputs_compared} unique inputs observed across both traces:"
        )
        lines.append("")
        lines.append(
            f"- Predictions matching: **{bd.predictions_matching}** ({(1 - bd.divergence_rate) * 100:.1f}%)"
        )
        lines.append(
            f"- Predictions diverging: **{bd.predictions_diverging}** ({bd.divergence_rate * 100:.1f}%)"
        )
        lines.append("")

    # K-bound certificates side-by-side
    lines.append("## Sample-complexity certificates")
    lines.append("")
    lines.append("| Side | K used | K lower bound | Margin | Consistency |")
    lines.append("|---|---:|---:|---:|---:|")
    for s in (diff.v1, diff.v2):
        lo = "—" if s.k_lower_bound is None else str(s.k_lower_bound)
        mg = "—" if s.margin is None else f"{s.margin}×"
        lines.append(f"| {s.label} | {s.k_used} | {lo} | {mg} | {s.consistency_score:.4f} |")
    lines.append("")

    # Notes
    if diff.notes:
        lines.append("## Notes")
        lines.append("")
        for n in diff.notes:
            lines.append(f"- {n}")
        lines.append("")

    # Recommended action
    lines.append("## Recommended action")
    lines.append("")
    if diff.family_changed:
        lines.append(
            "- **Family changed** between trace captures. The agent is now "
            "implementing a structurally different rule class than before. "
            "Investigate (a) model substitution, (b) major prompt rewrite, "
            "(c) tool-set change, (d) deployment to a different environment."
        )
    elif any(d.changed for d in diff.parameter_deltas):
        lines.append(
            "- **Parameters drifted within the same family**. The agent is "
            "still following the same rule class but with different constants. "
            "Investigate (a) silent model update, (b) configuration change, "
            "(c) prompt parameter edit, (d) data-distribution shift in inputs."
        )
    elif diff.behavioral_divergence and diff.behavioral_divergence.divergence_rate > 0.05:
        lines.append(
            "- Specs reported as identical but predictions diverge on >5% of "
            "the input union. Investigate predictor table coverage or possible "
            "non-determinism in the agent."
        )
    else:
        lines.append(
            "- No structural or parametric drift detected. Behavioral "
            "specification is stable across the two trace captures."
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*Generated by kbound — `kbound.diff.diff_traces()`. The "
        "diff fingerprint is bound to the recovered specs and can be "
        "regenerated by re-running on the same input traces.*"
    )
    return "\n".join(lines)
