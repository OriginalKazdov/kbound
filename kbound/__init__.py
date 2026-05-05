"""kbound — inductive rule recovery toolkit.

Give it K input/output observations of any deterministic system. Get back the
rule, the parameters, and a sample-complexity certificate.

Foundation: four papers (Dovzak) on the geometric structure of rule
induction and a master inequality for sample complexity. The library is
usable without reading any of them — the public API is `recover_rule()`.

Quickstart:

    >>> from kbound import recover_rule
    >>> observations = [(1, 15), (2, 18), (3, 12), (4, 16), (5, 11)]
    >>> result = recover_rule(observations)
    >>> result.rule
    'decision(x) = (5·x² + 7·x + 3) mod 19'
    >>> result.predict(42)
    16
"""

__version__ = "0.1.0"

from kbound.recover import recover_rule, RecoveryResult
from kbound.classifier.oracle_classifier import classify_geometry
from kbound.classifier.family_id import identify_family
from kbound.compliance import (
    check_compliance,
    ClaimedSpec,
    ComplianceReport,
    Counterexample,
    render_compliance_report_md,
    render_legal_counterexample_csv,
    render_remediation_sla,
    render_ai_bom_section,
)
from kbound.diff import (
    diff_traces,
    render_diff_report_md,
    SpecDiff,
    SideRecovery,
    BehavioralDivergence,
    ParamDelta,
)
from kbound.operators import OPERATORS, operator_for, list_operators

__all__ = [
    "__version__",
    # Recovery
    "recover_rule",
    "RecoveryResult",
    "classify_geometry",
    "identify_family",
    # Compliance
    "check_compliance",
    "ClaimedSpec",
    "ComplianceReport",
    "Counterexample",
    "render_compliance_report_md",
    "render_legal_counterexample_csv",
    "render_remediation_sla",
    "render_ai_bom_section",
    # Behavioral diff
    "diff_traces",
    "render_diff_report_md",
    "SpecDiff",
    "SideRecovery",
    "BehavioralDivergence",
    "ParamDelta",
    # Operator catalog
    "OPERATORS",
    "operator_for",
    "list_operators",
]
