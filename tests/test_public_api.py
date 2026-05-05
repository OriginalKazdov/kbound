"""Surface-level tests: imports, version, __all__ shape, OPERATORS catalog."""

from __future__ import annotations

import kbound


def test_version_is_string() -> None:
    assert isinstance(kbound.__version__, str)
    assert len(kbound.__version__) > 0


def test_version_matches_pyproject() -> None:
    """If we forget to bump pyproject when bumping __init__, CI catches it."""
    from pathlib import Path

    import tomllib

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    assert data["project"]["version"] == kbound.__version__


def test_all_exports_resolve() -> None:
    """Every name in __all__ must actually be importable from kbound."""
    for name in kbound.__all__:
        assert hasattr(kbound, name), f"__all__ promises {name!r} but kbound has no such attr"


def test_core_recover_api_present() -> None:
    assert callable(kbound.recover_rule)
    assert hasattr(kbound, "RecoveryResult")
    assert callable(kbound.classify_geometry)
    assert callable(kbound.identify_family)


def test_compliance_api_present() -> None:
    assert callable(kbound.check_compliance)
    assert hasattr(kbound, "ClaimedSpec")
    assert hasattr(kbound, "ComplianceReport")
    assert callable(kbound.render_compliance_report_md)
    assert callable(kbound.render_legal_counterexample_csv)
    assert callable(kbound.render_remediation_sla)
    assert callable(kbound.render_ai_bom_section)


def test_diff_api_present() -> None:
    assert callable(kbound.diff_traces)
    assert callable(kbound.render_diff_report_md)
    assert hasattr(kbound, "SpecDiff")


def test_operators_api_present() -> None:
    assert isinstance(kbound.OPERATORS, dict)
    assert callable(kbound.operator_for)
    assert callable(kbound.list_operators)
