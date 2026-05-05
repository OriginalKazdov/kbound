"""Tests for `check_compliance`, `ClaimedSpec`, `ComplianceReport`, renderers."""

from __future__ import annotations

import pytest

from kbound import (
    ClaimedSpec,
    ComplianceReport,
    Counterexample,
    check_compliance,
    render_ai_bom_section,
    render_compliance_report_md,
    render_legal_counterexample_csv,
    render_remediation_sla,
)


def test_claimed_spec_is_frozen() -> None:
    spec = ClaimedSpec(family="linear_residual", params={"a": 1, "c": 2, "m": 7})
    with pytest.raises((TypeError, AttributeError)):
        spec.family = "polynomial_threshold"  # type: ignore[misc]


def test_claimed_spec_default_source() -> None:
    spec = ClaimedSpec(family="linear_residual", params={})
    assert spec.source == "vendor-declared"


# ─── perfect compliance ────────────────────────────────────────────


def test_perfect_compliance(lcg_observations) -> None:
    spec = ClaimedSpec(family="linear_residual_policy", params={"a": 3, "c": 7, "m": 17})
    report = check_compliance(lcg_observations.examples, spec)
    assert report.agreement_pct == 1.0
    assert report.n_violations == 0
    assert report.counterexamples == []
    assert report.is_compliant() is True


def test_perfect_compliance_polynomial_via_engine_keys(polynomial_observations) -> None:
    """The `{a, b, c, p}` shape that recover_rule returns for polycoef must
    flow into the polynomial predictor without translation."""
    spec = ClaimedSpec(family="polycoef", params={"a": 5, "b": 7, "c": 3, "p": 19})
    report = check_compliance(polynomial_observations.examples, spec)
    assert report.agreement_pct == 1.0


def test_perfect_compliance_polynomial_via_coeffs() -> None:
    """The `{coeffs, m}` shape (compliance vocab) must also work."""
    examples = [(i, (5 * i**2 + 7 * i + 3) % 19) for i in range(1, 6)]
    spec = ClaimedSpec(family="polynomial_threshold", params={"coeffs": [3, 7, 5], "m": 19})
    report = check_compliance(examples, spec)
    assert report.agreement_pct == 1.0


# ─── violations ────────────────────────────────────────────────────


def test_partial_compliance_surfaces_counterexamples() -> None:
    """Inject a 25% deviation; report should show 75% agreement and
    list the counterexamples."""
    a, c, m = 3, 7, 17
    examples = [(i, (a * i + c) % m) for i in range(8)]
    examples[2] = (examples[2][0], (examples[2][1] + 1) % m)
    examples[5] = (examples[5][0], (examples[5][1] + 1) % m)

    spec = ClaimedSpec(family="linear_residual", params={"a": a, "c": c, "m": m})
    report = check_compliance(examples, spec)
    assert report.agreement_pct == pytest.approx(0.75)
    assert report.n_violations == 2
    assert len(report.counterexamples) == 2
    for ce in report.counterexamples:
        assert isinstance(ce, Counterexample)


def test_input_buckets_populated(lcg_observations) -> None:
    spec = ClaimedSpec(family="linear_residual_policy", params={"a": 3, "c": 7, "m": 17})
    report = check_compliance(lcg_observations.examples, spec)
    for bucket, pct in report.by_input_bucket.items():
        assert bucket in {"low", "mid", "high"}
        assert 0.0 <= pct <= 1.0


# ─── unknown-family handling ───────────────────────────────────────


def test_unknown_family_returns_zero_with_note() -> None:
    spec = ClaimedSpec(family="definitely_not_real", params={"a": 1, "c": 2, "m": 7})
    report = check_compliance([(1, 2), (2, 4), (3, 6), (4, 8)], spec)
    assert report.agreement_pct == 0.0
    assert any("unknown family" in note for note in report.notes)


# ─── renderers smoke ───────────────────────────────────────────────


def test_render_compliance_report_md_smoke(lcg_observations) -> None:
    spec = ClaimedSpec(family="linear_residual_policy", params={"a": 3, "c": 7, "m": 17})
    report = check_compliance(lcg_observations.examples, spec)
    md = render_compliance_report_md(report)
    assert isinstance(md, str)
    assert "Compliance Report" in md
    assert "linear_residual_policy" in md


def test_render_legal_csv_smoke() -> None:
    examples = [(i, (3 * i + 7) % 17) for i in range(8)]
    examples[2] = (examples[2][0], 99)
    spec = ClaimedSpec(family="linear_residual", params={"a": 3, "c": 7, "m": 17})
    report = check_compliance(examples, spec)
    csv = render_legal_counterexample_csv(report)
    assert isinstance(csv, str)
    assert "fingerprint" in csv
    assert "vendor_predicted_output" in csv


def test_render_remediation_sla_smoke(lcg_observations) -> None:
    examples = list(lcg_observations.examples)
    examples[1] = (examples[1][0], 99)
    spec = ClaimedSpec(family="linear_residual", params={"a": 3, "c": 7, "m": 17})
    report = check_compliance(examples, spec)
    sla = render_remediation_sla(report, vendor_name="AcmeAI")
    assert isinstance(sla, str)
    assert "AcmeAI" in sla
    assert "Remediation" in sla


def test_render_ai_bom_smoke(lcg_observations) -> None:
    spec = ClaimedSpec(family="linear_residual_policy", params={"a": 3, "c": 7, "m": 17})
    report = check_compliance(lcg_observations.examples, spec)
    bom = render_ai_bom_section(report, vendor_name="AcmeAI", system_name="LoanFastTrack")
    assert isinstance(bom, str)
    assert "AcmeAI" in bom
    assert "LoanFastTrack" in bom


# ─── return type ────────────────────────────────────────────────────


def test_returns_compliance_report_type(lcg_observations) -> None:
    spec = ClaimedSpec(family="linear_residual", params={"a": 3, "c": 7, "m": 17})
    report = check_compliance(lcg_observations.examples, spec)
    assert isinstance(report, ComplianceReport)
