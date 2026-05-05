"""Tests for the MCP server tools (kbound/mcp.py).

The official `mcp` SDK keeps `@mcp.tool()`-decorated functions directly
callable, so the unit tests here exercise the tool functions in-process
without spinning up a stdio transport. Integration testing through the
real MCP protocol is left for a future test_mcp_e2e suite.
"""

from __future__ import annotations

import asyncio

import pytest

mcp_module = pytest.importorskip("kbound.mcp", reason="requires `pip install kbound[mcp]`")


# ─── tool registration ─────────────────────────────────────────────


def test_all_five_tools_registered() -> None:
    """The FastMCP server should advertise exactly the 5 tools we ship."""
    tools = asyncio.run(mcp_module.mcp.list_tools())
    names = {t.name for t in tools}
    expected = {
        "recover_rule_from_observations",
        "predict_under_recovered_rule",
        "list_supported_rule_families",
        "verify_compliance_against_claimed_rule",
        "classify_observation_geometry",
    }
    assert names == expected, f"registered tools mismatch: {names ^ expected}"


def test_tools_have_descriptions() -> None:
    """Every tool must have a non-empty description (LLMs use it to pick which tool to call)."""
    tools = asyncio.run(mcp_module.mcp.list_tools())
    for t in tools:
        assert t.description, f"tool {t.name!r} has no description"
        assert len(t.description) > 100, (
            f"tool {t.name!r} description is too short — agents need real guidance"
        )


# ─── recover_rule_from_observations ────────────────────────────────


def test_recover_lcg_via_mcp(lcg_observations) -> None:
    obs = [[x, y] for x, y in lcg_observations.examples]
    r = mcp_module.recover_rule_from_observations(obs)
    assert r["family"] == "lcg"
    assert r["verified"] is True
    assert r["parameters"] == {"a": 3, "c": 7, "m": 17}
    assert r["k_used"] == len(obs)
    assert r["margin"] >= 1


def test_recover_polycoef_via_mcp(polynomial_observations) -> None:
    obs = [[x, y] for x, y in polynomial_observations.examples]
    r = mcp_module.recover_rule_from_observations(obs)
    assert r["family"] == "polycoef"
    assert r["verified"] is True


def test_recover_arity2_mod_p_add_via_mcp(mod_p_add_observations) -> None:
    """JSON nested-list inputs (mod_p_add, boolean, parity) must round-trip through tuples."""
    obs = [[list(x), y] for x, y in mod_p_add_observations.examples]
    r = mcp_module.recover_rule_from_observations(obs)
    assert r["family"] == "mod_p_add"
    assert r["verified"] is True


def test_recover_no_recovery_returns_null_family(random_noise_observations) -> None:
    obs = [[x, y] for x, y in random_noise_observations]
    r = mcp_module.recover_rule_from_observations(obs)
    # noise may or may not crash — assert it does not raise and returns a structured result
    assert "family" in r
    assert "verified" in r


def test_recover_validates_input_shape() -> None:
    with pytest.raises(ValueError, match="input, output"):
        mcp_module.recover_rule_from_observations([[1, 2, 3], [4, 5]])


# ─── predict_under_recovered_rule ──────────────────────────────────


def test_predict_lcg_via_mcp(lcg_observations) -> None:
    obs = [[x, y] for x, y in lcg_observations.examples]
    r = mcp_module.predict_under_recovered_rule(obs, 42)
    assert r["prediction"] == lcg_observations.predict_fn(42)
    assert r["verified"] is True


def test_predict_arity2_with_list_query(mod_p_add_observations) -> None:
    obs = [[list(x), y] for x, y in mod_p_add_observations.examples]
    r = mcp_module.predict_under_recovered_rule(obs, [5, 5])
    assert r["prediction"] == mod_p_add_observations.predict_fn((5, 5))


def test_predict_no_recovery_returns_null_with_reason(random_noise_observations) -> None:
    obs = [[x, y] for x, y in random_noise_observations]
    r = mcp_module.predict_under_recovered_rule(obs, 100)
    if not r["verified"]:
        assert r["prediction"] is None
        assert "reason" in r


# ─── list_supported_rule_families ──────────────────────────────────


def test_list_families_returns_full_catalog() -> None:
    families = mcp_module.list_supported_rule_families()
    assert isinstance(families, list)
    assert len(families) >= 16
    keys = {"family", "name", "description", "k_lower_bound", "validation_status"}
    for entry in families:
        assert keys.issubset(entry.keys()), f"missing keys: {keys - entry.keys()}"
        assert entry["validation_status"] in {"validated", "experimental"}


def test_list_families_contains_lcg_polycoef() -> None:
    families = mcp_module.list_supported_rule_families()
    family_ids = {f["family"] for f in families}
    assert "linear_residual_policy" in family_ids
    assert "polynomial_threshold_rule" in family_ids


# ─── verify_compliance_against_claimed_rule ────────────────────────


def test_verify_compliance_perfect(lcg_observations) -> None:
    obs = [[x, y] for x, y in lcg_observations.examples]
    r = mcp_module.verify_compliance_against_claimed_rule(
        obs, "linear_residual", {"a": 3, "c": 7, "m": 17}
    )
    assert r["agreement_pct"] == 1.0
    assert r["n_violations"] == 0
    assert r["counterexamples"] == []
    assert r["is_compliant_at_95pct"] is True


def test_verify_compliance_with_violations() -> None:
    a, c, m = 3, 7, 17
    obs = [[i, (a * i + c) % m] for i in range(8)]
    obs[2][1] = (obs[2][1] + 1) % m  # inject one mismatch
    r = mcp_module.verify_compliance_against_claimed_rule(
        obs, "linear_residual", {"a": a, "c": c, "m": m}
    )
    assert r["agreement_pct"] == pytest.approx(7 / 8)
    assert r["n_violations"] == 1
    assert len(r["counterexamples"]) == 1


def test_verify_compliance_unknown_family_returns_zero_with_note() -> None:
    obs = [[1, 2], [2, 4], [3, 6], [4, 8]]
    r = mcp_module.verify_compliance_against_claimed_rule(
        obs, "definitely_not_real", {"a": 1, "c": 0, "m": 7}
    )
    assert r["agreement_pct"] == 0.0
    assert any("unknown family" in n for n in r["notes"])


# ─── classify_observation_geometry ─────────────────────────────────


def test_classify_lcg_is_algebraic(lcg_observations) -> None:
    obs = [[x, y] for x, y in lcg_observations.examples]
    g = mcp_module.classify_observation_geometry(obs)
    assert g["geometry"] in ("algebraic", "borderline")
    assert g["detected_family"] == "lcg"


def test_classify_threshold_is_spatial() -> None:
    obs = [[i, 1 if i >= 5 else 0] for i in range(11)]
    g = mcp_module.classify_observation_geometry(obs)
    assert g["geometry"] == "spatial"


def test_classify_returns_features() -> None:
    obs = [[i, (3 * i + 7) % 17] for i in range(8)]
    g = mcp_module.classify_observation_geometry(obs)
    assert "features" in g
    assert "input_arity" in g["features"]
    assert g["features"]["input_arity"] == 1
