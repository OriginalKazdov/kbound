"""Engine pipeline shared by the Python API, the CLI, and the FastAPI service.

This module has NO web dependencies. It runs the full classify → family-id →
dispatch → verify pipeline and returns plain dicts. The FastAPI layer in
`kbound.api.main` wraps the same primitives and converts `ValueError` into
`HTTPException(400)` at the boundary.

Keeping this layer fastapi-free is what lets `import kbound` and
`from kbound import recover_rule` work without the optional `[server]` extras
installed.
"""

from __future__ import annotations

import time
from typing import Any

from kbound.classifier.family_id import identify_family
from kbound.classifier.oracle_classifier import classify_geometry
from kbound.solvers.dispatcher import dispatch


def _run_pipeline(
    examples: list,
    query: Any,
    threshold: float = 0.80,
    use_llm_fallback: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run the full classify → family-id → dispatch → verify pipeline.

    Single source of truth used by `/induce`, `/explain`, the CLI, and any
    callers that need both the answer and the verbose stage trace.

    Raises
    ------
    ValueError
        if `len(examples) < 4`. Callers that prefer HTTP semantics should
        catch this and re-raise as `fastapi.HTTPException(400, ...)`.
    """
    if len(examples) < 4:
        raise ValueError("Need at least 4 examples")

    t0 = time.perf_counter()

    # Stage 1: Geometry classification
    t_geom = time.perf_counter()
    geom_result = classify_geometry(examples)
    geom_ms = (time.perf_counter() - t_geom) * 1000

    # Stage 2: Family identification (only if algebraic/borderline)
    t_fam = time.perf_counter()
    family = None
    family_alternatives: list[str] = []
    if geom_result["geometry"] in ("algebraic", "borderline"):
        family = identify_family(examples, geom_result)
        family_alternatives = geom_result.get("families_tried", []) or []
    fam_ms = (time.perf_counter() - t_fam) * 1000

    # Stage 3: Dispatch (solver + verification embedded)
    t_disp = time.perf_counter()
    dispatch_result = dispatch(
        geometry=geom_result["geometry"],
        family=family,
        examples=examples,
        query=query,
        threshold=threshold,
        use_llm_fallback=use_llm_fallback,
    )
    disp_ms = (time.perf_counter() - t_disp) * 1000

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    confidence = dispatch_result.get("confidence") or 0.0
    verified_score = dispatch_result.get("verified_consistency")
    verified = bool(verified_score and verified_score >= 0.95) or confidence >= 0.95

    trace = {
        "geometry": {
            "verdict": geom_result["geometry"],
            "confidence": geom_result.get("confidence"),
            "elapsed_ms": geom_ms,
        },
        "family": {
            "id": family,
            "alternatives_tried": family_alternatives,
            "elapsed_ms": fam_ms,
        },
        "solver": {
            "name": dispatch_result["solver_used"],
            "elapsed_ms": disp_ms,
            "params": _extract_params(dispatch_result.get("details", {})),
        },
        "verification": {
            "consistency_score": verified_score,
            "passed": verified,
        },
    }

    if verbose:
        trace["geometry"]["features"] = geom_result.get("features")
        trace["geometry"]["per_model_accuracy"] = geom_result.get("per_model_accuracy")
        trace["solver"]["full_details"] = dispatch_result.get("details")

    return {
        "answer": dispatch_result.get("answer"),
        "geometry": geom_result["geometry"],
        "family": family,
        "solver_used": dispatch_result["solver_used"],
        "confidence": dispatch_result.get("confidence"),
        "rationale": dispatch_result.get("rationale", ""),
        "elapsed_ms": elapsed_ms,
        "verified": verified,
        "trace": trace,
    }


def _extract_params(details: dict) -> dict | None:
    """Pull the solver-recovered parameters out of the dispatcher details blob."""
    if not isinstance(details, dict):
        return None
    keys = ("a", "b", "c", "m", "p", "k", "operator", "truth_table")
    out = {k: details[k] for k in keys if k in details and details[k] is not None}
    return out or None


def _build_explain_stages(result: dict) -> list[dict]:
    """Convert the pipeline result into 5 numbered stage cards for the frontend."""
    trace = result["trace"]
    geom = trace["geometry"]
    fam = trace["family"]
    solver = trace["solver"]
    verif = trace["verification"]

    return [
        {
            "step": 1,
            "name": "Geometry Classification",
            "status": "ok",
            "summary": f"{geom['verdict']} (confidence {(geom.get('confidence') or 0):.2f})",
            "elapsed_ms": geom.get("elapsed_ms"),
            "details": {
                "verdict": geom["verdict"],
                "confidence": geom.get("confidence"),
                "features": geom.get("features"),
                "per_model_accuracy": geom.get("per_model_accuracy"),
            },
        },
        {
            "step": 2,
            "name": "Family Detection",
            "status": "ok" if fam["id"] else "skipped",
            "summary": (f"{fam['id']}" if fam["id"] else f"skipped ({geom['verdict']} path)"),
            "elapsed_ms": fam.get("elapsed_ms"),
            "details": {
                "family_id": fam["id"],
                "alternatives_tried": fam.get("alternatives_tried", []),
            },
        },
        {
            "step": 3,
            "name": "Solver Invocation",
            "status": "ok" if result["answer"] is not None else "failed",
            "summary": solver["name"],
            "elapsed_ms": solver.get("elapsed_ms"),
            "details": {
                "solver_name": solver["name"],
                "params_recovered": solver.get("params"),
                "full_details": solver.get("full_details"),
            },
        },
        {
            "step": 4,
            "name": "Verification & Audit",
            "status": (
                "ok"
                if verif["passed"]
                else ("warn" if (verif.get("consistency_score") or 0) > 0.5 else "failed")
            ),
            "summary": (
                f"consistency {verif.get('consistency_score') or result.get('confidence', 0):.0%}"
            ),
            "elapsed_ms": None,
            "details": verif,
        },
        {
            "step": 5,
            "name": "Answer",
            "status": "ok" if result["answer"] is not None else "failed",
            "summary": (
                f"answer = {result['answer']}" if result["answer"] is not None else "no answer"
            ),
            "elapsed_ms": None,
            "details": {
                "answer": result["answer"],
                "verified": result["verified"],
                "rationale": result["rationale"],
            },
        },
    ]
