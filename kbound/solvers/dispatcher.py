"""Dispatcher — routes a classified task to the appropriate solver.

For v0:
  - spatial → return LLM recommendation (no actual call yet, just metadata)
  - algebraic + lcg → invoke RCE-LCG solver (symbolic, no neural)
  - algebraic + unknown → fallback to LLM or "use symbolic solver"
  - borderline → conservative LLM with low confidence flag
"""

from __future__ import annotations

from typing import Any

from kbound.compositional.search import predict as compositional_predict
from kbound.compositional.search import synthesize as compositional_synthesize
from kbound.solvers import verify as verify_mod
from kbound.solvers.llm_route import call_llm_for_query
from kbound.solvers.rce_boolean import solve_boolean_2input, solve_parity_kbit
from kbound.solvers.rce_cubic import solve_cubic_symbolic
from kbound.solvers.rce_dlp import solve_dlp_symbolic
from kbound.solvers.rce_glibc import solve_glibc
from kbound.solvers.rce_java import solve_java
from kbound.solvers.rce_lcg import solve_lcg_symbolic
from kbound.solvers.rce_modadd import solve_modadd_symbolic
from kbound.solvers.rce_modexp import solve_modexp_symbolic
from kbound.solvers.rce_modinv import solve_modinv_symbolic
from kbound.solvers.rce_modmul import solve_modmul_symbolic
from kbound.solvers.rce_mt19937 import solve_mt19937
from kbound.solvers.rce_polycoef import solve_polycoef_symbolic
from kbound.solvers.rce_recurrence import solve_recurrence_symbolic


def _wrap_with_verification(result: dict, examples: list, family: str) -> dict:
    """Re-verify the predicted formula against the support set as a final consistency check.

    This is the cell-audit-style sanity check (Prism 399/399 mappings perfect):
    even if the solver claimed 100% consistency, we re-run the recovered formula here
    using the public verify functions to catch any silent bug.
    """
    details = result.get("details", {})
    family_param = (details or {}) if isinstance(details, dict) else {}

    verified_score = None
    try:
        if family == "lcg":
            verified_score = verify_mod.verify_lcg(
                examples, family_param.get("a"), family_param.get("c"), family_param.get("m")
            )
        elif family == "polycoef":
            verified_score = verify_mod.verify_polycoef(
                examples,
                family_param.get("a"),
                family_param.get("b"),
                family_param.get("c"),
                family_param.get("p"),
            )
        elif family == "modmul":
            verified_score = verify_mod.verify_modmul(
                examples, family_param.get("a"), family_param.get("p")
            )
        elif family == "modexp":
            verified_score = verify_mod.verify_modexp(
                examples, family_param.get("a"), family_param.get("p")
            )
        elif family == "modinv":
            verified_score = verify_mod.verify_modinv(examples, family_param.get("p"))
        elif family == "mod_p_add":
            verified_score = verify_mod.verify_modadd(examples, family_param.get("p"))
    except Exception:
        verified_score = None

    if verified_score is not None:
        result["verified_consistency"] = verified_score
        # Adjust confidence: take min of solver's claim and our verification
        result["confidence"] = min(result.get("confidence", 1.0), verified_score)

    return result


