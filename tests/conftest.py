"""Shared fixtures for kbound tests.

Each family fixture returns a `FamilyFixture` carrying the K observations,
the ground-truth predict function, and the expected `family` id that
`recover_rule` should detect.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

collect_ignore_glob = ["_legacy/*"]


@dataclass(frozen=True)
class FamilyFixture:
    name: str
    examples: list[tuple]
    predict_fn: Callable[[Any], int]
    expected_family: str
    supports_predict: bool = True


# ─── deterministic RNG for any test that needs randomness ─────────


@pytest.fixture(scope="session")
def seeded_rng() -> random.Random:
    return random.Random(42)


# ─── single-input modular families ─────────────────────────────────


@pytest.fixture
def lcg_observations() -> FamilyFixture:
    a, c, m = 3, 7, 17
    examples = [(i, (a * i + c) % m) for i in range(8)]
    return FamilyFixture(
        name="lcg",
        examples=examples,
        predict_fn=lambda x: (a * int(x) + c) % m,
        expected_family="lcg",
    )


@pytest.fixture
def polynomial_observations() -> FamilyFixture:
    a, b, c, p = 5, 7, 3, 19
    examples = [(i, (a * i * i + b * i + c) % p) for i in range(1, 6)]
    return FamilyFixture(
        name="polycoef",
        examples=examples,
        predict_fn=lambda x: (a * int(x) ** 2 + b * int(x) + c) % p,
        expected_family="polycoef",
    )


@pytest.fixture
def cubic_observations() -> FamilyFixture:
    a, b, c, d, p = 2, 3, 5, 7, 23
    examples = [(i, (a * i**3 + b * i**2 + c * i + d) % p) for i in range(1, 7)]
    return FamilyFixture(
        name="cubic",
        examples=examples,
        predict_fn=lambda x: (a * int(x) ** 3 + b * int(x) ** 2 + c * int(x) + d) % p,
        expected_family="cubic",
    )


@pytest.fixture
def modmul_observations() -> FamilyFixture:
    a, p = 5, 17
    examples = [(i, (a * i) % p) for i in range(1, 9)]
    return FamilyFixture(
        name="modmul",
        examples=examples,
        predict_fn=lambda x: (a * int(x)) % p,
        expected_family="modmul",
    )


@pytest.fixture
def modinv_observations() -> FamilyFixture:
    p = 11
    examples = [(i, pow(i, -1, p)) for i in range(1, p)]
    return FamilyFixture(
        name="modinv",
        examples=examples,
        predict_fn=lambda x: pow(int(x), -1, p),
        expected_family="modinv",
    )


@pytest.fixture
def modexp_observations() -> FamilyFixture:
    a, p = 3, 17
    examples = [(i, pow(a, i, p)) for i in range(8)]
    return FamilyFixture(
        name="modexp",
        examples=examples,
        predict_fn=lambda x: pow(a, int(x), p),
        expected_family="modexp",
    )


@pytest.fixture
def fib_observations() -> FamilyFixture:
    """Fibonacci-like recurrence mod 11. predict() not supported by _apply yet."""
    m = 11
    fib = [0, 1]
    while len(fib) < 16:
        fib.append((fib[-1] + fib[-2]) % m)
    examples = [(i, fib[i]) for i in range(8)]
    return FamilyFixture(
        name="recurrence_fib",
        examples=examples,
        predict_fn=lambda x: fib[int(x)],
        expected_family="recurrence_fib",
        supports_predict=False,
    )


# ─── 2-input / k-bit families ──────────────────────────────────────


@pytest.fixture
def mod_p_add_observations() -> FamilyFixture:
    p = 7
    pairs = [(1, 3), (2, 5), (4, 1), (6, 0), (3, 6), (5, 2), (0, 4), (1, 1)]
    examples = [((a, b), (a + b) % p) for a, b in pairs]
    return FamilyFixture(
        name="mod_p_add",
        examples=examples,
        predict_fn=lambda xy: (int(xy[0]) + int(xy[1])) % p,
        expected_family="mod_p_add",
    )


@pytest.fixture
def boolean_observations() -> FamilyFixture:
    """XOR truth table replicated to K=8."""
    cases = [((0, 0), 0), ((0, 1), 1), ((1, 0), 1), ((1, 1), 0)]
    examples = cases * 2
    return FamilyFixture(
        name="boolean_2input",
        examples=examples,
        predict_fn=lambda xy: int(xy[0]) ^ int(xy[1]),
        expected_family="boolean_2input",
        supports_predict=False,
    )


@pytest.fixture
def parity_observations() -> FamilyFixture:
    """4-bit parity (XOR of all bits) — full 16-row truth table."""
    examples = [(tuple((i >> j) & 1 for j in range(4)), bin(i).count("1") % 2) for i in range(16)]
    return FamilyFixture(
        name="parity_kbit",
        examples=examples,
        predict_fn=lambda b: sum(int(x) for x in b) % 2,
        expected_family="parity_kbit",
        supports_predict=False,
    )


# ─── pathological observations (no-recovery / errors) ──────────────


@pytest.fixture
def random_noise_observations(seeded_rng) -> list[tuple]:
    """Random noise — no operator family should fit cleanly."""
    return [(i, seeded_rng.randint(100, 999_999)) for i in range(8)]


@pytest.fixture
def conflicting_observations() -> list[tuple]:
    """Same x mapped to different y — no deterministic rule exists."""
    return [(1, 5), (2, 7), (3, 9), (1, 12), (4, 11), (5, 13), (6, 15), (7, 17)]


@pytest.fixture
def insufficient_k_observations() -> list[tuple]:
    """K=2 — below the 4-observation floor of recover_rule."""
    return [(1, 2), (2, 4)]


# ─── all-family fixture name list, used by test_families.py ────────


ALL_FAMILY_FIXTURE_NAMES = [
    "lcg_observations",
    "polynomial_observations",
    "cubic_observations",
    "modmul_observations",
    "modinv_observations",
    "modexp_observations",
    "fib_observations",
    "mod_p_add_observations",
    "boolean_observations",
    "parity_observations",
]
