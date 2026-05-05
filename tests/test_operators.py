"""Catalog invariants for the operator metadata."""

from __future__ import annotations

import pytest

from kbound import OPERATORS, list_operators, operator_for
from kbound.operators import OperatorMeta


def test_operators_count_at_least_16() -> None:
    """Operator catalog must keep its claimed coverage. README cites 16."""
    assert len(OPERATORS) >= 16


def test_each_operator_has_required_fields() -> None:
    for key, meta in OPERATORS.items():
        assert isinstance(meta, OperatorMeta)
        assert meta.internal_id, f"{key}: missing internal_id"
        assert meta.business_name, f"{key}: missing business_name"
        assert meta.family_label, f"{key}: missing family_label"
        assert meta.description, f"{key}: missing description"
        assert meta.typical_k_lower_bound >= 4, f"{key}: K_lower < 4"
        assert meta.validation_status in {"validated", "experimental"}


def test_family_label_matches_dict_key() -> None:
    """The dict key and family_label must be identical — they're used interchangeably."""
    for key, meta in OPERATORS.items():
        assert key == meta.family_label, f"key={key!r} but family_label={meta.family_label!r}"


def test_internal_ids_are_unique() -> None:
    seen: set[str] = set()
    for meta in OPERATORS.values():
        assert meta.internal_id not in seen, f"duplicate internal_id: {meta.internal_id}"
        seen.add(meta.internal_id)


@pytest.mark.parametrize("key", list(OPERATORS.keys()))
def test_operator_for_round_trip(key: str) -> None:
    meta = OPERATORS[key]
    assert operator_for(meta.internal_id) is meta


def test_operator_for_unknown_returns_none() -> None:
    assert operator_for("definitely_not_a_real_family") is None


def test_list_operators_shape() -> None:
    items = list_operators()
    assert isinstance(items, list)
    assert len(items) == len(OPERATORS)
    required_keys = {
        "key",
        "name",
        "family_label",
        "description",
        "typical_k_lower_bound",
        "validation_status",
    }
    for item in items:
        assert required_keys.issubset(item.keys()), f"missing keys: {required_keys - item.keys()}"
