"""kbound CLI — `kbound recover --logs <file.jsonl> --out <out.md>`.

Pipeline:
  1. Parse JSONL trace via openai_logs ingester
  2. Detect query trace (assistant content '?' or empty)
  3. Run recovery via the existing _run_pipeline engine
  4. Render Markdown + YAML

Usage:
    python -m kbound.cli \\
        --logs path/to/trace.jsonl --out spec.md [--yaml spec.yaml]

Or after pip install:
    kbound recover --logs trace.jsonl --out spec.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kbound._pipeline import _build_explain_stages, _run_pipeline
from kbound.formatter import build_bundle, to_markdown, to_yaml
from kbound.ingest.openai_logs import detect_query, parse_jsonl_trace


def recover_from_logs(logs_path: str, query_x: int | None = None) -> dict:
    """End-to-end: JSONL → spec_md + spec_yaml + bundle + raw backend result."""
    pairs = parse_jsonl_trace(logs_path)
    if query_x is None:
        query_x = detect_query(logs_path)
    if query_x is None:
        # No query line in trace — pick first observation's input as proxy
        query_x = pairs[0][0]
        # Drop it from pairs to avoid trivial recovery
        # Actually keep it; the pipeline tolerates it.

    # Coerce to format expected by _run_pipeline:
    # examples = list[(int|list[int], int)], query = same shape as input
    examples = [(int(x), int(y)) for x, y in pairs]
    result = _run_pipeline(
        examples=examples,
        query=int(query_x),
        verbose=True,
    )
    # _run_pipeline returns geometry/family/etc. at the top level + a trace dict
    # We need to provide a final-style dict to build_bundle
    backend_response = {
        "answer": result["answer"],
        "verified": result["verified"],
        "elapsed_ms": result["elapsed_ms"],
        "geometry": result["geometry"],
        "family": result["family"],
        "solver_used": result["solver_used"],
        "confidence": result["confidence"],
        "rationale": result["rationale"],
        "trace": result["trace"],
        "stages": _build_explain_stages(result),
        "final": {
            "family": result["family"],
            "geometry": result["geometry"],
            "solver_used": result["solver_used"],
        },
    }
    bundle = build_bundle(backend_response, n_observations=len(pairs), query_input=query_x)
    return {
        "bundle": bundle,
        "spec_md": to_markdown(bundle),
        "spec_yaml": to_yaml(bundle),
        "raw": backend_response,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="kbound", description="Recover behavioral spec from agent traces."
    )
    sub = p.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("recover", help="Recover spec from a JSONL trace file.")
    rec.add_argument("--logs", required=True, help="Path to OpenAI Chat Completions JSONL trace.")
    rec.add_argument("--out", default="-", help="Output path for spec.md (- = stdout).")
    rec.add_argument("--yaml", default=None, help="Optional output path for spec.yaml.")
    rec.add_argument("--query", type=int, default=None, help="Query input (overrides auto-detect).")

    df = sub.add_parser(
        "diff",
        help="Diff behavioral specs recovered from two trace captures. "
        "Surfaces parameter drift, family change, and behavioral divergence.",
    )
    df.add_argument("--v1", required=True, help="Path to the earlier (baseline) JSONL trace.")
    df.add_argument("--v2", required=True, help="Path to the later (current) JSONL trace.")
    df.add_argument("--out", default="-", help="Output path for the drift report (- = stdout).")

    # NOTE: `synthesize` is intentionally NOT registered as a CLI subcommand
    # for May 2026. The kbound.synth module remains importable for
    # internal experimentation, but the customer-facing surface is
    # observability + traceability, not "replace the LLM." See synth.py
    # banner. Re-enable when research on substitution-fit is complete.

    args = p.parse_args(argv)

    if args.command == "recover":
        result = recover_from_logs(args.logs, query_x=args.query)
        if args.out == "-":
            print(result["spec_md"])
        else:
            Path(args.out).write_text(result["spec_md"])
            print(f"✓ wrote {args.out}", file=sys.stderr)
        if args.yaml:
            Path(args.yaml).write_text(result["spec_yaml"])
            print(f"✓ wrote {args.yaml}", file=sys.stderr)
        return 0

    if args.command == "diff":
        # Imported lazily so `recover` does not pay the diff-module import cost.
        from kbound.diff import diff_traces, render_diff_report_md

        diff = diff_traces(args.v1, args.v2)
        report = render_diff_report_md(diff)
        if args.out == "-":
            print(report)
        else:
            Path(args.out).write_text(report)
            print(f"✓ wrote {args.out}", file=sys.stderr)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
