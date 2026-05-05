"""OperatorRegistry — re-export of internal solvers under behavioral business names.

The mapping below is the single source of truth for crypto-internal → business
translation. Never expose internal family ids (lcg, polycoef, mt19937, etc.) in
customer-facing surfaces. Only emit operator names from this registry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OperatorMeta:
    internal_id: str
    business_name: str
    family_label: str  # short label used in YAML output
    description: str  # one-line, auditor-readable
    typical_k_lower_bound: int
    # "validated" — solver demonstrably fires on real outputs in our test battery.
    # "experimental" — solver exists but has not yet passed end-to-end field validation
    #                  on observations from a real-world source.
    validation_status: str = "validated"


# Single source of truth. CHANGE HERE if we ever rename anything.
# Server enforces K>=4 in `_run_pipeline`; entries below reflect that floor regardless
# of theoretical lower bound. validation_status set per /tmp/kz_field_*.py results
# 2026-05-02 (real PRNG battery + limit finder + LLM black-box).
OPERATORS: dict[str, OperatorMeta] = {
    "linear_residual_policy": OperatorMeta(
        internal_id="lcg",
        business_name="Linear Residual Policy",
        family_label="linear_residual_policy",
        description="Decision computed as a linear combination of inputs reduced modulo a bound (small modulus, m <= ~few hundred).",
        typical_k_lower_bound=4,
        validation_status="validated",
    ),
    "polynomial_threshold_rule": OperatorMeta(
        internal_id="polycoef",
        business_name="Polynomial Threshold Rule",
        family_label="polynomial_threshold_rule",
        description="Decision computed as a polynomial of inputs reduced modulo a bound (small modulus, fast path).",
        typical_k_lower_bound=4,
        validation_status="validated",
    ),
    "polynomial_threshold_large_modulus": OperatorMeta(
        internal_id="polycoef_generic",
        business_name="Polynomial Threshold (Large-Modulus)",
        family_label="polynomial_threshold_large_modulus",
        description="Polynomial decision rule with arbitrary large modulus (recovered via determinant-gcd reconstruction on K >= degree+2 observations). Handles unknown coefficients and modulus — including mod 100003+, mod 2^32+ — for quadratic and cubic forms.",
        typical_k_lower_bound=5,
        validation_status="validated",
    ),
    "scaling_residual_rule": OperatorMeta(
        internal_id="modmul",
        business_name="Scaling Residual Rule",
        family_label="scaling_residual_rule",
        description="Decision proportional to input, reduced modulo a small bound.",
        typical_k_lower_bound=4,
        validation_status="experimental",
    ),
    "inverse_residual_rule": OperatorMeta(
        internal_id="modinv",
        business_name="Inverse Residual Rule",
        family_label="inverse_residual_rule",
        description="Decision is the modular inverse of input under a recovered small modulus.",
        typical_k_lower_bound=4,
        validation_status="experimental",
    ),
    "exponential_pattern_rule": OperatorMeta(
        internal_id="modexp",
        business_name="Exponential Pattern Rule",
        family_label="exponential_pattern_rule",
        description="Decision computed via exponentiation modulo a recovered small base/modulus pair.",
        typical_k_lower_bound=4,
        validation_status="validated",
    ),
    "additive_composition_rule": OperatorMeta(
        internal_id="mod_p_add",
        business_name="Additive Composition Rule",
        family_label="additive_composition_rule",
        description="Decision is the sum of two inputs reduced modulo a small bound.",
        typical_k_lower_bound=4,
        validation_status="validated",
    ),
    "linear_recurrence_policy": OperatorMeta(
        internal_id="recurrence_fib",
        business_name="Linear Recurrence Policy",
        family_label="linear_recurrence_policy",
        description="Decision at step n is a linear combination of recent decisions modulo a small bound (Fibonacci-like fast path).",
        typical_k_lower_bound=4,
        validation_status="validated",
    ),
    "linear_recurrence_large_modulus": OperatorMeta(
        internal_id="recurrence_generic",
        business_name="Linear Recurrence (Large-Modulus)",
        family_label="linear_recurrence_large_modulus",
        description="Order-2 or order-3 linear recurrence with arbitrary large modulus (recovered via determinant-gcd reconstruction on sliding windows of consecutive observations). Handles unknown coefficients and modulus including mod 100003+.",
        typical_k_lower_bound=5,
        validation_status="validated",
    ),
    "binary_decision_gate": OperatorMeta(
        internal_id="boolean_2input",
        business_name="Binary Decision Gate",
        family_label="binary_decision_gate",
        description="Two-input boolean truth table — direct gate (AND/OR/XOR/etc.).",
        typical_k_lower_bound=4,
        validation_status="validated",
    ),
    "k_bit_parity_rule": OperatorMeta(
        internal_id="parity_kbit",
        business_name="k-Bit Parity Rule",
        family_label="k_bit_parity_rule",
        description="Decision is the XOR-parity over a subset of binary inputs.",
        typical_k_lower_bound=4,
        validation_status="experimental",
    ),
    "linear_residual_large_modulus": OperatorMeta(
        internal_id="lcg_generic",
        business_name="Linear Residual (Large-Modulus)",
        family_label="linear_residual_large_modulus",
        description="Linear residual rule with arbitrary large modulus (recovered via Boyar 1989 attack on K >= 6 consecutive outputs). Handles unknown a, c, m — including 2^32 and 2^64 generators — when call indices are sequential.",
        typical_k_lower_bound=6,
        validation_status="validated",
    ),
    "linear_residual_with_truncation": OperatorMeta(
        internal_id="java_random",
        business_name="Linear Residual with Truncation",
        family_label="linear_residual_with_truncation",
        description="Linear residual rule where the observed output is the high bits of a larger 48-bit state (java.util.Random canonical form).",
        typical_k_lower_bound=32,
        validation_status="validated",
    ),
    "stateful_pattern_large_state": OperatorMeta(
        internal_id="mt19937",
        business_name="Stateful Pattern (Large State)",
        family_label="stateful_pattern_large_state",
        description="Pattern with large internal state; recoverable from 624 consecutive observations (canonical large-state generator form).",
        typical_k_lower_bound=624,
        validation_status="validated",
    ),
    "stateful_pattern_additive_feedback": OperatorMeta(
        internal_id="glibc_tgfsr",
        business_name="Stateful Pattern (Additive Feedback)",
        family_label="stateful_pattern_additive_feedback",
        description="Stateful pattern with 31-word internal state and an additive-feedback recurrence (the default deterministic generator on Linux / FreeBSD / macOS / Solaris userland since the late 1990s). Recoverable via parity-constraint solve given 100+ consecutive observations.",
        typical_k_lower_bound=100,
        validation_status="validated",
    ),
    "cubic_threshold_rule": OperatorMeta(
        internal_id="cubic",
        business_name="Cubic Threshold Rule",
        family_label="cubic_threshold_rule",
        description="Decision computed as a cubic polynomial of inputs reduced modulo a small bound.",
        typical_k_lower_bound=4,
        validation_status="validated",
    ),
}


# Reverse lookup: internal solver id → business operator key
_INTERNAL_TO_BUSINESS: dict[str, str] = {m.internal_id: k for k, m in OPERATORS.items()}


def operator_for(internal_id: str) -> OperatorMeta | None:
    """Translate an internal solver id (e.g. 'lcg') to the public OperatorMeta."""
    key = _INTERNAL_TO_BUSINESS.get(internal_id)
    if key is None:
        return None
    return OPERATORS[key]


def list_operators() -> list[dict]:
    """List of public operators for /spec/operators endpoint."""
    return [
        {
            "key": k,
            "name": m.business_name,
            "family_label": m.family_label,
            "description": m.description,
            "typical_k_lower_bound": m.typical_k_lower_bound,
            "validation_status": m.validation_status,
        }
        for k, m in OPERATORS.items()
    ]
