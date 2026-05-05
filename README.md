# kbound

> **Inductive rule recovery toolkit.**
> Give it K observations, get back the rule plus a sample-complexity certificate.

```bash
pip install kbound
```

```python
from kbound import recover_rule

# Five observations from a deterministic system
observations = [(1, 15), (2, 18), (3, 12), (4, 16), (5, 11)]

r = recover_rule(observations)

r.rule          # 'decision(x) = (5·x² + 7·x + 3) mod 19'
r.confidence    # 1.0
r.verified      # True
r.predict(42)   # 16  (extrapolates over the recovered rule)
r.certificate   # {'k_used': 5, 'k_lower_bound': 4, 'margin': 1.25, ...}
```

That is the whole API for the common case. No prompt tuning, no training, no LLM call.

---

## What it does

Given `K ≥ 4` input/output pairs from any deterministic system — an AI agent, a smart contract, a legacy decision rule, a math problem — kbound:

1. **Classifies** the geometric structure of the rule (spatial-separable vs. algebraically-coupled).
2. **Detects** which family it belongs to from a 16-operator catalog (linear residual, polynomial threshold, modular exponentiation, Boolean gate, k-bit parity, linear recurrence, …).
3. **Recovers** the parameters via the matching solver — Boyar's attack for LCGs, Vandermonde solve over `F_p` for polynomials, GF(2) elimination for additive-feedback generators, and so on.
4. **Verifies** the recovered rule reproduces every observation, then **emits a certificate** with `K_used`, the family-specific `K_lower_bound`, and the safety margin.

If nothing in the catalog matches, it returns `RecoveryResult(no_recovery, …)` — honest failure, no hallucination.

---

## How it compares

|  | What it does | When kbound wins |
|---|---|---|
| **SymPy** | Manipulates a formula you give it (solve, simplify, integrate). | When you do **not** have the formula yet — only observations. |
| **DreamCoder / general program synthesis** | Open-ended program search via library learning. | When the rule fits a known algebraic family — kbound is `O(K)` to seconds, DreamCoder is minutes to hours. |
| **Z3 / SMT** | Constraint satisfaction over a manually-encoded theory. | When you want push-button recovery without writing the encoding. (kbound uses Z3 internally for the bitwise non-linear class.) |
| **LLM K-shot induction** | Few-shot prompt: "given these examples, what's `f(x)`?" | When the rule is **algebraically coupled**: frontier LLMs hit ~0.02 accuracy on `lcg_mod50` at K=16 in-context (Dovzak 2026). kbound hits 1.00. |

---

## Use cases

- **Build deterministic copilots for AI agents**: drop kbound in as an MCP server; agents now answer K-shot induction questions correctly instead of hallucinating. (See `kbound/mcp.py`, status: in progress.)
- **Audit deployed AI agents**: recover the rule the agent is actually following from a trace log; compare against the vendor-declared specification (`kbound.check_compliance`); emit auditor-ready Markdown + CSV + remediation SLA.
- **Cryptanalysis & security research**: recover LCG / glibc / Java / MT19937 / TGFSR-additive-feedback / 2-LCG-XOR-composition state from observed outputs, with a sample-complexity bound on the recovery.
- **Behavioral diff between system versions**: `kbound.diff_traces(v1, v2)` surfaces silent rule changes between deployments.
- **Reverse-engineer legacy decision systems**: feed (input, output) pairs from production logs, get back the executable rule.

---

## Operator catalog (16 families, today)

```
Linear Residual Policy             y = (a·x + c) mod m            small modulus
Linear Residual (Large-Modulus)    y = (a·x + c) mod m            unknown m, Boyar 1989
Linear Residual w/ Truncation      java.util.Random — top-32 bits of m=2⁴⁸ state
Polynomial Threshold Rule          y = (a·x² + b·x + c) mod p     small modulus
Polynomial Threshold (Large-Mod)   y = polynomial mod arbitrary m, deg 2-3
Cubic Threshold Rule               y = (a·x³ + b·x² + c·x + d) mod p
Scaling Residual Rule              y = (a·x) mod p
Inverse Residual Rule              y = x⁻¹ mod p
Exponential Pattern Rule           y = a^x mod p
Additive Composition Rule          y = (x₁ + x₂) mod p
Linear Recurrence Policy           y_n = (a·y_{n-1} + b·y_{n-2}) mod m
Linear Recurrence (Large-Modulus)  order-2 / order-3, arbitrary m
Binary Decision Gate               2-input boolean truth table
k-Bit Parity Rule                  XOR over a subset of bits
Stateful Pattern (Large State)     MT19937 — recovered from K ≥ 624 outputs
Stateful Pattern (Additive Fbk)    glibc TYPE_3 — recovered from K ≥ 100 outputs
```

Each operator has a typical `K_lower_bound`. The certificate every recovery emits cites it.

---

## Compliance primitive

When the rule is **declared** by a vendor and you want to audit how often the agent honors it:

```python
from kbound import check_compliance, ClaimedSpec

claimed = ClaimedSpec(
    family="linear_residual",
    params={"a": 3, "c": 5, "m": 11},
    source="vendor system prompt v7.0",
)

report = check_compliance(observations, claimed)

report.agreement_pct       # 0.73 — the agent honors the spec 73% of the time
report.counterexamples     # first 10 deviations: input, observed, expected
report.is_compliant()      # False at default 95% threshold
```

Render to Markdown, legal-grade CSV, remediation SLA, or AI Bill-of-Materials section:

```python
from kbound import (
    render_compliance_report_md,
    render_legal_counterexample_csv,
    render_remediation_sla,
    render_ai_bom_section,
)
```

The compliance check is the primitive that converts "no rule recovered" into a positive audit finding when you have a declared spec to test against.

---

## Foundations

kbound is grounded in four papers (Dovzak):

1. **The Compositional Depth Decay is a Dispatch Tax** — exponential-decay law fingerprinting architectures' compositional generalization.
2. **The Geometric Boundary of Few-Shot Rule Induction in Frontier LLMs** — measures where commercial LLMs cross from 0.88 accuracy to chance, depending on rule geometry.
3. **Geometry of Few-Shot Rule Induction** — the spatial-separable vs. algebraically-coupled distinction; defines the Relational Consistency Executor (RCE) that kbound implements for the algebraic side.
4. **A Universal Sample-Complexity Framework for Black-Box Rule Recovery** — the master inequality `K ≥ (dim − log|Sym(r)|)/b` that yields the K-bound certificate every recovery cites.

You do not need to read them to use kbound. They are the answer to "is this principled?" rather than "how do I use it?"

---

## Status

`v0.1.0`. The 16 operators are stable and tested. The MCP server adapter and full documentation site are in progress. Public API surface (`recover_rule`, `check_compliance`, `classify_geometry`, the renderers) is stable.

Roadmap (short):
- `kbound/mcp.py` — MCP server packaging, registered in the public catalog.
- `kbound diff` CLI — behavioral diff between trace versions.
- Documentation site at `originalkazdov.github.io/kbound`.
- Continuous benchmark of frontier LLMs vs. kbound across the operator catalog.

---

## Contributing

Issues and PRs welcome. New operators are first-class: see `kbound/solvers/` for the solver template plus the operator metadata pattern in `kbound/operators.py`.

## License

MIT.
