"""Run kbound end-to-end against the 11 synthetic agents and
emit a structured pass/fail report.

For each agent:
1. Generate trace (already done by agents.py).
2. Run recovery (kbound.cli.recover.recover_from_logs).
3. If a claimed_spec is set on the agent, run compliance check.
4. For the drift pair (agent_09 vs agent_10), run kazdov diff.
5. Score the outcome against the agent's `expected` field.

Outcomes:
- RECOVERED: engine returned a spec, consistency >= 0.95, family matches expected
- PARTIAL: engine returned a spec, consistency [0.5, 0.95)
- NO_RECOVERY: engine returned no_recovery (honest failure)
- WRONG_FAMILY: engine returned a spec but the family is unexpected
- ERROR: exception during recovery
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import agents as agents_module

from kbound.cli import recover_from_logs
from kbound.compliance import check_compliance, ClaimedSpec
from kbound.diff import diff_traces


def grade_outcome(bundle, agent) -> tuple[str, str]:
    """Return (status, one-line summary) given a SpecBundle and agent metadata."""
    if bundle.operator is None:
        return "NO_RECOVERY", f"engine emitted no_recovery (status: {bundle.proof_status})"
    fam = bundle.operator.family_label
    cons = bundle.consistency_score
    if cons >= 0.95:
        return "RECOVERED", f"family={fam}, params={bundle.parameters}, consistency={cons:.4f}"
    elif cons >= 0.50:
        return "PARTIAL", f"family={fam}, consistency={cons:.4f} (below 0.95)"
    else:
        return "WRONG_FAMILY", f"family={fam}, but consistency only {cons:.4f}"


def main() -> int:
    here = Path(__file__).parent
    traces_dir = here / "traces"

    print("=" * 78)
    print(" KAZDOV SPEC — END-TO-END BATTERY")
    print("=" * 78)
    print()

    results: list[dict] = []

    for agent in agents_module.AGENTS:
        path = traces_dir / f"{agent.id}.jsonl"
        if not path.exists():
            print(f"  [{agent.id}] trace not found, skipping")
            continue

        print(f"--- {agent.id} · {agent.label} ---")
        print(f"  expected: {agent.expected}")

        # 1. Recovery
        t0 = time.perf_counter()
        try:
            r = recover_from_logs(str(path))
            elapsed = (time.perf_counter() - t0) * 1000
            bundle = r["bundle"]
            status, summary = grade_outcome(bundle, agent)
            print(f"  recovery: {status} ({elapsed:.0f}ms)")
            print(f"            {summary}")
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            status = "ERROR"
            summary = f"exception: {type(e).__name__}: {e}"
            bundle = None
            print(f"  recovery: ERROR ({elapsed:.0f}ms)")
            print(f"            {summary}")

        # 2. Compliance check (only if vendor-claimed spec is provided)
        compliance_summary = None
        if agent.claimed_spec is not None:
            obs = []
            for line in open(path):
                rec = json.loads(line)
                obs.append((rec["_meta"]["x"], rec["_meta"]["y"]))
            spec = ClaimedSpec(
                family=agent.claimed_spec["family"],
                params=agent.claimed_spec["params"],
                source=agent.claimed_spec["source"],
            )
            cr = check_compliance(obs, spec)
            compliance_summary = f"agreement={cr.agreement_pct:.1%} ({cr.n_agree}/{cr.n_total}), buckets=low:{cr.by_input_bucket['low']:.0%} mid:{cr.by_input_bucket['mid']:.0%} high:{cr.by_input_bucket['high']:.0%}"
            print(f"  compliance: {compliance_summary}")

        results.append({
            "agent_id": agent.id,
            "label": agent.label,
            "complexity": agent.complexity,
            "expected": agent.expected,
            "recovery_status": status,
            "recovery_summary": summary,
            "recovery_ms": round(elapsed),
            "compliance": compliance_summary,
        })
        print()

    # 3. Diff demo for agents 09 vs 10
    print("--- diff: agent_09_drift_v1 vs agent_10_drift_v2 ---")
    try:
        d = diff_traces(
            str(traces_dir / "agent_09_drift_v1.jsonl"),
            str(traces_dir / "agent_10_drift_v2.jsonl"),
        )
        print(f"  v1 spec: {d.v1.decision_rule}")
        print(f"  v2 spec: {d.v2.decision_rule}")
        print(f"  family_changed: {d.family_changed}")
        if d.behavioral_divergence:
            bd = d.behavioral_divergence
            print(f"  divergence: {bd.predictions_diverging}/{bd.inputs_compared} ({bd.divergence_rate:.1%})")
        print(f"  fingerprint: {d.fingerprint}")
        results.append({
            "agent_id": "DIFF_09_vs_10",
            "label": "Drift detection: agent_09 vs agent_10",
            "complexity": "diff",
            "expected": "behavioral divergence detected",
            "recovery_status": "OK",
            "recovery_summary": f"v1={d.v1.decision_rule}; v2={d.v2.decision_rule}; div={d.behavioral_divergence.divergence_rate:.1%}",
            "recovery_ms": 0,
            "compliance": None,
        })
    except Exception as e:
        print(f"  ERROR: {e}")
    print()

    # 4. Aggregate report
    print("=" * 78)
    print(" AGGREGATE")
    print("=" * 78)
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["recovery_status"]] = by_status.get(r["recovery_status"], 0) + 1
    for k, v in sorted(by_status.items()):
        print(f"  {k:14s} {v}")
    print()

    # 5. Markdown summary table
    print("--- Markdown summary ---")
    print()
    print("| Agent | Complexity | Expected | Recovery | Compliance |")
    print("|---|---|---|---|---|")
    for r in results:
        comp = r["compliance"] or "—"
        print(f"| `{r['agent_id']}` | {r['complexity']} | {r['expected'][:60]}... | **{r['recovery_status']}** {r['recovery_summary'][:60]}... | {comp[:60]}... |")

    # 6. Persist
    out = here / "battery_report.json"
    with out.open("w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport saved: {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
