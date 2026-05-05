"""POC: behavioral spec recovery on a deployed-style "claims routing agent".

Realistic scenario: a fintech runs an AI agent that takes claim_id (numeric)
and routes the claim to a department (0-10). The agent is a black-box from
the auditor's perspective — they only see (input, output) pairs from API logs.

Under the hood, the agent uses a deterministic LCG-style hash for routing
(common pattern in real production: deterministic backend wrapped in LLM
facade for natural-language interaction).

This PoC:
  1. Simulates the agent (LCG-backed, with realistic API surface).
  2. Captures K=16 (input, output) traces — the data an auditor would have.
  3. Submits the traces to kbound via the public API.
  4. Receives the recovered spec.md + spec.yaml + audit certificate.
  5. Validates the recovered rule against held-out future traces.

This is the deliverable you'd show a VP Trust & Safety at Sierra/Decagon/
Harvey to land a $15-30K forensic-engagement contract.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path


# ============================================================
# 1) The "deployed agent" (simulated, but realistic)
# ============================================================

class ClaimsRoutingAgent:
    """A production-style claims routing service.

    Wraps a deterministic LCG decision rule under a facade that *could* be
    an LLM agent in real life. From the auditor's perspective, this is a
    black box — they only see what comes in and what comes out.

    Real-world equivalents:
      - Customer support tier router (Sierra-style)
      - Fraud risk tier assignment (Decagon, Hebbia)
      - Shard / bucket assignment (any backend)
    """

    # Hidden production rule — the auditor doesn't know this exists.
    _A = 3
    _C = 4
    _M = 11

    def __init__(self):
        self._call_count = 0

    def route(self, claim_id: int) -> dict:
        """Public API: takes a claim_id, returns routing decision."""
        self._call_count += 1
        # The "deterministic backend" the LLM facade calls into.
        department = (self._A * claim_id + self._C) % self._M
        return {
            "claim_id": claim_id,
            "department": department,
            "trace_id": f"req-{self._call_count:04d}",
            "timestamp": int(time.time()),
            # In a real agent, there'd be reasoning/explanation here too.
            # We omit that — Kazdov only needs the I/O pairs.
        }


# ============================================================
# 2) The "auditor's view" — capture K=16 traces from the agent
# ============================================================

def capture_audit_traces(agent: ClaimsRoutingAgent, n_traces: int = 16) -> list[dict]:
    """Replay realistic claim_ids through the agent (what the auditor pulls
    from production logs / replays from a sandboxed copy of the agent).

    Realistic claim_ids: 4-6 digit numbers, randomly sampled.
    """
    import random
    rng = random.Random(42)  # auditor's sample seed (reproducible audit)
    claim_ids = rng.sample(range(1000, 999999), n_traces)
    traces = []
    for cid in claim_ids:
        result = agent.route(cid)
        traces.append({
            "id": result["trace_id"],
            "model": "claims-routing-agent-v3.2",
            "messages": [
                {"role": "system", "content": "You are a claims routing assistant. Return the department index (0-10) for the given claim_id."},
                {"role": "user", "content": f"claim_id={cid}"},
                {"role": "assistant", "content": str(result["department"])},
            ],
            "_meta": {
                "x": cid,
                "y": result["department"],
                "feature_path": "messages[1].content",
                "decision_path": "messages[2].content",
            },
        })
    return traces


# ============================================================
# 3) Submit traces to kbound (real API call)
# ============================================================

def kazdov_recover(traces: list[dict], query_claim_id: int) -> dict:
    """POST traces to /spec/recover/openai-logs as a multipart upload."""
    boundary = "----poc-claims-routing"
    jsonl_body = "\n".join(json.dumps(t) for t in traces)
    body_bytes = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="audit_traces.jsonl"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + jsonl_body.encode() + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="query"\r\n\r\n{query_claim_id}'
        f"\r\n--{boundary}--\r\n"
    ).encode()
    req = urllib.request.Request(
        "http://localhost:8765/spec/recover/openai-logs",
        data=body_bytes,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ============================================================
# 4) Validation — re-run the recovered spec on held-out traces
# ============================================================

def validate_against_holdout(agent: ClaimsRoutingAgent, recovered: dict, n_holdout: int = 20) -> dict:
    """Re-run the recovered spec on NEW (input, output) pairs and check accuracy.

    This is what an auditor would do to verify the recovered spec matches
    actual agent behavior on inputs the recovery didn't see.
    """
    import random
    rng = random.Random(99)  # different seed for holdout
    held_inputs = rng.sample(range(1000, 999999), n_holdout)

    op = recovered["operator"]
    params = recovered["parameters"]

    # The recovered rule, applied symbolically
    a = params.get("a"); c = params.get("c"); m = params.get("m")
    if a is None or c is None or m is None:
        return {"verified": False, "reason": "no recovered parameters"}

    matches = 0
    mismatches = []
    for cid in held_inputs:
        agent_output = agent.route(cid)["department"]
        recovered_pred = (a * cid + c) % m
        if recovered_pred == agent_output:
            matches += 1
        else:
            mismatches.append((cid, agent_output, recovered_pred))

    return {
        "verified": matches == len(held_inputs),
        "n_holdout": n_holdout,
        "n_matches": matches,
        "accuracy_pct": 100.0 * matches / len(held_inputs),
        "mismatches": mismatches[:5],
        "recovered_rule": f"department(claim_id) = ({a}*claim_id + {c}) mod {m}",
    }


# ============================================================
# 5) End-to-end PoC
# ============================================================

def main():
    print("=" * 72)
    print("  PoC — behavioral spec recovery on a deployed AI agent")
    print("  Target: 'claims routing agent' (black-box from auditor's view)")
    print("=" * 72)
    print()

    # Step 1: a deployed agent runs in production. We don't know its internals.
    print("[1/5] Deployed agent is live in production at fintech-corp...")
    agent = ClaimsRoutingAgent()
    print("      ✓ Agent deployed (claims-routing-agent-v3.2)")
    print()

    # Step 2: auditor pulls 16 (input, output) traces from production logs
    print("[2/5] Auditor pulls K=16 (input, output) traces from production logs...")
    traces = capture_audit_traces(agent, n_traces=16)
    print(f"      ✓ Captured {len(traces)} traces")
    print(f"      First 3 (input → output):")
    for t in traces[:3]:
        x, y = t["_meta"]["x"], t["_meta"]["y"]
        print(f"        claim_id={x:>8d}  →  department={y}")
    print()

    # Step 3: submit to kbound
    print("[3/5] Submitting traces to kbound for recovery...")
    holdout_query = 12345
    t0 = time.time()
    result = kazdov_recover(traces, query_claim_id=holdout_query)
    elapsed = time.time() - t0
    print(f"      ✓ Recovery completed in {elapsed:.2f}s")
    print()

    # Step 4: show the deliverables (spec.md + spec.yaml + certificate)
    print("[4/5] Deliverables received from kbound:")
    print()
    print("    --- spec.md (auditor-readable) ---")
    print()
    print(result["spec_md"])
    print()
    print("    --- spec.yaml (machine-checkable) ---")
    print()
    print(result["spec_yaml"])
    print()
    print("    --- certificate (audit metadata) ---")
    print(f"      Operator:        {result['operator']['business_name']}")
    print(f"      K used:          {result['certificate']['k_used']}")
    print(f"      K lower bound:   {result['certificate']['k_lower_bound']}")
    print(f"      Margin:          {result['certificate']['margin']}× over lower bound")
    print(f"      Proof status:    {result['certificate']['proof_status']}")
    print(f"      Consistency:     {result['certificate']['consistency_score']:.0%}")
    print(f"      Validation tier: {result['operator'].get('validation_status', 'validated')}")
    print()
    print(f"      Held-out query (claim_id={holdout_query}):")
    print(f"        Predicted department: {result['query']['predicted_output']}")
    print()

    # Step 5: validate the recovered spec on 20 held-out (input, output) pairs
    print("[5/5] Validating recovered spec against 20 held-out production traces...")
    val = validate_against_holdout(agent, result, n_holdout=20)
    print(f"      Recovered rule: {val['recovered_rule']}")
    print(f"      Accuracy on 20 held-out: {val['n_matches']}/{val['n_holdout']} = {val['accuracy_pct']:.0f}%")
    if val["verified"]:
        print(f"      ✓ Spec MATCHES agent behavior on all held-out traces")
    else:
        print(f"      ✗ Mismatches: {val['mismatches'][:3]}")
    print()

    # Summary
    print("=" * 72)
    if val["verified"]:
        print("  ✅ POC SUCCESS — recovered spec exactly reproduces agent behavior")
        print("  on traces it never saw. This is the deliverable a Sierra/Decagon/")
        print("  Harvey VP Trust & Safety would receive in a $15-30K audit engagement.")
    else:
        print("  ⚠️ POC INCOMPLETE — recovery succeeded on observed but failed on holdout")
        print("  → factorization ambiguity, would need more K observations")
    print("=" * 72)


if __name__ == "__main__":
    main()
