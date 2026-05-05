"""Run replacement-code synthesis against the Flavor A enterprise agents
and emit the generated code + ROI report for each."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import enterprise_agents as ea

from kbound.cli import recover_from_logs
from kbound.synth import (
    synthesize_replacement,
    render_replacement_report_md,
    UnsupportedFamilyError,
)


def main() -> int:
    here = Path(__file__).parent
    traces = here / "enterprise_traces"
    out_dir = here / "synthesized_replacements"
    out_dir.mkdir(exist_ok=True)

    print()
    print("═" * 78)
    print(" KAZDOV SPEC — REPLACEMENT SYNTHESIS")
    print(" The fix complement: where recovery succeeded, emit the code that")
    print(" replaces the LLM call entirely.")
    print("═" * 78)
    print()

    summary_rows: list[dict] = []

    for agent in ea.AGENTS:
        path = traces / f"{agent.id}.jsonl"
        if not path.exists():
            continue
        try:
            r = recover_from_logs(str(path))
            rb = synthesize_replacement(r["bundle"])
        except UnsupportedFamilyError as e:
            print(f"⚪ [{agent.flavor}] {agent.company:15s} {agent.product_name[:30]:30s}  → no spec recovered, cannot synthesize")
            continue
        except Exception as e:
            print(f"❌ [{agent.flavor}] {agent.company:15s} {agent.product_name[:30]:30s}  → ERROR: {e}")
            continue

        # Save the artifacts
        report = render_replacement_report_md(rb)
        report_path = out_dir / f"{agent.id}_replacement.md"
        report_path.write_text(report)

        # Per-language source files for direct copy/paste
        lang_ext = {"python": "py", "typescript": "ts", "rust": "rs", "cedar": "cedar"}
        for lang, src in rb.sources.items():
            ext = lang_ext.get(lang, "txt")
            (out_dir / f"{agent.id}_decision.{ext}").write_text(src)

        flavor_emoji = {"A": "🟢", "C": "🟠", "D": "🔵", "E": "🔴"}.get(agent.flavor, "⚪")
        roi_high = rb.ROI_estimate["scenarios"]["high_volume_5m_calls"]
        roi_mid = rb.ROI_estimate["scenarios"]["mid_volume_500k_calls"]
        safe = "✅ safe" if rb.is_safe_to_substitute else "⚠️  validate"
        print(f"{flavor_emoji} [{agent.flavor}] {agent.company:15s} {agent.product_name[:30]:30s}")
        print(f"     rule:        {rb.decision_rule}")
        print(f"     consistency: {rb.consistency_score} ({safe})")
        print(f"     ROI @ 500K/mo: ${roi_mid['monthly_savings_usd']:,.0f} saved")
        print(f"     ROI @ 5M/mo:   ${roi_high['monthly_savings_usd']:,.0f} saved ({roi_high['savings_pct']}%)")
        print(f"     targets emitted: {rb.target_languages}")
        if rb.limitations:
            print(f"     limitations:")
            for lim in rb.limitations:
                print(f"       · {lim[:90]}")
        print(f"     artifacts:   {report_path.relative_to(here)}")
        print()

        summary_rows.append({
            "agent_id": agent.id,
            "company": agent.company,
            "product": agent.product_name,
            "vertical": agent.vertical,
            "flavor": agent.flavor,
            "decision_rule": rb.decision_rule,
            "consistency": rb.consistency_score,
            "safe_to_substitute": rb.is_safe_to_substitute,
            "roi_500k_calls_usd": roi_mid["monthly_savings_usd"],
            "roi_5m_calls_usd": roi_high["monthly_savings_usd"],
            "fingerprint": rb.fingerprint,
            "limitations": rb.limitations,
        })

    # Aggregate
    print("─" * 78)
    print(" AGGREGATE")
    print("─" * 78)
    safe_count = sum(1 for r in summary_rows if r["safe_to_substitute"])
    print(f"  agents with synthesized replacement:  {len(summary_rows)}")
    print(f"  safe to substitute (consistency 1.0): {safe_count}")
    print(f"  needs validation before substitute:   {len(summary_rows) - safe_count}")
    if summary_rows:
        total_500k = sum(r["roi_500k_calls_usd"] for r in summary_rows)
        total_5m = sum(r["roi_5m_calls_usd"] for r in summary_rows)
        print(f"  total ROI if all 5 substituted:")
        print(f"    @ 500K calls/mo each → ${total_500k:>10,.0f} / mo  → ${total_500k * 12:>12,.0f} / yr")
        print(f"    @ 5M calls/mo each   → ${total_5m:>10,.0f} / mo  → ${total_5m * 12:>12,.0f} / yr")

    # Persist summary JSON
    summary_path = out_dir / "synthesis_summary.json"
    summary_path.write_text(json.dumps(summary_rows, indent=2, default=str))
    print()
    print(f"Summary -> {summary_path.relative_to(here)}")
    print(f"Per-agent reports + source files in {out_dir.relative_to(here)}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
