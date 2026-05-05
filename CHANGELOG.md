# Changelog

All notable changes to `kbound` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — MCP server

### Added

- **`kbound.mcp` module + `kbound-mcp` console script**: stdio MCP server that exposes inductive rule recovery as tools any MCP-aware AI agent (Claude Desktop, Claude Code, Cursor, Cline, etc.) can call. Five tools registered:
  - `recover_rule_from_observations` — give K observations, get rule + certificate
  - `predict_under_recovered_rule` — recover and predict held-out input in one shot
  - `list_supported_rule_families` — catalog of operator families with K_lower_bound
  - `verify_compliance_against_claimed_rule` — vendor-claim verification primitive
  - `classify_observation_geometry` — cheap pre-check (spatial / algebraic / borderline)
- New optional extra `kbound[mcp]` (depends on `mcp>=1.0.0`).
- 18 pytest tests covering MCP tool registration, descriptions, and end-to-end behavior across arity-1, arity-2, and no-recovery paths.
- README section with Claude Desktop / Cursor configuration snippets.

### Why this matters

Frontier LLMs hit ~0.02 accuracy on K-shot algebraic induction at K=16 in-context (Dovzak 2026). Wrapping kbound as an MCP tool gives those agents a deterministic side-channel: instead of hallucinating a rule from K observations, the agent calls `recover_rule_from_observations` and gets back the closed-form rule plus a sample-complexity certificate.

## [0.1.0] — initial release

### Added

- `kbound.recover_rule(observations)` — top-level convenience: takes K observation pairs, returns a `RecoveryResult` with the recovered rule, parameters, family, certificate, and `predict()` for held-out inputs.
- `kbound.RecoveryResult` dataclass + `predict(x)` for arity-1, arity-2, and k-bit families.
- `kbound.classify_geometry(observations)` — spatial / algebraic / borderline classification with feature trace.
- `kbound.identify_family(observations, geom)` — algebraic subfamily detector.
- `kbound.check_compliance(observations, claimed)` + `ClaimedSpec` + `ComplianceReport` — vendor-claim verification primitive with counterexamples and per-input-bucket agreement.
- Renderers: `render_compliance_report_md`, `render_legal_counterexample_csv`, `render_remediation_sla`, `render_ai_bom_section`.
- `kbound.diff_traces(v1, v2)` + `render_diff_report_md` — behavioral diff between two trace captures.
- 16 typed operator families (`linear_residual_policy`, `polynomial_threshold_rule`, `cubic_threshold_rule`, `scaling_residual_rule`, `inverse_residual_rule`, `exponential_pattern_rule`, `additive_composition_rule`, `linear_recurrence_policy`, `linear_recurrence_large_modulus`, `binary_decision_gate`, `k_bit_parity_rule`, `linear_residual_large_modulus`, `linear_residual_with_truncation`, `stateful_pattern_large_state`, `stateful_pattern_additive_feedback`, `polynomial_threshold_large_modulus`).
- `kbound` console script: `kbound recover` and `kbound diff`.
- FastAPI service at `kbound.api.main:app` (optional, install via `pip install kbound[server]`).
- Three bundled demo traces under `kbound.data.demos`.
- 94 pytest tests + ruff lint + format pass.

### Public API stability

`kbound.__all__` lists every symbol that is part of the v0.x compat contract.
Internal modules (`kbound._pipeline`, `kbound.solvers._modular`, `kbound.api.*`)
are not stable; depend on them at your own risk.

### Known limitations

- `recover_rule` requires K ≥ 4 observations; below this it raises `ValueError`.
- Spatial-geometry rules (threshold, conjunctive) require `llm_fallback=True` + `ANTHROPIC_API_KEY` to recover; without it, `recover_rule` returns `RecoveryResult(no_recovery, …)` for those families.
- The `kbound.synth` module that emits replacement code (Python / TypeScript / Rust / Cedar) is research-experimental and not promoted in the public surface.
