"""10 synthetic agents with diverse complexity profiles for end-to-end
test of kbound.

Each agent is a black-box function `int -> int` (1D in/out, matching the
engine's current input shape). Agents range from "trivially recoverable"
to "engine-should-honestly-emit-no_recovery."

Goal: exercise the engine across the full spectrum of behavior so we
can observe both wins (clean recoveries with K-bound certs) and honest
failures (no_recovery on agents outside the catalog).
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass(frozen=True)
class Agent:
    """A synthetic test agent."""
    id: str                                # short identifier
    label: str                             # human-friendly name
    description: str                       # what it claims to do (vendor-side)
    complexity: str                        # easy / medium / hard / out-of-catalog
    expected: str                          # what we expect engine to do
    fn: Callable[[int], int]               # the actual decision function
    input_universe: range                  # range of inputs to sample from
    n_traces: int = 40
    # Optional: vendor-claimed spec for compliance verification
    claimed_spec: Optional[dict] = None


# ──────────────────────────────────────────────────────────────────
# Agent definitions — 10 diverse cases
# ──────────────────────────────────────────────────────────────────

def _classic_lcg(x: int) -> int:
    return (7 * x + 2) % 11


def _polynomial(x: int) -> int:
    # f(x) = (3x^2 + 5x + 1) mod 13
    return (3 * x * x + 5 * x + 1) % 13


def _recurrence_seed_factor(x: int) -> int:
    # Output = (x-th Fibonacci-like number mod 17), bounded by lookup
    # We pre-compute the sequence so it's deterministic and 1D in/out.
    seq = [3, 7]
    for _ in range(2, 80):
        seq.append((2 * seq[-1] + 3 * seq[-2]) % 17)
    return seq[x % len(seq)]


def _modular_exp(x: int) -> int:
    # f(x) = 2^x mod 13
    return pow(2, x, 13)


def _composed_categorical(x: int) -> int:
    # First apply (7x+2) mod 11, then bucket into 0/1/2 (APPROVE/REVIEW/DENY)
    inner = (7 * x + 2) % 11
    if inner <= 3:
        return 0      # APPROVE
    elif inner <= 7:
        return 1      # REVIEW
    else:
        return 2      # DENY


def _multi_feature_packed(x: int) -> int:
    # Simulate multi-feature by packing 2 values into the integer:
    # high 8 bits = "credit_score", low 8 bits = "tier"
    # Decision: (2*score + 3*tier) mod 100
    score = (x >> 8) & 0xFF
    tier = x & 0xFF
    return (2 * score + 3 * tier) % 100


def _pure_threshold(x: int) -> int:
    # Pure threshold rule: 1 if x >= 700 else 0
    return 1 if x >= 700 else 0


def _noisy_lcg(x: int) -> int:
    # Mostly (7x+2) mod 11 but with 30% noise — returns random output
    rng = random.Random(x)  # deterministic per x
    if rng.random() < 0.30:
        return rng.randint(0, 10)
    return (7 * x + 2) % 11


# Drift agent: helper builds two halves
def _drift_agent_v1(x: int) -> int:
    return (7 * x + 2) % 11


def _drift_agent_v2(x: int) -> int:
    return (11 * x + 5) % 13


def _meta_escalation(x: int) -> int:
    # Multi-criteria escalation: based on x's parity, magnitude, AND last digit
    # Returns 0/1/2/3 based on combination — outside catalog rule classes
    parity = x % 2
    big = 1 if x >= 100 else 0
    last = x % 10
    if parity == 0 and big == 0 and last < 5:
        return 0
    elif parity == 0 and big == 1:
        return 1
    elif parity == 1 and last >= 5:
        return 2
    else:
        return 3


AGENTS: list[Agent] = [
    Agent(
        id="agent_01_lcg_easy",
        label="Customer router (LCG)",
        description="A vendor-deployed routing agent that maps customer IDs to one of 11 service queues.",
        complexity="easy",
        expected="recover (7·x + 2) mod 11 with K=40, consistency 1.0",
        fn=_classic_lcg,
        input_universe=range(1, 250),
        claimed_spec={"family": "linear_residual", "params": {"a": 7, "c": 2, "m": 11}, "source": "vendor system prompt"},
    ),
    Agent(
        id="agent_02_polynomial",
        label="Risk scorer (polynomial)",
        description="A vendor-deployed risk scoring agent applying a quadratic polynomial mod 13.",
        complexity="medium",
        expected="recover polynomial threshold rule with coeffs [1, 5, 3] mod 13",
        fn=_polynomial,
        input_universe=range(0, 100),
    ),
    Agent(
        id="agent_03_recurrence",
        label="State machine (linear recurrence)",
        description="A vendor agent that emits a Fibonacci-like sequence value indexed by step.",
        complexity="medium",
        expected="recover linear recurrence order-2",
        fn=_recurrence_seed_factor,
        input_universe=range(2, 80),
    ),
    Agent(
        id="agent_04_modexp",
        label="Cryptographic primitive (mod exp)",
        description="A vendor agent computing 2^x mod 13 — used in custom signature/encryption flows.",
        complexity="medium",
        expected="recover exponential pattern rule",
        fn=_modular_exp,
        input_universe=range(0, 100),
    ),
    Agent(
        id="agent_05_composed_categorical",
        label="Loan approval (composed: LCG → categorical bucket)",
        description="A vendor agent that applies a hidden modular hash, then maps the result to APPROVE / REVIEW / DENY (0/1/2).",
        complexity="hard",
        expected="probably no_recovery — composition + categorical output is outside the 1D-int catalog",
        fn=_composed_categorical,
        input_universe=range(1, 250),
    ),
    Agent(
        id="agent_06_multi_feature_packed",
        label="Credit decision (multi-feature)",
        description="Real production pattern: agent reads (score, tier) and outputs (2·score + 3·tier) mod 100. We pack into a single int for testing.",
        complexity="hard",
        expected="possibly recovers as linear residual with a bigger modulus (m=100), but the underlying multi-feature semantics are lost",
        fn=_multi_feature_packed,
        input_universe=range(1, 65000),
    ),
    Agent(
        id="agent_07_pure_threshold",
        label="Eligibility gate (threshold)",
        description="Pure threshold rule: returns 1 if x ≥ 700 else 0. Common in approval flows.",
        complexity="hard",
        expected="no_recovery — threshold rules are not in the engine's modular/polynomial/recurrence catalog",
        fn=_pure_threshold,
        input_universe=range(1, 1500),
    ),
    Agent(
        id="agent_08_noisy_lcg",
        label="Stochastic agent (LCG + 30% noise)",
        description="An agent that follows (7x+2) mod 11 only 70% of the time; the remaining 30% returns a random integer in [0, 10].",
        complexity="hard",
        expected="no_recovery (consistency too low) — but compliance check against the claimed (7x+2) mod 11 should report ~70% agreement",
        fn=_noisy_lcg,
        input_universe=range(1, 250),
        claimed_spec={"family": "linear_residual", "params": {"a": 7, "c": 2, "m": 11}, "source": "vendor system prompt — pre-noise"},
    ),
    Agent(
        id="agent_09_drift_v1",
        label="Drift v1 (baseline)",
        description="The baseline agent before a vendor update — (7x+2) mod 11.",
        complexity="easy",
        expected="recover (7·x + 2) mod 11 — baseline for diff against agent_10",
        fn=_drift_agent_v1,
        input_universe=range(1, 200),
    ),
    Agent(
        id="agent_10_drift_v2",
        label="Drift v2 (post-vendor-update)",
        description="The same agent after a silent vendor update — now (11x+5) mod 13.",
        complexity="easy",
        expected="recover (11·x + 5) mod 13. Diff against agent_09 should detect parameter drift and high behavioral divergence.",
        fn=_drift_agent_v2,
        input_universe=range(500, 700),  # disjoint inputs to simulate "new month, new tickets"
    ),
    # Bonus 11th: meta-escalation, expected to fail honestly
    Agent(
        id="agent_11_meta_escalation",
        label="Meta-escalation (multi-criteria)",
        description="An agent whose decision combines parity, magnitude, and last-digit checks. Out of catalog.",
        complexity="out-of-catalog",
        expected="no_recovery — multi-criteria branching is not in the engine's catalog",
        fn=_meta_escalation,
        input_universe=range(1, 500),
    ),
]


# ──────────────────────────────────────────────────────────────────
# Trace generators
# ──────────────────────────────────────────────────────────────────


def make_trace_record(idx: int, x: int, y: int, agent_id: str, model: str = "synthetic") -> dict:
    """OpenAI-Chat-Completions wire-format JSONL record."""
    return {
        "id": f"chatcmpl-{agent_id}-{idx:04d}",
        "model": model,
        "created": 1748000000 + idx * 30,
        "messages": [
            {
                "role": "system",
                "content": f"Synthetic test agent {agent_id}. Given an integer input, return the decision as an integer.",
            },
            {"role": "user", "content": f"input={x}"},
            {"role": "assistant", "content": str(y)},
        ],
        "_meta": {
            "x": x,
            "y": y,
            "agent_id": agent_id,
            "feature_path": "messages[1].content",
            "decision_path": "messages[2].content",
        },
    }


def generate_trace(agent: Agent, out_path: Path, seed: int = 42) -> None:
    rng = random.Random(seed)
    inputs = rng.sample(list(agent.input_universe), agent.n_traces)
    with out_path.open("w") as f:
        for i, x in enumerate(inputs):
            try:
                y = agent.fn(x)
            except Exception as e:
                print(f"  [{agent.id}] error on x={x}: {e} — skipping")
                continue
            f.write(json.dumps(make_trace_record(i, x, y, agent.id)) + "\n")


def generate_all(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for agent in AGENTS:
        p = out_dir / f"{agent.id}.jsonl"
        generate_trace(agent, p)
        paths[agent.id] = p
        print(f"  wrote {agent.n_traces} traces -> {p.name}")
    return paths


if __name__ == "__main__":
    here = Path(__file__).parent
    out = here / "traces"
    print(f"Generating {len(AGENTS)} agent traces -> {out}/")
    generate_all(out)
    print(f"\nDone. {len(AGENTS)} agents ready for evaluation.")
