"""Parametrized recovery + predict tests across every supported family.

Each fixture supplies (examples, expected_family, predict_fn). For families
where `_apply` does not yet wire the predict path (recurrence, boolean_2input,
parity_kbit), we test recovery only.
"""

from __future__ import annotations

import pytest

from kbound import recover_rule

from .conftest import ALL_FAMILY_FIXTURE_NAMES, FamilyFixture


@pytest.mark.parametrize("fixture_name", ALL_FAMILY_FIXTURE_NAMES)
def test_recovery_succeeds(fixture_name: str, request: pytest.FixtureRequest) -> None:
    fix: FamilyFixture = request.getfixturevalue(fixture_name)
    r = recover_rule(fix.examples)
    assert r.family == fix.expected_family, (
        f"{fixture_name}: expected family={fix.expected_family!r}, got {r.family!r}"
    )
    assert r.verified, f"{fixture_name}: recovery not verified"
    assert r.confidence >= 0.95, f"{fixture_name}: confidence={r.confidence:.3f} below 0.95"


@pytest.mark.parametrize("fixture_name", ALL_FAMILY_FIXTURE_NAMES)
def test_certificate_margin(fixture_name: str, request: pytest.FixtureRequest) -> None:
    fix: FamilyFixture = request.getfixturevalue(fixture_name)
    r = recover_rule(fix.examples)
    assert r.k_used == len(fix.examples)
    assert r.k_lower_bound is not None
    assert r.k_used >= r.k_lower_bound, (
        f"{fixture_name}: K_used={r.k_used} < K_lower={r.k_lower_bound}"
    )


PREDICTABLE_FIXTURES = [
    "lcg_observations",
    "polynomial_observations",
    "cubic_observations",
    "modmul_observations",
    "modinv_observations",
    "modexp_observations",
    "mod_p_add_observations",
]


@pytest.mark.parametrize("fixture_name", PREDICTABLE_FIXTURES)
def test_predict_held_out(fixture_name: str, request: pytest.FixtureRequest) -> None:
    """Held-out predict for families whose `_apply` implementation is wired."""
    fix: FamilyFixture = request.getfixturevalue(fixture_name)
    r = recover_rule(fix.examples)

    if fix.expected_family == "modinv":
        held_out = (max(int(e[0]) for e in fix.examples) % 9) + 1
    elif fix.expected_family == "mod_p_add":
        held_out = (4, 5)
    else:
        held_out = max(int(e[0]) for e in fix.examples) + 7

    expected = fix.predict_fn(held_out)
    actual = r.predict(held_out)
    assert actual == expected, (
        f"{fixture_name}: predict({held_out}) returned {actual}, expected {expected}"
    )


def test_lcg_recovers_function_form_not_boyar(lcg_observations: FamilyFixture) -> None:
    """Regression test for the family_id reorder fix: small-mod LCG must run
    BEFORE Boyar so users get the function-form (a, c, m) and not Boyar's
    state-machine (a=1, c=step) recovery."""
    r = recover_rule(lcg_observations.examples)
    assert r.family == "lcg", (
        f"expected family='lcg' (function form), got {r.family!r} (likely Boyar)"
    )
    assert r.parameters["a"] == 3
    assert r.parameters["c"] == 7
    assert r.parameters["m"] == 17


def test_large_modulus_lcg_falls_back_to_boyar() -> None:
    """When the modulus is too large for small-mod search, Boyar takes over.
    This verifies the fallback path the reorder did NOT break."""
    a, c, m = 1103515245, 12345, 2**31
    examples = [(i, (a * i + c) % m) for i in range(8)]
    r = recover_rule(examples)
    assert r.family == "lcg_generic", f"large m should land in Boyar fallback, got {r.family!r}"
    assert r.verified
