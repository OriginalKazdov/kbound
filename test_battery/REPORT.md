# Kazdov Spec — End-to-end Battery Report

**Date:** 2026-05-04
**Run by:** `test_battery/run_battery.py`
**Engine version:** v0.3.0 (compliance + diff primitives)

## What we tested

11 synthetic agents with varying complexity, plus a drift-pair diff.
Each agent emits 40 trace observations in JSONL. The engine's recovery
pipeline + compliance-check primitive + diff primitive run against
each.

## Results — top line

| Outcome | Count | Notes |
|---|---|---|
| **RECOVERED** (consistency ≥ 0.95) | 5 / 11 | Engine returned a closed-form spec |
| **NO_RECOVERY** (honest) | 6 / 11 | Engine refused to fit a rule |
| **DIFF working** | 1 / 1 | 96.2% divergence detected on agent_09 vs agent_10 |

Total wall-clock: ~67 seconds for the full battery (11 recoveries + 1 diff).

## Per-agent outcome

| # | Agent | Complexity | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| 1 | `agent_01_lcg_easy` | easy | RECOVERED | RECOVERED `(7·x + 2) mod 11`, 87ms, consistency 1.0 | ✅ as expected |
| 2 | `agent_02_polynomial` | medium | RECOVERED polynomial | RECOVERED `coeffs [1, 5, 3] mod 13`, 7.7s, consistency 1.0 | ✅ as expected |
| 3 | `agent_03_recurrence` | medium | RECOVERED recurrence | NO_RECOVERY, 11.6s | ⚠️ honest (see note) |
| 4 | `agent_04_modexp` | medium | RECOVERED exp | RECOVERED `2^x mod 13`, 84ms, consistency 1.0 | ✅ as expected |
| 5 | `agent_05_composed_categorical` | hard | NO_RECOVERY likely | NO_RECOVERY, 8.1s | ✅ as expected |
| 6 | `agent_06_multi_feature_packed` | hard | NO_RECOVERY (1D limitation) | NO_RECOVERY, 7.1s | ✅ as expected — confirms 1D handicap |
| 7 | `agent_07_pure_threshold` | hard | NO_RECOVERY (out of catalog) | NO_RECOVERY, 1.5s | ✅ as expected |
| 8 | `agent_08_noisy_lcg` | hard | NO_RECOVERY + compliance ~70% | NO_RECOVERY, 12.2s + **compliance 72.5%** | ✅✅ critical — validates the compliance-verification angle |
| 9 | `agent_09_drift_v1` | easy | RECOVERED | RECOVERED `(7·x + 2) mod 11`, 89ms | ✅ as expected |
| 10 | `agent_10_drift_v2` | easy | RECOVERED + diff | RECOVERED `(11·x + 5) mod 13`, 6ms | ✅ as expected |
| 11 | `agent_11_meta_escalation` | out-of-catalog | NO_RECOVERY | NO_RECOVERY, 13.5s | ✅ as expected |
|   | **DIFF 09 vs 10** | drift | divergence detected | **96.2% divergence**, fingerprint `6faa792bc4d141ef` | ✅ as expected |

## The interesting cases — what we learned

### agent_08 (noisy LCG) — the keystone validation

**This is the most important result of the battery.** The agent
follows `(7·x + 2) mod 11` only 70% of the time; the remaining 30% is
random noise.

- **Recovery output:** `no_recovery` — engine correctly refuses to fit
  a rule that doesn't have ≥95% consistency.
- **Compliance output:** when given the *claimed* `(7·x + 2) mod 11`
  spec (the noise-free version the vendor would declare), the engine
  reports **72.5% agreement (29/40)** with bucket breakdown
  (low: 76%, mid: 78%, high: 64%).

**Why this matters:** this is exactly the production scenario the
product is designed for. A vendor declares a clean policy. The agent
honors it most of the time but drifts under load / specific input
ranges / model updates. Kazdov Spec says:

> "I cannot recover a closed-form rule because the agent is not
> deterministic, BUT against your declared spec the agreement is 72.5%
> with these specific counterexamples and this input-range gradient."

That output is fileable evidence. It's the artifact that drives a
remediation SLA (which we ship via `render_remediation_sla()`). It
validates the entire commercial wedge of the product.

### agent_03 (linear recurrence) — false alarm, real lesson

Expected RECOVERED, got NO_RECOVERY. Investigation: the trace
generator used **random sampling** from `range(2, 80)`. Linear
recurrence solvers (Hankel-determinant attack) require **consecutive
indices** `i, i+1, i+2, …` to detect the recurrence relation. With
non-consecutive samples, the solver correctly cannot reconstruct the
recurrence.

**Conclusion:** engine behavior was correct — `no_recovery` was the
honest output for the data it was given. **Lesson for product
documentation:** customer-facing docs should explicitly note that
recurrence-class agents need traces captured at consecutive call
indices, not random samples.

### agent_06 (multi-feature packed) — confirms the 1D handicap

Packed `(score, tier)` into a single int via bit-shifting. Engine
returned `no_recovery`. This confirms the product's central technical
limitation: **the engine catalog assumes scalar input → scalar output
under modular / polynomial / recurrence structure, not vector-input
rules.** The fix is on the roadmap (multi-feature input, ~2-3
sessions of work) but is intentionally NOT yet shipped.

### Drift detection — clean win

`agent_09` recovered to `(7·x + 2) mod 11`; `agent_10` recovered to
`(11·x + 5) mod 13`. The diff primitive correctly:

- Recovered both specs side-by-side.
- Computed parameter deltas (`a: 7→11`, `c: 2→5`, `m: 11→13`).
- Reported behavioral divergence: 77/80 = 96.2% of unique inputs in
  the union predict differently between v1 and v2.
- Emitted a stable fingerprint (`6faa792bc4d141ef`).

This is the "git-blame for agent behavior" wedge demonstrated end to
end — and the most defensibly novel commercial primitive in the
product.

## What this battery tells us

### Validated

1. **Closed-form recovery works as claimed** on the catalog: linear
   residual, polynomial threshold, exponential pattern.
2. **`no_recovery` is honest, not a bug** — the engine refuses to fit
   noisy / out-of-catalog / structurally-mismatched data instead of
   inventing a fit.
3. **Compliance verification is the keystone primitive** — even when
   recovery fails (agent_08), the compliance-vs-claim check produces
   the audit-grade artifact.
4. **Drift detection works** end-to-end with reproducible fingerprint.

### Honest limitations confirmed

1. **1D scalar inputs only** — multi-feature agents (agent_06) and
   pure threshold rules (agent_07) are out of catalog.
2. **Recurrence solvers require consecutive-index traces.** Document
   this in the product docs.
3. **Compositional rules** (agent_05: LCG + categorical bucket) and
   **multi-criteria branching** (agent_11) are out of catalog.

### Action items

- **Engineering:** add a documentation note about consecutive indices
  for recurrence-class agents.
- **Product:** the multi-feature input extension (~2-3 sessions)
  remains on the roadmap. Validated by this battery as the #1
  capability gap.
- **Marketing:** the agent_08 result (no_recovery + 72.5% compliance)
  is the canonical demo of the compliance-verification wedge. Use
  it in cold outreach + workshop submission + 1-pager.

## Reproducibility

Battery is fully self-contained:

```bash
cd test_battery
PYTHONPATH=../.. ../.venv/bin/python agents.py        # generates 11 traces
PYTHONPATH=../.. ../.venv/bin/python run_battery.py   # runs the battery
```

JSON report: `test_battery/battery_report.json`.
