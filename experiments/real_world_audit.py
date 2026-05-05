"""
Real-world PRNG audit experiment — Kazdov Compiler vs published vulnerabilities.

Each scenario reproduces a known-class vulnerability from smart-contract audit
literature, generates K observable (input, output) pairs (the data an auditor
could pull from testnet), and feeds them to Kazdov via /internal/explain/text.

Outputs a compact table: did Kazdov recover the rule? what params? how fast?
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass


API = "http://localhost:8765/internal/explain/text"


@dataclass
class Scenario:
    id: str
    title: str
    source: str            # historical/documented reference
    rule_description: str  # "what the contract is doing"
    family_expected: str   # which Kazdov family should fire
    examples: list         # list of (x, y) pairs
    query_x: object
    query_y_expected: object
    true_params: dict


# ============================================================
# SCENARIO 1 — Etherroll-style dice (predictable LCG mod n)
# ============================================================
# Pattern: contract uses prev_block_hash + nonce → some int → % MAX_FACE
# Real-world examples: Etherroll, multiple NFT mints, lottery tickets.
# Reduced form: f(seed) = (a*seed + c) mod m
def scen_etherroll():
    a, c, m = 7, 3, 13   # small modulus = how many lottery slots / NFT rarities / dice faces
    seeds = [110, 47, 251, 88, 304, 19, 522, 73]
    pairs = [(s, (a*s + c) % m) for s in seeds]
    qx = 1000
    return Scenario(
        id="etherroll_lcg",
        title="Etherroll-style dice — predictable LCG mod 13",
        source="Etherroll, 2017 (post-mortem published)",
        rule_description="dice_face = (a·seed + c) mod m where seed = prev_blockhash low bits",
        family_expected="lcg",
        examples=pairs,
        query_x=qx,
        query_y_expected=(a*qx + c) % m,
        true_params={"a": a, "c": c, "m": m},
    )


# ============================================================
# SCENARIO 2 — NFT rarity assignment (vulnerable mint)
# ============================================================
# Pattern: rarity[token_id] = (a*token_id + c) mod 10  (10 rarity tiers)
# Real-world: multiple unverified mints in 2021-2022, Meebits-style reroll
def scen_nft_rarity():
    a, c, m = 23, 11, 13
    token_ids = [101, 102, 103, 104, 105, 106, 107, 108]
    pairs = [(t, (a*t + c) % m) for t in token_ids]
    qx = 200
    return Scenario(
        id="nft_rarity_lcg",
        title="NFT mint rarity — predictable LCG",
        source="Meebits-class reroll bug (2021), pattern repeated in many drops",
        rule_description="rarity[token_id] = (a·token_id + c) mod m",
        family_expected="lcg",
        examples=pairs,
        query_x=qx,
        query_y_expected=(a*qx + c) % m,
        true_params={"a": a, "c": c, "m": m},
    )


# ============================================================
# SCENARIO 3 — Polynomial-based "obfuscation" (Shamir-style leak)
# ============================================================
# Pattern: shares of a secret polynomial mod p. Recovering coefficients = leak.
# Real-world: poorly-implemented secret-sharing in custom MPC contracts.
def scen_polycoef():
    a, b, c, p = 4, 7, 5, 17
    xs = [0, 1, 2, 3, 5, 7, 10, 13]
    pairs = [(x, (a*x*x + b*x + c) % p) for x in xs]
    qx = 4
    return Scenario(
        id="shamir_poly_leak",
        title="Polynomial coefficient leak (Shamir-class)",
        source="generic pattern in custom MPC / commit-reveal schemes",
        rule_description="f(x) = (a·x² + b·x + c) mod p — recovering (a,b,c) leaks the secret polynomial",
        family_expected="polycoef",
        examples=pairs,
        query_x=qx,
        query_y_expected=(a*qx*qx + b*qx + c) % p,
        true_params={"a": a, "b": b, "c": c, "p": p},
    )


# ============================================================
# SCENARIO 4 — RSA primitive observation (modular exponentiation)
# ============================================================
# Pattern: side-channel observation of a^x mod p with small p.
# Real-world: timing/leak attacks against weak custom RSA precompiles.
def scen_rsa_modexp():
    a, p = 5, 13
    xs = [2, 3, 4, 5, 6, 7, 9, 11]
    pairs = [(x, pow(a, x, p)) for x in xs]
    qx = 12
    return Scenario(
        id="rsa_primitive",
        title="RSA primitive — modular exponentiation with weak modulus",
        source="generic RSA-precompile audit pattern",
        rule_description="output = a^x mod p — recovering (a, p) means the trapdoor is broken",
        family_expected="modexp",
        examples=pairs,
        query_x=qx,
        query_y_expected=pow(a, qx, p),
        true_params={"a": a, "p": p},
    )


# ============================================================
# SCENARIO 5 — DB shard routing (NOT a vulnerability, just a use case)
# ============================================================
# Pattern: production hash routing for sharding by user_id.
# Use case: Kazdov can recover the routing rule from observed user→shard pairs,
# useful for migration audits or detecting hidden coupling.
def scen_shard_routing():
    a, c, m = 5, 7, 11
    user_ids = [1001, 2034, 7782, 4521, 8893, 1115, 3308, 6650]
    pairs = [(uid, (a*uid + c) % m) for uid in user_ids]
    qx = 9999
    return Scenario(
        id="shard_routing",
        title="DB shard routing — recoverable from observed assignments",
        source="production pattern (not a bug; useful for migration audit)",
        rule_description="shard[user_id] = (a·user_id + c) mod m",
        family_expected="lcg",
        examples=pairs,
        query_x=qx,
        query_y_expected=(a*qx + c) % m,
        true_params={"a": a, "c": c, "m": m},
    )


# ============================================================
# SCENARIO 6 — Predictable lottery winner index (Roast-Football-class)
# ============================================================
# Pattern: winner_index = (block.number * a + c) mod num_participants
# Real-world: Roast Football Protocol exploit, $110K loss, Dec 2022.
def scen_roast_football():
    a, c, m = 11, 4, 7
    blocks = [12500, 12501, 12502, 12503, 12504, 12505, 12506, 12507]
    pairs = [(b, (a*b + c) % m) for b in blocks]
    qx = 12600
    return Scenario(
        id="roast_football",
        title="Lottery winner — Roast Football class ($110K loss)",
        source="Roast Football Protocol exploit, 2022-12 (~$110K)",
        rule_description="winner_idx = (block.number·a + c) mod num_players",
        family_expected="lcg",
        examples=pairs,
        query_x=qx,
        query_y_expected=(a*qx + c) % m,
        true_params={"a": a, "c": c, "m": m},
    )


# ============================================================
# SCENARIO 7 — Linear recurrence (stream cipher state)
# ============================================================
# Pattern: state_n = (a·state_{n-1} + b·state_{n-2}) mod m
# Real-world: weak stream cipher / LFSR-based PRNG audit
def scen_recurrence():
    m = 11
    a_, b_ = 3, 2
    state = [3, 5]
    for _ in range(20):
        state.append((a_ * state[-1] + b_ * state[-2]) % m)
    pairs = [(n, state[n]) for n in range(8)]
    qx = 12
    return Scenario(
        id="lfsr_recurrence",
        title="Linear recurrence — LFSR / weak stream cipher",
        source="LFSR audit pattern (academic; e.g. weak custom session token PRNGs)",
        rule_description="state_n = (a·state_{n-1} + b·state_{n-2}) mod m",
        family_expected="recurrence_fib",
        examples=pairs,
        query_x=qx,
        query_y_expected=state[qx],
        true_params={"a": a_, "b": b_, "m": m},
    )


SCENARIOS = [
    scen_etherroll(),
    scen_nft_rarity(),
    scen_polycoef(),
    scen_rsa_modexp(),
    scen_shard_routing(),
    scen_roast_football(),
    scen_recurrence(),
]


# ============================================================
# RUNNER
# ============================================================

def fmt_x(x):
    if isinstance(x, tuple):
        return "(" + ",".join(str(v) for v in x) + ")"
    return str(x)


def to_text(examples, query_x):
    lines = [f"{fmt_x(x)} → {y}" for x, y in examples]
    lines.append(f"{fmt_x(query_x)} → ?")
    return "\n".join(lines)


def post_explain(text):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(
        API, data=body, headers={"content-type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def run():
    rows = []
    print(f"Running {len(SCENARIOS)} real-world-flavored scenarios against Kazdov...\n")
    for s in SCENARIOS:
        text = to_text(s.examples, s.query_x)
        t0 = time.perf_counter()
        try:
            data = post_explain(text)
            elapsed = (time.perf_counter() - t0) * 1000
            ans = data.get("answer")
            ver = data.get("verified")
            family = data.get("final", {}).get("family")
            geom = data.get("final", {}).get("geometry")
            solver = data.get("final", {}).get("solver_used", "")
            # Find recovered params from solver invocation stage details
            recovered = {}
            for stage in data.get("stages", []):
                if stage["step"] == 3:
                    fd = (stage.get("details") or {}).get("full_details") or {}
                    for k in ("a", "b", "c", "m", "p", "k"):
                        if k in fd:
                            recovered[k] = fd[k]
            ok_answer = ans == s.query_y_expected
            ok_family = family == s.family_expected
            params_match = all(recovered.get(k) == v for k, v in s.true_params.items() if k in recovered)
            row = {
                "id": s.id,
                "title": s.title,
                "n": len(s.examples),
                "expected_family": s.family_expected,
                "got_family": family or "—",
                "expected_answer": s.query_y_expected,
                "got_answer": ans,
                "answer_correct": ok_answer,
                "family_correct": ok_family,
                "verified": ver,
                "geometry": geom,
                "true_params": s.true_params,
                "recovered_params": recovered,
                "params_match": params_match,
                "solver": solver,
                "elapsed_ms": round(elapsed, 1),
                "source": s.source,
            }
            rows.append(row)
            check_a = "✓" if ok_answer else "✗"
            check_f = "✓" if ok_family else "✗"
            check_p = "✓" if params_match else "✗"
            print(f"  [{check_a} answer · {check_f} family · {check_p} params] {s.id:<22} → {family or '?':<18} {elapsed:.0f}ms")
        except Exception as e:
            print(f"  [✗ ERROR] {s.id}: {e}")
            rows.append({"id": s.id, "title": s.title, "error": str(e)})

    # Summary
    correct = sum(1 for r in rows if r.get("answer_correct"))
    print(f"\nSummary: {correct}/{len(SCENARIOS)} answers correct, "
          f"{sum(1 for r in rows if r.get('verified'))}/{len(SCENARIOS)} verified")

    return rows


if __name__ == "__main__":
    rows = run()
    out_path = "/Users/kazdov/code/OriginalKazdov/kbound/experiments/results.json"
    with open(out_path, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    print(f"\nFull results: {out_path}")