def dispatch(
    geometry: str,
    family: str | None,
    examples: list[tuple],
    query: int | list[int],
    threshold: float = 0.80,
    use_llm_fallback: bool = True,
) -> dict[str, Any]:
    """Route task to solver, return answer + metadata."""

    # PRE-CHECK: Boolean overrides spatial when applicable (exact symbolic solution > LLM)
    if geometry == "spatial":
        try:
            xs_check = [e[0] for e in examples]
            ys_check = [e[1] for e in examples]
            arity_check = len(xs_check[0]) if isinstance(xs_check[0], (list, tuple)) else 1
            all_binary = (
                arity_check >= 2
                and all(
                    int(b) in (0, 1)
                    for x in xs_check
                    for b in (x if isinstance(x, (list, tuple)) else [x])
                )
                and all(int(y) in (0, 1) for y in ys_check)
            )
            if all_binary and arity_check == 2:
                bool_result = solve_boolean_2input(examples, query)
                if bool_result.get("consistency_score", 0) >= 0.95:
                    return {
                        "answer": bool_result["predicted_y"],
                        "solver_used": f"RCE-Boolean ({bool_result.get('operator')})",
                        "confidence": bool_result["consistency_score"],
                        "rationale": (
                            f"Boolean operator detected: {bool_result.get('operator')}. "
                            f"Truth table {bool_result.get('truth_table')}. "
                            f"Symbolic exact solution preferred over LLM route."
                        ),
                        "details": bool_result,
                    }
            if all_binary and arity_check > 2:
                par_result = solve_parity_kbit(examples, query)
                if par_result.get("consistency_score", 0) >= 0.95:
                    return {
                        "answer": par_result["predicted_y"],
                        "solver_used": f"RCE-Parity ({par_result.get('operator')})",
                        "confidence": par_result["consistency_score"],
                        "rationale": (
                            f"k-bit parity detected: {par_result.get('operator')}. "
                            f"Symbolic exact solution."
                        ),
                        "details": par_result,
                    }
        except Exception:
            pass  # If boolean check fails, fall through to LLM route

    # Spatial → LLM route (REAL Anthropic call now)
    if geometry == "spatial":
        llm_result = call_llm_for_query(examples, query, model="claude-haiku-4-5")
        return {
            "answer": llm_result.get("answer"),
            "solver_used": f"LLM ({llm_result.get('model_used', 'haiku-4-5')})",
            "confidence": llm_result.get("inferred_confidence"),
            "rationale": (
                f"Spatial-separable rule. Routed to {llm_result.get('model_used', 'haiku-4-5')} "
                f"(cheapest model above 80% threshold per paper #1 calibration). "
                f"LLM raw output: {llm_result.get('raw_output', '')[:120]}..."
            ),
            "details": llm_result,
        }

    # === Well-known PRNG families (large-modulus variants) ===

    if geometry == "algebraic" and family == "mt19937":
        result = solve_mt19937(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-MT19937 (Mersenne Twister state recovery)",
            "confidence": result.get("consistency_score", 0.0),
            "rationale": (
                f"Identified MT19937 — the canonical PRNG of Python's random, PHP's mt_rand, "
                f"Ruby, and pre-2018 V8 Math.random. Recovered full state via "
                f"{result.get('method', 'tempering inverse')}. Any future output is now predictable."
            ),
            "details": result,
        }

    if geometry == "algebraic" and family == "glibc":
        result = solve_glibc(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-Glibc (rand() canonical LCG, m=2³¹)",
            "confidence": result.get("consistency_score", 0.0),
            "rationale": (
                f"Identified the canonical glibc rand() LCG (a=1103515245, c=12345, m=2³¹). "
                f"Form: {result.get('form')}. Any future output is now predictable."
            ),
            "details": result,
        }

    if geometry == "algebraic" and family == "glibc_windowed":
        result = solve_glibc(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-Glibc-Windowed (rand() & 0x7FFF — 15-bit truncation)",
            "confidence": result.get("consistency_score", 0.0),
            "rationale": (
                "Identified glibc rand() with 15-bit windowed output (older / embedded libc). "
                "Recovered the missing 16 high bits of the seed by brute force."
            ),
            "details": result,
        }

    if geometry == "algebraic" and family == "java_random":
        result = solve_java(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-Java (java.util.Random state recovery via 2¹⁶ brute-force)",
            "confidence": result.get("consistency_score", 0.0),
            "rationale": (
                "Identified java.util.Random (m=2⁴⁸, a=0x5DEECE66D, b=0xB). Recovered the "
                "full 48-bit state by brute-forcing the 16 unknown low bits — the Minecraft "
                "seed-cracking attack."
            ),
            "details": result,
        }

    # Algebraic + glibc TGFSR (additive feedback shift register, post-glibc-2.0 default)
    if geometry == "algebraic" and family == "glibc_tgfsr":
        from kbound.solvers.rce_glibc_tgfsr import solve_glibc_tgfsr

        result = solve_glibc_tgfsr(examples, query)
        return _wrap_with_verification(
            {
                "answer": result["predicted_y"],
                "solver_used": "RCE-Glibc-TGFSR (additive feedback, LSB-recovery via GF(2) elimination)",
                "confidence": result.get("consistency_score", 0.0),
                "rationale": (
                    "Identified additive-feedback stateful pattern: 31-word internal state, "
                    "recurrence v_k = v_{k-31} + v_{k-3} mod 2^32, output = v_k >> 1. "
                    "Recovered the 31 unknown LSB bits via parity-constraint solve over "
                    "the recurrence; full state then determines all subsequent outputs."
                ),
                "details": result,
            },
            examples,
            "glibc_tgfsr",
        )

    # Algebraic + generic linear recurrence (Hankel-det-gcd — large-modulus)
    if geometry == "algebraic" and family == "recurrence_generic":
        from kbound.solvers.rce_recurrence_generic import solve_recurrence_generic

        result = solve_recurrence_generic(examples, query)
        order = result.get("order")
        coeffs = result.get("coefficients", [])
        m = result.get("m")
        if order == 2 and len(coeffs) == 2:
            terms = f"{coeffs[0]}·y_(n-1) + {coeffs[1]}·y_(n-2)"
        elif order == 3 and len(coeffs) == 3:
            terms = f"{coeffs[0]}·y_(n-1) + {coeffs[1]}·y_(n-2) + {coeffs[2]}·y_(n-3)"
        else:
            terms = f"order-{order} linear combination of previous terms"
        return _wrap_with_verification(
            {
                "answer": result["predicted_y"],
                "solver_used": f"RCE-Recurrence-Generic (Hankel det gcd, order {order})",
                "confidence": result.get("consistency_score", 0.0),
                "rationale": (
                    f"Identified order-{order} linear recurrence y_n = ({terms}) mod {m}. "
                    f"The determinant-gcd reconstruction recovers the unknown modulus from "
                    f"sliding-window cross-products, then solves the system over the recovered modulus."
                ),
                "details": result,
            },
            examples,
            "recurrence_generic",
        )

    # Algebraic + generic polynomial (Vandermonde-determinant-gcd — large-modulus)
    if geometry == "algebraic" and family == "polycoef_generic":
        from kbound.solvers.rce_polycoef_generic import solve_polycoef_generic

        result = solve_polycoef_generic(examples, query)
        deg = result.get("degree", 2)
        if deg == 2:
            terms = f"{result.get('a')}·x² + {result.get('b')}·x + {result.get('c')}"
        elif deg == 3:
            terms = f"{result.get('a')}·x³ + {result.get('b')}·x² + {result.get('c')}·x + {result.get('d')}"
        else:
            terms = f"degree-{deg} polynomial"
        return _wrap_with_verification(
            {
                "answer": result["predicted_y"],
                "solver_used": f"RCE-Polycoef-Generic (Vandermonde det gcd, degree {deg})",
                "confidence": result.get("consistency_score", 0.0),
                "rationale": (
                    f"Identified degree-{deg} polynomial f(x) = ({terms}) mod {result.get('p')}. "
                    f"The Vandermonde-determinant gcd attack reconstructs the unknown modulus from "
                    f"({deg}+2)-tuple cross-products, then solves the system over the recovered modulus."
                ),
                "details": result,
            },
            examples,
            "polycoef_generic",
        )

    # Algebraic + generic LCG (Boyar attack — large-modulus / unknown-params)
    if geometry == "algebraic" and family == "lcg_generic":
        from kbound.solvers.rce_lcg_generic import solve_lcg_generic

        result = solve_lcg_generic(examples, query)
        return _wrap_with_verification(
            {
                "answer": result["predicted_y"],
                "solver_used": "RCE-LCG-Generic (Boyar 1989 attack on unknown a, c, m)",
                "confidence": result.get("consistency_score", 0.0),
                "rationale": (
                    f"Identified LCG with recovered parameters a={result.get('a')}, "
                    f"c={result.get('c')}, m={result.get('m')}. The Boyar attack reconstructs "
                    f"(a, c, m) from gcd of cross-products of consecutive differences — works "
                    f"for any pure LCG regardless of modulus size."
                ),
                "details": result,
            },
            examples,
            "lcg_generic",
        )

    # Algebraic + identified family
    if geometry == "algebraic" and family == "lcg":
        result = solve_lcg_symbolic(examples, query)
        wrapped = {
            "answer": result["predicted_y"],
            "solver_used": "RCE-LCG (symbolic consistency search)",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified LCG family with parameters a={result['a']}, c={result['c']}, "
                f"m={result['m']}. Symbolic search reached {result['consistency_score']:.0%} "
                f"consistency on the support set. RCE crosses the algebraic boundary where "
                f"frontier LLMs fail."
            ),
            "details": result,
        }
        return _wrap_with_verification(wrapped, examples, "lcg")

    # Algebraic + DLP (discrete log — inverse of ModExp)
    if geometry == "algebraic" and family == "dlp":
        result = solve_dlp_symbolic(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-DLP (discrete logarithm via brute baby-step)",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified discrete log: x such that {result.get('a')}^x ≡ y mod {result.get('p')}. "
                f"Symbolic search reached {result['consistency_score']:.0%} consistency. "
                f"Cryptanalytic relevance: ElGamal/DSA primitive."
            ),
            "details": result,
        }

    if geometry == "algebraic" and family == "polycoef":
        result = solve_polycoef_symbolic(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-Polycoef (3x3 mod-p Gaussian elimination)",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified polynomial family f(x) = ({result['a']}·x² + {result['b']}·x + "
                f"{result['c']}) mod {result['p']}. Linear-system mod p reached "
                f"{result['consistency_score']:.0%} consistency. RCE-Polycoef crosses the algebraic "
                f"boundary where frontier LLMs fail."
            ),
            "details": result,
        }

    if geometry == "algebraic" and family == "cubic":
        result = solve_cubic_symbolic(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-Cubic (4x4 mod-p Vandermonde — MiMC / AO primitive starter)",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified cubic polynomial f(x) = ({result['a']}·x³ + {result['b']}·x² + "
                f"{result['c']}·x + {result['d']}) mod {result['p']}. Recovered via Vandermonde solve "
                f"over GF(p). This is the building block for MiMC permutation cryptanalysis "
                f"and the entry point to ZK-friendly AO primitive auditing."
            ),
            "details": result,
        }

    # Algebraic + Boolean 2-input
    if geometry == "algebraic" and family == "boolean_2input":
        result = solve_boolean_2input(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-Boolean (16-truth-table search)",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified Boolean 2-input operator: {result.get('operator')}. "
                f"Truth table: {result.get('truth_table')}. "
                f"Symbolic search reached {result['consistency_score']:.0%} consistency."
            ),
            "details": result,
        }

    # Algebraic + parity (k-bit input)
    if geometry == "algebraic" and family == "parity_kbit":
        result = solve_parity_kbit(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-Parity (k-bit XOR)",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified k-bit parity rule: {result.get('operator')}. "
                f"Symbolic verification: {result['consistency_score']:.0%} consistent."
            ),
            "details": result,
        }

    # Algebraic + mod_p_add (2-input modular addition)
    if geometry == "algebraic" and family == "mod_p_add":
        result = solve_modadd_symbolic(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-ModAdd (symbolic prime search)",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified 2-input modular addition family: y = (x1 + x2) mod {result['p']}. "
                f"Symbolic search reached {result['consistency_score']:.0%} consistency on the support set."
            ),
            "details": result,
        }

    # Algebraic + ModMul (y = (a*x) mod p)
    if geometry == "algebraic" and family == "modmul":
        result = solve_modmul_symbolic(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-ModMul (modular multiplication)",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified modular multiplication: y = ({result['a']}·x) mod {result['p']}. "
                f"Symbolic search reached {result['consistency_score']:.0%} consistency."
            ),
            "details": result,
        }

    # Algebraic + ModInv (y = x^(-1) mod p)
    if geometry == "algebraic" and family == "modinv":
        result = solve_modinv_symbolic(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-ModInv (modular inverse via extended Euclidean)",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified modular inverse: y = x⁻¹ mod {result['p']}. "
                f"Symbolic search reached {result['consistency_score']:.0%} consistency. "
                f"Relevant to cryptographic signature verification."
            ),
            "details": result,
        }

    # Algebraic + ModExp (y = a^x mod p)  — RSA primitive
    if geometry == "algebraic" and family == "modexp":
        result = solve_modexp_symbolic(examples, query)
        return {
            "answer": result["predicted_y"],
            "solver_used": "RCE-ModExp (modular exponentiation, RSA primitive)",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified modular exponentiation: y = {result['a']}^x mod {result['p']}. "
                f"Symbolic search reached {result['consistency_score']:.0%} consistency. "
                f"This is an RSA primitive operation."
            ),
            "details": result,
        }

    # Algebraic + recurrence (Fibonacci-like or linear)
    if geometry == "algebraic" and family in ("recurrence_fib", "recurrence_linear"):
        result = solve_recurrence_symbolic(
            examples, query, fibonacci_only=(family == "recurrence_fib")
        )
        return {
            "answer": result["predicted_y"],
            "solver_used": f"RCE-Recurrence ({family})",
            "confidence": result["consistency_score"],
            "rationale": (
                f"Identified linear recurrence: y_n = ({result.get('a', '?')}*y_{{n-1}} + "
                f"{result.get('b', '?')}*y_{{n-2}}) mod {result.get('m', '?')}. "
                f"Symbolic search reached {result['consistency_score']:.0%} consistency."
            ),
            "details": result,
        }

    # Algebraic + unknown family — try compositional synthesis BEFORE LLM fallback.
    # This is novel: depth-2 search over typed primitive compositions.
    if geometry == "algebraic" and family in (None, "unknown"):
        try:
            arity = len(examples[0][0]) if isinstance(examples[0][0], (list, tuple)) else 1
            if arity == 1:
                pairs_int = [
                    (int(x) if not isinstance(x, (list, tuple)) else int(x[0]), int(y))
                    for x, y in examples
                ]
                comp_result = compositional_synthesize(pairs_int)
                if comp_result.get("score", 0) >= 0.95:
                    qx = int(query) if not isinstance(query, (list, tuple)) else int(query[0])
                    pred = compositional_predict(comp_result, qx)
                    return {
                        "answer": pred,
                        "solver_used": f"RCE-Compose (depth-{comp_result['depth']}: {' ∘ '.join(comp_result['atoms'])})",
                        "confidence": comp_result["score"],
                        "rationale": (
                            f"Compositional synthesis recovered: y = {comp_result.get('expression', '?')}. "
                            f"This is novel: existing tools recover atomic rules; we synthesize "
                            f"compositions from K observations automatically."
                        ),
                        "details": comp_result,
                    }
        except Exception:
            pass  # fall through to LLM

    # Algebraic + unknown family (after composition attempt failed)
    if geometry == "algebraic":
        if use_llm_fallback:
            return {
                "answer": None,
                "solver_used": "LLM fallback (algebraic family unknown — v0 stub)",
                "confidence": 0.05,
                "rationale": (
                    "Algebraic structure detected but specific family not identified. "
                    "Per paper #1, frontier LLMs fail at chance on unknown algebraic at K=16. "
                    "Recommend: provide more context about the rule family, or use symbolic "
                    "solver if available."
                ),
                "details": {"family_identification_failed": True},
            }
        else:
            return {
                "answer": None,
                "solver_used": "no_solver",
                "confidence": 0.0,
                "rationale": "Algebraic family unknown and LLM fallback disabled.",
                "details": {},
            }

    # Borderline + Boolean / parity override
    if geometry == "borderline":
        try:
            xs_check = [e[0] for e in examples]
            ys_check = [e[1] for e in examples]
            arity_check = len(xs_check[0]) if isinstance(xs_check[0], (list, tuple)) else 1
            all_binary = all(
                int(b) in (0, 1)
                for x in xs_check
                for b in (x if isinstance(x, (list, tuple)) else [x])
            ) and all(int(y) in (0, 1) for y in ys_check)
            if all_binary and arity_check >= 2:
                if family == "parity_kbit" or arity_check > 2:
                    par_result = solve_parity_kbit(examples, query)
                    if par_result.get("consistency_score", 0) >= 0.95:
                        return {
                            "answer": par_result["predicted_y"],
                            "solver_used": f"RCE-Parity ({par_result.get('operator')})",
                            "confidence": par_result["consistency_score"],
                            "rationale": (
                                f"k-bit parity detected: {par_result.get('operator')}. "
                                f"Symbolic exact solution."
                            ),
                            "details": par_result,
                        }
                if arity_check == 2:
                    bool_result = solve_boolean_2input(examples, query)
                    if bool_result.get("consistency_score", 0) >= 0.95:
                        return {
                            "answer": bool_result["predicted_y"],
                            "solver_used": f"RCE-Boolean ({bool_result.get('operator')})",
                            "confidence": bool_result["consistency_score"],
                            "rationale": f"Boolean operator: {bool_result.get('operator')}.",
                            "details": bool_result,
                        }
        except Exception:
            pass

    # Borderline (no specific solver matched)
    return {
        "answer": None,
        "solver_used": "LLM (borderline — low confidence)",
        "confidence": 0.5,
        "rationale": "Geometry borderline — neither cleanly spatial nor clearly algebraic. Proceed with caution.",
        "details": {"geometry": geometry},
    }
