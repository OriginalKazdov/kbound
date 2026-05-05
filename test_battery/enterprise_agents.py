"""15 enterprise-grade synthetic agents for end-to-end product testing.

Unlike test_battery/agents.py (which used abstract math agents), these
simulate REAL production AI agents at REAL company types. Each agent has:

- A fictional but plausible company + product name
- Industry vertical
- A "vendor system prompt" — the policy as the vendor would publish it
- Realistic input semantics (credit scores 300-850, claim amounts in
  USD, ticket priorities, etc.)
- A hidden decision function that matches OR violates the declared
  policy (the keystone case for compliance verification)
- Expected engine outcome (RECOVERED / NO_RECOVERY / PARTIAL)
- Optional drift partner (for testing kazdov diff)

The battery covers 5 outcome flavors:
  (A) clean recoverable — engine returns spec, used as positive proof
  (B) honest no-recovery — out of catalog, engine refuses (good!)
  (C) noisy no-recovery + compliance — keystone use case
  (D) drift pair — vendor silently changed the rule between versions
  (E) vendor lie — declared spec doesn't match reality
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


@dataclass(frozen=True)
class EnterpriseAgent:
    id: str
    company: str
    product_name: str
    vertical: str
    system_prompt: str
    input_semantics: str
    decision_fn: Callable[[int], int]
    input_domain: range
    n_traces: int = 40
    expected_outcome: str = "RECOVERED"  # one of: RECOVERED, NO_RECOVERY, PARTIAL
    claimed_spec: Optional[dict] = None
    drift_partner: Optional[str] = None
    flavor: str = "A"
    notes: str = ""


# ──────────────────────────────────────────────────────────────────
# Decision function builders (closures over hidden parameters)
# ──────────────────────────────────────────────────────────────────


def _make_lcg(a: int, c: int, m: int) -> Callable[[int], int]:
    return lambda x: (a * x + c) % m


def _make_poly(coeffs: list[int], m: int) -> Callable[[int], int]:
    def f(x: int) -> int:
        return sum(c * (x ** i) for i, c in enumerate(coeffs)) % m
    return f


def _make_modexp(base: int, m: int) -> Callable[[int], int]:
    return lambda x: pow(base, x, m)


def _make_noisy_lcg(a: int, c: int, m: int, noise_rate: float) -> Callable[[int], int]:
    def f(x: int) -> int:
        rng = random.Random(x * 31 + a + c + m)
        if rng.random() < noise_rate:
            return rng.randint(0, m - 1)
        return (a * x + c) % m
    return f


def _make_noisy_poly(coeffs: list[int], m: int, noise_rate: float) -> Callable[[int], int]:
    def f(x: int) -> int:
        rng = random.Random(x * 17 + sum(coeffs) + m)
        if rng.random() < noise_rate:
            return rng.randint(0, m - 1)
        return sum(c * (x ** i) for i, c in enumerate(coeffs)) % m
    return f


def _amazon_pricing(x: int) -> int:
    """Multi-feature packing: high-bits = competitor_price, low-bits = inventory_days
    Decision: surge price = ((competitor + 50) - inventory_days * 2) clamped 100-999.
    Forced into 1D for the engine — should fail (1D handicap)."""
    competitor = (x >> 8) & 0xFF  # 0-255
    inventory_days = x & 0xFF      # 0-255
    raw = (competitor + 50) - inventory_days * 2
    return max(100, min(999, raw))


def _cigna_prior_auth(x: int) -> int:
    """Multi-criteria branching: severity + plan_tier + procedure_class.
    Output: 0=auto-approve, 1=manual-review, 2=auto-deny.
    Out of catalog — should fail."""
    severity = (x >> 12) & 0xF       # 0-15
    plan_tier = (x >> 8) & 0xF       # 0=basic, 1=plus, 2=platinum
    procedure_class = x & 0xFF       # 0-255
    if plan_tier == 2 and severity >= 6:
        return 0  # auto-approve
    if severity >= 10 or procedure_class < 30:
        return 0
    if severity < 3 and procedure_class > 200:
        return 2  # auto-deny
    return 1


def _workday_threshold(x: int) -> int:
    """Pure threshold: candidate score >= 70 → ADVANCE, else REJECT.
    Out of catalog (threshold rules), should fail."""
    return 1 if x >= 70 else 0


def _meta_content_mod(x: int) -> int:
    """Vendor declares (3x+5) mod 11; reality is (3x+5) mod 11 except
    for hash buckets falling in {2, 5, 8} which return 0 (auto-allow due to
    advertiser whitelist — undisclosed exception). 27% deviation."""
    declared = (3 * x + 5) % 11
    if declared in (2, 5, 8):
        return 0
    return declared


# ──────────────────────────────────────────────────────────────────
# THE FIFTEEN AGENTS
# ──────────────────────────────────────────────────────────────────


AGENTS: list[EnterpriseAgent] = [
    # ───── Flavor A: clean recoverable ─────
    EnterpriseAgent(
        id="01_acmebank_loanfasttrack",
        company="AcmeBank",
        product_name="LoanFastTrack",
        vertical="fintech / consumer credit",
        system_prompt=(
            "You are AcmeBank's automated loan pre-qualification router. "
            "Given an applicant_id (integer), return the assigned underwriter "
            "queue (integer 0-12) using the bank's documented routing "
            "function. Output ONLY the integer."
        ),
        input_semantics="applicant_id: integer in [10000, 999999]",
        decision_fn=_make_lcg(13, 7, 17),
        input_domain=range(10000, 999999),
        expected_outcome="RECOVERED",
        flavor="A",
        notes="Clean modular router. Should recover (13·x + 7) mod 17.",
    ),
    EnterpriseAgent(
        id="02_allstate_claimstriage",
        company="Allstate",
        product_name="ClaimsTriagePro",
        vertical="insurance / auto claims",
        system_prompt=(
            "You are Allstate's first-pass auto-claim triage agent. Given a "
            "claim_id, return the assigned adjuster pool (0-16) using the "
            "polynomial-hash routing rule documented in Section 4.2 of the "
            "ClaimsTriagePro Operations Manual."
        ),
        input_semantics="claim_id: integer 100000-999999",
        decision_fn=_make_poly([3, 7, 5], 19),  # (5x² + 7x + 3) mod 19
        input_domain=range(100000, 999999),
        expected_outcome="RECOVERED",
        flavor="A",
        notes="Polynomial threshold — coeffs [3, 7, 5] mod 19.",
    ),
    EnterpriseAgent(
        id="03_stripe_fraudshield",
        company="Stripe",
        product_name="FraudShield Quadratic Tier",
        vertical="payments / fraud",
        system_prompt=(
            "Stripe FraudShield risk-scoring agent. Returns the risk bucket "
            "(0-22) for a transaction_id, computed via a documented "
            "quadratic transformation."
        ),
        input_semantics="transaction_id: integer 1-10⁶",
        decision_fn=_make_poly([1, 11, 7], 23),  # (7x² + 11x + 1) mod 23
        input_domain=range(1, 100000),
        expected_outcome="RECOVERED",
        flavor="A",
        notes="Quadratic mod 23. Stripe-style fraud scoring.",
    ),
    EnterpriseAgent(
        id="04_verizon_supportrouter",
        company="Verizon",
        product_name="SupportTicketRouter v3.4",
        vertical="telco / customer support",
        system_prompt=(
            "Verizon support routing agent. Maps ticket_id to one of 13 "
            "support pods using the hash function published in the v3 routing "
            "spec."
        ),
        input_semantics="ticket_id: integer 1-10⁹",
        decision_fn=_make_lcg(31, 17, 13),
        input_domain=range(1, 999999),
        expected_outcome="RECOVERED",
        flavor="A",
        notes="LCG-style ticket router (31·x + 17) mod 13.",
    ),
    EnterpriseAgent(
        id="05_twilio_messageprio",
        company="Twilio",
        product_name="MessageQueuePriority",
        vertical="comms / SMS infra",
        system_prompt=(
            "Twilio message priority assigner. Given a sender_account_id, "
            "return the priority bucket using the documented exponential "
            "modular function."
        ),
        input_semantics="sender_account_id: integer",
        decision_fn=_make_modexp(3, 19),  # 3^x mod 19
        input_domain=range(0, 200),
        expected_outcome="RECOVERED",
        flavor="A",
        notes="Exponential pattern: 3^x mod 19.",
    ),

    # ───── Flavor B: honest no-recovery ─────
    EnterpriseAgent(
        id="06_paypal_disputebot",
        company="PayPal",
        product_name="DisputeResolutionBot v2",
        vertical="payments / dispute",
        system_prompt=(
            "PayPal automated dispute resolver. Given a dispute_id (integer), "
            "decide: 0=auto-refund, 1=route-to-agent, 2=auto-reject. Decision "
            "policy is internal."
        ),
        input_semantics="dispute_id: integer (with composed inner hash + categorical mapping)",
        decision_fn=lambda x: (lambda h: 0 if h <= 2 else (1 if h <= 7 else 2))((11 * x + 4) % 11),
        input_domain=range(1, 250),
        expected_outcome="NO_RECOVERY",
        flavor="B",
        notes="Composed: modular hash → categorical bucket. Out of catalog.",
    ),
    EnterpriseAgent(
        id="07_cigna_priorauth",
        company="Cigna",
        product_name="PriorAuthAgent",
        vertical="healthcare / payer",
        system_prompt=(
            "Cigna prior-authorization decision agent. Multi-criteria: "
            "severity, plan_tier, and procedure_class jointly determine "
            "auto-approve / review / auto-deny."
        ),
        input_semantics="encoded triple (severity, plan_tier, procedure_class)",
        decision_fn=_cigna_prior_auth,
        input_domain=range(1, 65535),
        expected_outcome="NO_RECOVERY",
        flavor="B",
        notes="Multi-criteria branching — paradigmatic out-of-catalog case.",
    ),
    EnterpriseAgent(
        id="08_workday_candidatescreen",
        company="Workday",
        product_name="CandidateScreen ATS",
        vertical="HR / recruiting",
        system_prompt=(
            "Workday Candidate Screening agent. Given an assessment_score "
            "(integer 0-100), return 1 if candidate advances, else 0."
        ),
        input_semantics="assessment_score: integer 0-100",
        decision_fn=_workday_threshold,
        input_domain=range(0, 101),
        n_traces=40,
        expected_outcome="NO_RECOVERY",
        flavor="B",
        notes="Pure threshold rule (≥70 → 1). Out of catalog.",
    ),
    EnterpriseAgent(
        id="09_amazon_pricingbot",
        company="Amazon Retail",
        product_name="DynamicPricingBot",
        vertical="e-commerce / pricing",
        system_prompt=(
            "Amazon Dynamic Pricing agent. Computes surge price from "
            "(competitor_price, inventory_days_remaining)."
        ),
        input_semantics="packed (competitor_price, inventory_days) into single int",
        decision_fn=_amazon_pricing,
        input_domain=range(1, 65535),
        expected_outcome="NO_RECOVERY",
        flavor="B",
        notes="Multi-feature pricing rule. 1D handicap kicks in.",
    ),

    # ───── Flavor C: noisy LLM — keystone compliance use case ─────
    EnterpriseAgent(
        id="10_capitalone_creditlimit",
        company="Capital One",
        product_name="CreditLimitAgent v7",
        vertical="fintech / consumer credit",
        system_prompt=(
            "Capital One initial credit-limit assignment agent. Given a "
            "customer_id, return the limit tier (0-10) using the published "
            "linear residual rule (a=11, c=3, m=11)."
        ),
        input_semantics="customer_id: integer",
        decision_fn=_make_noisy_lcg(11, 3, 11, noise_rate=0.30),
        input_domain=range(1, 999999),
        expected_outcome="NO_RECOVERY",
        claimed_spec={"family": "linear_residual", "params": {"a": 11, "c": 3, "m": 11}, "source": "vendor system prompt v7.0"},
        flavor="C",
        notes="Vendor-declared LCG, but agent honors it only ~70% of the time. Compliance check should expose the gap.",
    ),
    EnterpriseAgent(
        id="11_jpmorgan_kycbot",
        company="JPMorgan",
        product_name="KYC Risk Scorer",
        vertical="banking / compliance",
        system_prompt=(
            "JPMorgan KYC/AML risk-tier assigner. Maps account_id to risk "
            "tier 0-12 using the bank's documented (a=7, c=4, m=13) rule."
        ),
        input_semantics="account_id: integer",
        decision_fn=_make_noisy_lcg(7, 4, 13, noise_rate=0.20),
        input_domain=range(1, 999999),
        expected_outcome="NO_RECOVERY",
        claimed_spec={"family": "linear_residual", "params": {"a": 7, "c": 4, "m": 13}, "source": "JPMorgan KYC documentation v3.2"},
        flavor="C",
        notes="80% compliant agent. Compliance should report ~80% agreement.",
    ),
    EnterpriseAgent(
        id="12_salesforce_leadscorer",
        company="Salesforce",
        product_name="Einstein LeadScore Quadratic",
        vertical="sales / CRM",
        system_prompt=(
            "Salesforce Einstein lead-scoring agent. Returns lead score "
            "0-16 for a lead_id, computed via the documented quadratic rule."
        ),
        input_semantics="lead_id: integer",
        decision_fn=_make_noisy_poly([2, 9, 5], 17, noise_rate=0.15),
        input_domain=range(1, 50000),
        expected_outcome="NO_RECOVERY",
        claimed_spec={"family": "polynomial_threshold", "params": {"coeffs": [2, 9, 5], "m": 17}, "source": "Einstein scoring rules v4.1"},
        flavor="C",
        notes="85% compliant quadratic. Compliance check should land near 85%.",
    ),

    # ───── Flavor D: drift pair (agents 13-14) ─────
    EnterpriseAgent(
        id="13_hertz_classifier_v1",
        company="Hertz",
        product_name="ClaimsClassifier (Q1 2026 baseline)",
        vertical="insurance / auto",
        system_prompt=(
            "Hertz fleet damage claims classifier. Maps damage_report_id to "
            "repair shop pool (0-16) using the Q1 2026 published routing."
        ),
        input_semantics="damage_report_id: integer",
        decision_fn=_make_lcg(13, 7, 17),
        input_domain=range(1, 200),
        expected_outcome="RECOVERED",
        drift_partner="14_hertz_classifier_v2",
        flavor="D",
        notes="Pre-update baseline. (13·x + 7) mod 17.",
    ),
    EnterpriseAgent(
        id="14_hertz_classifier_v2",
        company="Hertz",
        product_name="ClaimsClassifier (Q2 2026, post silent update)",
        vertical="insurance / auto",
        system_prompt=(
            "Hertz fleet damage claims classifier. Same documentation as "
            "v1 (vendor did NOT publish update notes)."
        ),
        input_semantics="damage_report_id: integer (different range — 'new month, new tickets')",
        decision_fn=_make_lcg(19, 11, 23),
        input_domain=range(500, 700),
        expected_outcome="RECOVERED",
        drift_partner="13_hertz_classifier_v1",
        flavor="D",
        notes="Post-update — vendor silently changed to (19·x + 11) mod 23. Diff vs v1 should detect drift.",
    ),

    # ───── Flavor E: vendor lie — declared X, does Y ─────
    EnterpriseAgent(
        id="15_meta_contentmod",
        company="Meta",
        product_name="ContentModerator-X",
        vertical="social / content moderation",
        system_prompt=(
            "Meta content moderation agent. Given content_id, returns "
            "decision 0-10 using the linear residual rule (a=3, c=5, m=11) "
            "documented in the Trust & Safety operating manual."
        ),
        input_semantics="content_id: integer",
        decision_fn=_meta_content_mod,
        input_domain=range(1, 1000),
        expected_outcome="NO_RECOVERY",
        claimed_spec={"family": "linear_residual", "params": {"a": 3, "c": 5, "m": 11}, "source": "Meta T&S operating manual"},
        flavor="E",
        notes=(
            "Vendor declares clean (3x+5) mod 11 but agent has UNDISCLOSED "
            "exception: hash buckets {2, 5, 8} return 0 (auto-allow due to "
            "advertiser whitelist). ~27% deviation. Compliance check should "
            "expose ~73% agreement + bucket-level pattern."
        ),
    ),
]


# ──────────────────────────────────────────────────────────────────
# Trace generator — same wire format as the rest of the project
# ──────────────────────────────────────────────────────────────────


def make_trace_record(idx: int, x: int, y: int, agent: EnterpriseAgent) -> dict:
    return {
        "id": f"chatcmpl-{agent.id}-{idx:04d}",
        "model": f"{agent.company.lower().replace(' ', '-')}-{agent.product_name.lower().replace(' ', '-')}",
        "created": 1748000000 + idx * 30,
        "messages": [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": f"input={x}"},
            {"role": "assistant", "content": str(y)},
        ],
        "_meta": {
            "x": x,
            "y": y,
            "agent_id": agent.id,
            "company": agent.company,
            "product": agent.product_name,
            "vertical": agent.vertical,
            "feature_path": "messages[1].content",
            "decision_path": "messages[2].content",
        },
    }


def generate_trace(agent: EnterpriseAgent, out_path: Path, seed: int = 7) -> None:
    rng = random.Random(seed + hash(agent.id) % 1000)
    inputs = rng.sample(list(agent.input_domain), agent.n_traces)
    with out_path.open("w") as f:
        for i, x in enumerate(inputs):
            try:
                y = agent.decision_fn(x)
            except Exception as e:
                print(f"  [{agent.id}] error on x={x}: {e}")
                continue
            f.write(json.dumps(make_trace_record(i, x, y, agent)) + "\n")


def generate_all(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for a in AGENTS:
        p = out_dir / f"{a.id}.jsonl"
        generate_trace(a, p)
        print(f"  [{a.flavor}] {a.company:15s} {a.product_name[:30]:30s} -> {p.name}")


if __name__ == "__main__":
    here = Path(__file__).parent
    out = here / "enterprise_traces"
    print(f"Generating {len(AGENTS)} enterprise agent traces -> {out}/")
    generate_all(out)
    print(f"\nDone. {len(AGENTS)} agents across "
          f"{len({a.vertical for a in AGENTS})} verticals.")
