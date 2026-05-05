"""Comparison harness — Compiler vs LLM-alone on a battery of algebraic tasks.

Generates N episodes per family × M families. Runs:
  - Compiler-side: free, fast (~50ms per episode)
  - LLM-side: requires ANTHROPIC_API_KEY env var; ~$30-100 for 900 calls on Opus 4.7

If no API key, runs Compiler-only and saves a partial table.

Usage:
    export ANTHROPIC_API_KEY=...
    python3 -m kbound.tests.comparison_harness --n_per_family 50 --model claude-haiku-4-5

Output: results/comparison_<timestamp>.json + console table.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from kbound.classifier.oracle_classifier import classify_geometry
from kbound.classifier.family_id import identify_family
from kbound.solvers.dispatcher import dispatch
from kbound.solvers.llm_route import call_llm_for_query


# ----------- task generators -----------

def gen_lcg(rng: random.Random) -> tuple[list, int, int]:
    m = rng.choice([7, 11, 13, 17, 19, 23, 29, 31])
    a = rng.randrange(1, m)
    c = rng.randrange(0, m)
    xs = rng.sample(range(100), 16)
    ys = [(a * x + c) % m for x in xs]
    qx = rng.randrange(100)
    qy = (a * qx + c) % m
    return list(zip(xs, ys)), qx, qy


def gen_polycoef(rng: random.Random) -> tuple[list, int, int]:
    p = rng.choice([11, 13, 17, 19, 23, 29])
    a = rng.randrange(1, p); b = rng.randrange(0, p); c = rng.randrange(0, p)
    xs = rng.sample(range(40), 16)
    ys = [(a * x*x + b * x + c) % p for x in xs]
    qx = rng.randrange(40)
    qy = (a * qx*qx + b * qx + c) % p
    return list(zip(xs, ys)), qx, qy


def gen_modmul(rng: random.Random) -> tuple[list, int, int]:
    p = rng.choice([7, 11, 13, 17, 19, 23, 29])
    a = rng.randrange(1, p)
    xs = rng.sample(range(80), 16)
    ys = [(a * x) % p for x in xs]
    qx = rng.randrange(80)
    qy = (a * qx) % p
    return list(zip(xs, ys)), qx, qy


def gen_modinv(rng: random.Random) -> tuple[list, int, int]:
    p = rng.choice([11, 13, 17, 19, 23, 29])
    def modinv(a, m):
        a = a % m
        if a == 0: return None
        old_r, r, old_s, s = a, m, 1, 0
        while r != 0:
            q = old_r // r
            old_r, r = r, old_r - q * r
            old_s, s = s, old_s - q * s
        return old_s % m if old_r == 1 else None
    candidates = [v for v in range(1, p)]
    rng.shuffle(candidates)
    pairs = [(v, modinv(v, p)) for v in candidates if modinv(v, p) is not None][:16]
    if len(pairs) < 16:
        return None, None, None  # skip
    qx = rng.randrange(1, p)
    qy = modinv(qx, p)
    return pairs, qx, qy


def gen_modexp(rng: random.Random) -> tuple[list, int, int]:
    p = rng.choice([7, 11, 13, 17, 19, 23])
    a = rng.randrange(2, min(p, 10))
    xs = list(range(2, 18))  # exponents
    ys = [pow(a, x, p) for x in xs]
    qx = rng.randrange(2, 30)
    qy = pow(a, qx, p)
    return list(zip(xs, ys)), qx, qy


def gen_modadd(rng: random.Random) -> tuple[list, int, int]:
    p = rng.choice([7, 11, 13, 17, 19])
    pairs = []
    for _ in range(16):
        a = rng.randrange(40); b = rng.randrange(40)
        pairs.append(((a, b), (a + b) % p))
    qx = (rng.randrange(40), rng.randrange(40))
    qy = (qx[0] + qx[1]) % p
    return pairs, qx, qy


def gen_recurrence_fib(rng: random.Random) -> tuple[list, int, int]:
    m = rng.choice([5, 7, 11, 13])
    a, b = rng.randrange(1, m), rng.randrange(1, m)
    seq = [a, b]
    for _ in range(20):
        seq.append((seq[-1] + seq[-2]) % m)
    examples = [(n, seq[n]) for n in range(16)]
    qn = rng.randrange(16, 21)
    return examples, qn, seq[qn]


def gen_boolean_2input(rng: random.Random) -> tuple[list, tuple, int]:
    # Random truth table
    tt = [rng.choice([0, 1]) for _ in range(4)]
    pairs = []
    for _ in range(16):
        a, b = rng.choice([0, 1]), rng.choice([0, 1])
        pairs.append(((a, b), tt[2*a + b]))
    qa, qb = rng.choice([0, 1]), rng.choice([0, 1])
    return pairs, (qa, qb), tt[2*qa + qb]


GENERATORS = {
    "lcg": gen_lcg,
    "polycoef": gen_polycoef,
    "modmul": gen_modmul,
    "modinv": gen_modinv,
    "modexp": gen_modexp,
    "mod_p_add": gen_modadd,
    "recurrence_fib": gen_recurrence_fib,
    "boolean_2input": gen_boolean_2input,
}


# ----------- runners -----------

def run_compiler(examples, query) -> tuple[Any, dict]:
    """Run the full induction compiler. Returns (predicted_answer, metadata)."""
    geom = classify_geometry(examples)
    family = None
    if geom["geometry"] in ("algebraic", "borderline"):
        family = identify_family(examples, geom)
    result = dispatch(geom["geometry"], family, examples, query, use_llm_fallback=False)
    return result.get("answer"), {
        "geometry": geom["geometry"],
        "family": family,
        "solver_used": result["solver_used"],
        "confidence": result.get("confidence"),
    }


def run_llm(examples, query, model: str) -> tuple[Any, dict]:
    """Call LLM directly (no compiler routing)."""
    result = call_llm_for_query(examples, query, model=model)
    return result.get("answer"), result


# ----------- main -----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n_per_family", type=int, default=20)
    ap.add_argument("--model", default="claude-haiku-4-5")
    ap.add_argument("--families", nargs="+", default=list(GENERATORS.keys()))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--llm", action="store_true",
                    help="Run LLM-side. Requires ANTHROPIC_API_KEY.")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.llm and not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠ --llm flag set but no ANTHROPIC_API_KEY. Skipping LLM side.")
        args.llm = False

    print(f"=== Comparison harness ===")
    print(f"  families: {args.families}")
    print(f"  n_per_family: {args.n_per_family}")
    print(f"  llm side: {args.llm}  (model: {args.model})")
    print()

    rng = random.Random(args.seed)
    summary = {}

    for family in args.families:
        if family not in GENERATORS:
            print(f"  ✗ unknown family: {family}, skipping")
            continue

        compiler_correct = 0; llm_correct = 0
        n_actual = 0
        compiler_times = []; llm_times = []

        for i in range(args.n_per_family):
            res = GENERATORS[family](rng)
            if res[0] is None:
                continue
            examples, query, true_y = res
            n_actual += 1

            # Compiler
            t0 = time.perf_counter()
            comp_answer, comp_meta = run_compiler(examples, query)
            compiler_times.append(time.perf_counter() - t0)
            if comp_answer == true_y:
                compiler_correct += 1

            # LLM (optional)
            if args.llm:
                t0 = time.perf_counter()
                llm_answer, _ = run_llm(examples, query, args.model)
                llm_times.append(time.perf_counter() - t0)
                if llm_answer == true_y:
                    llm_correct += 1

        comp_acc = compiler_correct / n_actual if n_actual else 0
        llm_acc  = llm_correct / n_actual if n_actual else 0
        gap = (comp_acc / max(llm_acc, 0.001)) if args.llm else None

        summary[family] = {
            "n": n_actual,
            "compiler_acc": comp_acc,
            "llm_acc": llm_acc if args.llm else None,
            "gap_x": gap,
            "compiler_mean_ms": (sum(compiler_times) / len(compiler_times) * 1000) if compiler_times else None,
            "llm_mean_ms": (sum(llm_times) / len(llm_times) * 1000) if llm_times else None,
        }
        print(f"  {family:<18s}  n={n_actual:>3d}  compiler={comp_acc:.2%}  "
              f"{'llm=' + format(llm_acc, '.2%') if args.llm else ''}  "
              f"{'gap=' + format(gap, '.1f') + 'x' if args.llm else ''}")

    print()
    print("==== SUMMARY ====")
    print(f"{'Family':<18} {'n':>5} {'Compiler':>10} {'LLM':>10} {'Gap':>8}")
    print("-" * 60)
    for family, s in summary.items():
        gap_str = f"{s['gap_x']:.1f}x" if s.get("gap_x") else "—"
        llm_str = f"{s['llm_acc']:.2%}" if s.get("llm_acc") is not None else "—"
        print(f"{family:<18} {s['n']:>5} {s['compiler_acc']:>9.2%}  {llm_str:>9}  {gap_str:>8}")

    if args.out is None:
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        out_dir = Path(__file__).parent.parent / "results"
        out_dir.mkdir(exist_ok=True)
        args.out = out_dir / f"comparison_{ts}.json"

    with open(args.out, "w") as f:
        json.dump({"args": vars(args), "summary": summary}, f, indent=2, default=str)
    print(f"\nResults saved: {args.out}")


if __name__ == "__main__":
    main()
