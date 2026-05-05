"""Run kbound end-to-end against the 15 enterprise agents and emit
a full audit report — by flavor (A clean recover / B honest no_recovery /
C noisy compliance / D drift pair / E vendor lie).

This is the paper-grade evidence run: same engine, real-flavored fixtures.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import enterprise_agents as ea

from kbound.cli import recover_from_logs
from kbound.compliance import (
    check_compliance, ClaimedSpec,
    render_legal_counterexample_csv,
    render_remediation_sla,
)
from kbound.diff import diff_traces


def run_one(agent: ea.EnterpriseAgent, trace_path: Path) -> dict:
    out: dict = {
        "id": agent.id,
        "company": agent.company,
        "product": agent.product_name,
        "vertical": agent.vertical,
        "flavor": agent.flavor,
        "expected_outcome": agent.expected_outcome,
    }

    # Recovery
    t0 = time.perf_counter()
    try:
        r = recover_from_logs(str(trace_path))
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        b = r["bundle"]
        if b.operator is None:
            out["recovery"] = {"status": "NO_RECOVERY", "elapsed_ms": elapsed_ms}
        else:
            out["recovery"] = {
                "status": "RECOVERED" if b.consistency_score >= 0.95 else "PARTIAL",
                "family": b.operator.family_label,
                "params": dict(b.parameters),
                "decision_rule": b.decision_rule,
                "consistency": round(b.consistency_score, 4),
                "k_used": b.k_used,
                "k_lower_bound": b.k_lower_bound,
                "margin": b.margin,
                "elapsed_ms": elapsed_ms,
            }
    except Exception as e:
        out["recovery"] = {"status": "ERROR", "error": str(e)}

    # Compliance check (if vendor-claimed spec is set)
    if agent.claimed_spec is not None:
        obs = []
        for line in trace_path.open():
            rec = json.loads(line)
            obs.append((rec["_meta"]["x"], rec["_meta"]["y"]))
        spec = ClaimedSpec(**agent.claimed_spec)
        cr = check_compliance(obs, spec)
        out["compliance"] = {
            "claimed_family": spec.family,
            "claimed_params": spec.params,
            "agreement_pct": round(cr.agreement_pct, 4),
            "n_agree": cr.n_agree,
            "n_violations": cr.n_violations,
            "n_total": cr.n_total,
            "compliant_at_95": cr.is_compliant(),
            "by_input_bucket": cr.by_input_bucket,
            "first_counterexamples": [
                {"x": ce.x, "y_observed": ce.y_observed, "y_predicted": ce.y_predicted}
                for ce in cr.counterexamples[:5]
            ],
        }
    return out


def main() -> int:
    here = Path(__file__).parent
    traces = here / "enterprise_traces"

    print()
    print("═" * 78)
    print(" KAZDOV SPEC — ENTERPRISE AGENT BATTERY (15 agents, 13 verticals)")
    print("═" * 78)
    print()

    results: list[dict] = []
    for agent in ea.AGENTS:
        path = traces / f"{agent.id}.jsonl"
        if not path.exists():
            print(f"  [skip] missing trace for {agent.id}")
            continue
        r = run_one(agent, path)
        results.append(r)

        # Pretty-print
        rec = r["recovery"]
        comp = r.get("compliance")
        flavor_color = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔵", "E": "🔴"}.get(agent.flavor, "⚪")

        print(f"{flavor_color} [{agent.flavor}] {agent.company:15s} · {agent.product_name[:35]:35s} · {agent.vertical}")
        if rec["status"] == "RECOVERED":
            print(f"    recovery: ✅ RECOVERED  rule={rec['decision_rule']}  consistency={rec['consistency']}  ({rec['elapsed_ms']}ms)")
        elif rec["status"] == "PARTIAL":
            print(f"    recovery: 🟡 PARTIAL  consistency={rec['consistency']}  ({rec['elapsed_ms']}ms)")
        elif rec["status"] == "NO_RECOVERY":
            print(f"    recovery: ⚪ NO_RECOVERY  (engine refused honestly, {rec['elapsed_ms']}ms)")
        else:
            print(f"    recovery: ❌ ERROR  {rec.get('error', '?')}")
        if comp is not None:
            agree_emoji = "✅" if comp["compliant_at_95"] else "🔴"
            print(f"    compliance vs vendor claim: {agree_emoji} {comp['agreement_pct']:.1%}  ({comp['n_agree']}/{comp['n_total']})  buckets={comp['by_input_bucket']}")
        print()

    # Drift detection between Hertz v1 and v2
    print("─" * 78)
    print(" DRIFT DETECTION — Hertz ClaimsClassifier v1 → v2 (silent vendor update)")
    print("─" * 78)
    try:
        d = diff_traces(
            str(traces / "13_hertz_classifier_v1.jsonl"),
            str(traces / "14_hertz_classifier_v2.jsonl"),
        )
        print(f"  v1 spec:        {d.v1.decision_rule}")
        print(f"  v2 spec:        {d.v2.decision_rule}")
        print(f"  family changed: {d.family_changed}")
        if d.behavioral_divergence:
            bd = d.behavioral_divergence
            print(f"  divergence:     {bd.predictions_diverging}/{bd.inputs_compared} = {bd.divergence_rate:.1%}")
        print(f"  fingerprint:    {d.fingerprint}")
        results.append({
            "id": "DIFF_hertz_v1_v2",
            "kind": "drift_detection",
            "v1_rule": d.v1.decision_rule,
            "v2_rule": d.v2.decision_rule,
            "family_changed": d.family_changed,
            "divergence_rate": d.behavioral_divergence.divergence_rate if d.behavioral_divergence else None,
            "fingerprint": d.fingerprint,
        })
    except Exception as e:
        print(f"  ERROR: {e}")
    print()

    # Aggregate by flavor
    print("═" * 78)
    print(" AGGREGATE BY FLAVOR")
    print("═" * 78)
    by_flavor: dict[str, list[dict]] = {}
    for r in results:
        by_flavor.setdefault(r.get("flavor", "?"), []).append(r)
    flavor_descriptions = {
        "A": "clean recoverable (engine returns spec)",
        "B": "honest no-recovery (out of catalog)",
        "C": "noisy LLM — keystone compliance use case",
        "D": "drift pair (silent vendor update)",
        "E": "vendor lie — declared X, agent does Y",
    }
    for flavor in ["A", "B", "C", "D", "E"]:
        items = by_flavor.get(flavor, [])
        if not items:
            continue
        recovered = sum(1 for r in items if r["recovery"]["status"] == "RECOVERED")
        no_rec = sum(1 for r in items if r["recovery"]["status"] == "NO_RECOVERY")
        partial = sum(1 for r in items if r["recovery"]["status"] == "PARTIAL")
        compliance_results = [r["compliance"]["agreement_pct"] for r in items if r.get("compliance")]
        print(f"  Flavor {flavor}: {flavor_descriptions[flavor]}")
        print(f"    n={len(items)}  recovered={recovered}  no_recovery={no_rec}  partial={partial}")
        if compliance_results:
            print(f"    compliance %: {[f'{c:.0%}' for c in compliance_results]}")
        print()

    # Save JSON report
    out = here / "enterprise_battery_report.json"
    with out.open("w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Full report -> {out}")

    # Save legal counterexample CSV for each Flavor C and E (where it matters)
    print()
    print("─" * 78)
    print(" SAMPLE LEGAL COUNTEREXAMPLE EXPORTS (Flavor C + E only)")
    print("─" * 78)
    csv_dir = here / "enterprise_csv_exports"
    csv_dir.mkdir(exist_ok=True)
    for r in results:
        if r.get("compliance") and r["flavor"] in ("C", "E"):
            agent = next((a for a in ea.AGENTS if a.id == r["id"]), None)
            if agent is None or not agent.claimed_spec:
                continue
            obs = []
            tp = traces / f"{agent.id}.jsonl"
            for line in tp.open():
                rec = json.loads(line)
                obs.append((rec["_meta"]["x"], rec["_meta"]["y"]))
            spec = ClaimedSpec(**agent.claimed_spec)
            cr = check_compliance(obs, spec)
            csv_text = render_legal_counterexample_csv(cr)
            csv_path = csv_dir / f"{agent.id}_counterexamples.csv"
            csv_path.write_text(csv_text)
            print(f"  -> {csv_path.name} ({len(csv_text)} bytes)")
            # Also generate the SLA template
            sla = render_remediation_sla(cr, agent.company, "Acme Corp (customer)")
            sla_path = csv_dir / f"{agent.id}_remediation_sla.md"
            sla_path.write_text(sla)
            print(f"  -> {sla_path.name} ({len(sla)} bytes)")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
