# PoC — Behavioral Spec Recovery on a Deployed Claims-Routing Agent

**Audience**: VP Trust & Safety / Head of AI Risk at AI-native mid-market companies
(Sierra, Decagon, Harvey, Glean, Hebbia, Cresta tier).

**Pitch**: "Show me 16 (input, output) pairs from any deterministic backend
your AI agent calls into, and I'll recover the exact decision rule it's
following — as a Markdown spec your auditor can attach to a SR 11-7 / NIST AI
RMF / EU AI Act submission. 60-second turnaround. Audit-grade."

## What this PoC demonstrates

Real end-to-end recovery on a simulated-but-realistic deployed AI agent. The
agent (a "claims routing service") wraps a deterministic LCG-style hash for
routing decisions. From the auditor's perspective it is a black box — they
only have access to (input, output) pairs from production logs.

Steps:
1. The agent runs in production. We don't know its internals.
2. The auditor pulls K=16 traces from production logs.
3. The traces are submitted to Kazdov Spec via `POST /spec/recover/openai-logs`.
4. Kazdov returns `spec.md` + `spec.yaml` + audit certificate in <60s.
5. The recovered spec is validated against 20 held-out traces the recovery
   never saw — should reproduce agent behavior exactly.

## Result (last run, 2026-05-03)

```
Recovery time:       0.06s
Operator family:     Linear Residual Policy
Recovered rule:      decision(claim_id) = (3·claim_id + 4) mod 11
Parameters:          a=3, c=4, m=11
Consistency score:   100% (16/16 observed traces)
Held-out accuracy:   100% (20/20 traces the recovery never saw)
Audit certificate:   K=16 used, K=4 lower bound, 4.0× margin, validated tier
```

The recovered rule **exactly matches** the agent's hidden production logic,
and predicts behavior on 20 unseen traces with 100% accuracy.

## Real-world fit

This PoC simulates the kind of deterministic backend that real agents call:
- Customer support tier routers (Sierra, Decagon, Cresta — agent-as-facade)
- Fraud risk tier assignment (Hebbia, financial AI agents)
- Shard / bucket / pool assignment (any backend that hashes user_id → group)
- A/B test bucketing exposed via agent
- Content moderation tier (Trust & Safety internal tools)

Real agents in this category typically wrap deterministic Python services in
LLM facades (for natural-language interaction). Kazdov recovers what's
deterministic underneath, regardless of the LLM wrapper's stochastic noise.

## What Kazdov does NOT recover

Honest scope:
- **Pure stochastic LLM decisions** (no deterministic backend) — Kazdov returns
  `verified=False, geometry=spatial, confidence=0.5, warnings=[...]`. Honest
  fallback, no false positives.
- **Cryptographically-strong RNG** (ChaCha20, AES-CTR, /dev/urandom-derived)
  — by design uncrackable. Kazdov returns "no algebraic family identified."
- **Non-modular decision rules** (real-valued thresholds, lookup tables,
  neural classifiers) — different scope, requires different tooling.

If your agent's decision logic is one of these, Kazdov will tell you so
honestly and decline to fabricate a spec.

## How to use this PoC for outreach

1. Replace the synthetic `ClaimsRoutingAgent` in `run_poc.py` with the
   prospect's actual API endpoint (or a sandboxed copy of their agent).
2. Capture K=16 traces from their public demos / sandbox / sample API calls.
3. Run the PoC end-to-end.
4. If it succeeds: send the resulting `spec.md` + `spec.yaml` to the prospect's
   VP Trust & Safety as a "we recovered the policy your agent is following"
   demonstration.
5. If it returns honest fallback: send the fallback report — the prospect
   learns that their agent's decisions are NOT deterministic-backend-driven.
   Either way, you've delivered information they didn't have before.

Pricing the engagement:
- Free preliminary recovery (this PoC).
- $15-30K full forensic engagement: deeper recovery, drift detection over
  time, regulatory crosswalk (NIST AI RMF / EU AI Act / SR 11-7), signed
  certificate, executive summary.
- $50K+ ACV ongoing subscription via compiler.kazdov.com.

## Files in this PoC

- `run_poc.py` — end-to-end script. Run with `python3 run_poc.py` (assumes
  Kazdov Spec running at http://localhost:8765).
- `traces_sample.jsonl` (generated on first run) — the 16 captured traces
  in OpenAI Chat Completions format.
- `spec.md` (generated) — the auditor-readable Markdown spec.
- `spec.yaml` (generated) — the machine-checkable YAML spec.

## Running

```bash
# Start Kazdov Spec API
cd /Users/kazdov/code/OriginalKazdov/induction_compiler
PYTHONPATH=. .venv/bin/uvicorn induction_compiler.kazdov_spec.api.spec_app:app --port 8765 &

# Run the PoC
PYTHONPATH=. .venv/bin/python3 docs/poc_claims_routing/run_poc.py
```

Expected output: PoC SUCCESS with 100% accuracy on held-out traces.
