"""Core `recover_rule` contract: validation, no-recovery, certificate, predict."""

from __future__ import annotations

import pytest

from kbound import recover_rule
from kbound.recover import RecoveryResult

# ─── argument validation ───────────────────────────────────────────


def test_empty_examples_raises() -> None:
    with pytest.raises(ValueError, match="at least 4"):
        recover_rule([])


def test_insufficient_k_raises(insufficient_k_observations: list[tuple]) -> None:
    with pytest.raises(ValueError, match="at least 4"):
        recover_rule(insufficient_k_observations)


# ─── happy path ────────────────────────────────────────────────────


def test_recovery_returns_recoveryresult(polynomial_observations) -> None:
    r = recover_rule(polynomial_observations.examples)
    assert isinstance(r, RecoveryResult)
    assert r.family == "polycoef"
    assert r.verified is True
    assert r.confidence == pytest.approx(1.0)


def test_certificate_fields_when_recovered(lcg_observations) -> None:
    r = recover_rule(lcg_observations.examples)
    cert = r.certificate
    assert cert["k_used"] == len(lcg_observations.examples)
    assert cert["k_lower_bound"] >= 4
    assert cert["margin"] == pytest.approx(round(cert["k_used"] / cert["k_lower_bound"], 2))
    assert cert["proof_status"] == "empirical"
    assert "operator" in cert
    assert "family_label" in cert


def test_repr_recovered(lcg_observations) -> None:
    r = recover_rule(lcg_observations.examples)
    rep = repr(r)
    assert "rule=" in rep
    assert "confidence=" in rep
    assert "k_used=" in rep


# ─── no-recovery paths ─────────────────────────────────────────────


def test_random_noise_does_not_crash(random_noise_observations: list[tuple]) -> None:
    """Random noise: the engine may classify it as some family by accident, but
    must not raise. We assert structural sanity, not semantic correctness."""
    r = recover_rule(random_noise_observations)
    assert isinstance(r, RecoveryResult)
    assert isinstance(r.confidence, float)
    assert 0.0 <= r.confidence <= 1.0


def test_conflicting_observations_does_not_crash(conflicting_observations) -> None:
    """The same x maps to different y. The engine should not crash; it should
    either return no_recovery or a low-confidence result. We do not assume which."""
    r = recover_rule(conflicting_observations)
    assert isinstance(r, RecoveryResult)
    assert not r.verified, "verified=True is impossible when observations contradict each other"


def test_predict_on_no_recovery_raises() -> None:
    """If family is None, predict() must raise rather than return junk."""
    r = RecoveryResult(rule=None, family=None, operator=None)
    with pytest.raises(ValueError, match="no rule recovered"):
        r.predict(0)


def test_no_recovery_repr_is_distinct() -> None:
    r = RecoveryResult(rule=None, family=None, operator=None, k_used=4)
    rep = repr(r)
    assert "no_recovery" in rep
    assert "k_used=4" in rep


# ─── consistency between recover_rule and predict ──────────────────


def test_predict_matches_ground_truth(polynomial_observations) -> None:
    r = recover_rule(polynomial_observations.examples)
    held_out = max(int(e[0]) for e in polynomial_observations.examples) + 10
    assert r.predict(held_out) == polynomial_observations.predict_fn(held_out)


def test_predict_idempotent(polynomial_observations) -> None:
    r = recover_rule(polynomial_observations.examples)
    assert r.predict(7) == r.predict(7)


# ─── interop with check_compliance (round-trip) ────────────────────


def test_recover_to_compliance_round_trip(lcg_observations) -> None:
    """The `family` and `parameters` returned by recover_rule must be directly
    consumable by ClaimedSpec without aliasing — this regression-tests the
    Boyar-form vs function-form fix in family_id ordering."""
    from kbound import ClaimedSpec, check_compliance

    r = recover_rule(lcg_observations.examples)
    spec = ClaimedSpec(family=r.family, params=r.parameters)
    report = check_compliance(lcg_observations.examples, spec)
    assert report.agreement_pct == 1.0, (
        f"recover→compliance round-trip should be 100%, got {report.agreement_pct}"
    )
