"""Tests for `classify_geometry` and `identify_family`."""

from __future__ import annotations

from kbound import classify_geometry, identify_family


def test_classify_geometry_returns_required_keys(lcg_observations) -> None:
    g = classify_geometry(lcg_observations.examples)
    assert "geometry" in g
    assert "features" in g
    assert "output_cardinality_bucket" in g
    assert "per_model_accuracy" in g
    assert "recommended_model" in g


def test_classify_lcg_is_algebraic(lcg_observations) -> None:
    g = classify_geometry(lcg_observations.examples)
    assert g["geometry"] in ("algebraic", "borderline")


def test_classify_polynomial_is_algebraic(polynomial_observations) -> None:
    g = classify_geometry(polynomial_observations.examples)
    assert g["geometry"] in ("algebraic", "borderline")


def test_classify_threshold_is_spatial() -> None:
    """A monotone 1D threshold rule should land in the spatial bucket."""
    examples = [(i, 1 if i >= 5 else 0) for i in range(0, 11)]
    g = classify_geometry(examples)
    assert g["geometry"] == "spatial"


def test_features_arity_matches_input(mod_p_add_observations) -> None:
    g = classify_geometry(mod_p_add_observations.examples)
    assert g["features"]["input_arity"] == 2


def test_features_output_cardinality(boolean_observations) -> None:
    g = classify_geometry(boolean_observations.examples)
    assert g["features"]["output_cardinality"] == 2


# ─── identify_family ───────────────────────────────────────────────


def test_identify_family_lcg(lcg_observations) -> None:
    g = classify_geometry(lcg_observations.examples)
    fam = identify_family(lcg_observations.examples, g)
    assert fam == "lcg"


def test_identify_family_polycoef(polynomial_observations) -> None:
    g = classify_geometry(polynomial_observations.examples)
    fam = identify_family(polynomial_observations.examples, g)
    assert fam == "polycoef"


def test_identify_family_modexp(modexp_observations) -> None:
    g = classify_geometry(modexp_observations.examples)
    fam = identify_family(modexp_observations.examples, g)
    assert fam == "modexp"


def test_identify_family_mod_p_add(mod_p_add_observations) -> None:
    g = classify_geometry(mod_p_add_observations.examples)
    fam = identify_family(mod_p_add_observations.examples, g)
    assert fam == "mod_p_add"


def test_identify_family_boolean_2input(boolean_observations) -> None:
    g = classify_geometry(boolean_observations.examples)
    fam = identify_family(boolean_observations.examples, g)
    assert fam == "boolean_2input"
