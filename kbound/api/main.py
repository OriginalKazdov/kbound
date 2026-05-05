"""Induction Compiler v0 — FastAPI service.

End-to-end pipeline:
  1. Oracle classifies geometry (spatial / algebraic / borderline)
  2. Family identifier classifies algebraic subfamily (lcg / polycoef / mod_p / ...)
  3. Dispatcher routes to specific solver
  4. Returns answer + metadata

Run locally:
    uvicorn kbound.api.main:app --reload --port 8000

Endpoints:
    POST /induce          — Run the full pipeline. Returns answer + compact trace.
    POST /induce/text     — Same but accepts pasted free-form text input.
    POST /explain         — Verbose trace: every feature, candidate, equation.
    GET  /families        — List all supported families with metadata.
    GET  /families/{id}   — Detail for a specific family.
    GET  /capability      — Compact heatmap-friendly capability matrix.
    GET  /demos           — List prebuilt demo cases.
    GET  /demos/{id}      — Get a specific demo's full input.
    POST /demos/{id}/run  — Run a demo through the pipeline.
    GET  /health          — Liveness check.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from kbound._pipeline import (
    _build_explain_stages as _build_explain_stages_impl,
)
from kbound._pipeline import (
    _extract_params as _extract_params_impl,
)
from kbound._pipeline import (
    _run_pipeline as _run_pipeline_impl,
)
from kbound.active.state import ActiveSession
from kbound.api.demos import DEMOS, get_demo, list_demos
from kbound.api.families import (
    FAMILIES,
    capability_matrix,
    get_family,
    list_families,
)
from kbound.api.parsers import parse_input

app = FastAPI(
    title="Induction Compiler v0",
    description="Geometric routing of in-context rule-induction tasks.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Request / response schemas
# ============================================================


class InduceRequest(BaseModel):
    examples: list[tuple[int | list[int], int]] = Field(
        ..., description="K (input, output) pairs demonstrating the rule"
    )
    query: int | list[int] = Field(..., description="Query input to predict y for")
    threshold: float = Field(0.80, description="Minimum P(success) for LLM routing")
    use_llm_fallback: bool = Field(True, description="If algebraic family unknown, fallback to LLM")


class InduceTextRequest(BaseModel):
    text: str = Field(..., description="Free-form input: JSON, CSV, arrow form, or mixed")
    threshold: float = Field(0.80)
    use_llm_fallback: bool = Field(True)


class InduceResponse(BaseModel):
    answer: int | None
    geometry: str
    family: str | None
    solver_used: str
    confidence: float | None
    rationale: str
    elapsed_ms: float
    verified: bool
    trace: dict[str, Any]


class ExplainResponse(BaseModel):
    """Verbose trace — for the /explain endpoint and the frontend pipeline panel."""

    answer: int | None
    verified: bool
    elapsed_ms: float
    stages: list[dict[str, Any]]  # each stage: {step, name, status, summary, details}
    final: dict[str, Any]


# ============================================================
# Pipeline core (shared helper)
# ============================================================


def _run_pipeline(
    examples: list,
    query: Any,
    threshold: float = 0.80,
    use_llm_fallback: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    """FastAPI-aware wrapper: same as kbound._pipeline._run_pipeline but
    converts the underlying ValueError into an HTTPException(400)."""
    try:
        return _run_pipeline_impl(
            examples=examples,
            query=query,
            threshold=threshold,
            use_llm_fallback=use_llm_fallback,
            verbose=verbose,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# Re-export the helpers under their original names so the endpoint code below
# can stay verbatim (they originally lived in this module before the pipeline
# was lifted into the fastapi-free `_pipeline.py`).
_extract_params = _extract_params_impl
_build_explain_stages = _build_explain_stages_impl


# ============================================================
# Root + health
# ============================================================


@app.get("/")
def root():
    return {
        "service": "Induction Compiler",
        "version": app.version,
        "endpoints": [
            "POST /induce",
            "POST /induce/text",
            "POST /explain",
            "GET /families",
            "GET /families/{id}",
            "GET /capability",
            "GET /demos",
            "GET /demos/{id}",
            "POST /demos/{id}/run",
            "GET /health",
            "GET /docs",
        ],
        "supported_families": [f["id"] for f in FAMILIES],
        "n_demos": len(DEMOS),
    }


@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ============================================================
# /induce — primary endpoint
# ============================================================


@app.post("/induce", response_model=InduceResponse)
def induce(req: InduceRequest):
    """Route a rule-induction task to the appropriate solver. Returns answer + compact trace."""
    result = _run_pipeline(
        examples=req.examples,
        query=req.query,
        threshold=req.threshold,
        use_llm_fallback=req.use_llm_fallback,
        verbose=False,
    )
    return InduceResponse(**result)


@app.post("/induce/text", response_model=InduceResponse)
def induce_text(req: InduceTextRequest):
    """Same as /induce but accepts free-form pasted text (JSON, CSV, arrow form)."""
    parsed = parse_input(req.text)
    if not parsed["examples"]:
        raise HTTPException(
            400, f"No examples parsed from input (format detected: {parsed['format_detected']})"
        )
    if parsed["query"] is None:
        raise HTTPException(
            400, "No query found in input. Add a line like 'query: 50' or '50 -> ?'."
        )
    result = _run_pipeline(
        examples=parsed["examples"],
        query=parsed["query"],
        threshold=req.threshold,
        use_llm_fallback=req.use_llm_fallback,
        verbose=False,
    )
    result["trace"]["input"] = {"format_detected": parsed["format_detected"]}
    return InduceResponse(**result)


# ============================================================
# /induce/active — interactive query optimization
# ============================================================


class ActiveStartRequest(BaseModel):
    examples: list[tuple[int, int]] = Field(
        ..., description="Initial K observations (input, output) pairs"
    )
    families: list[str] | None = Field(
        None, description="Restrict candidate families (default: lcg, polycoef, modmul, modexp)"
    )
    query_pool: list[int] | None = Field(
        None, description="Inputs to consider for next query (default: 0..200 + a few large)"
    )


class ActiveContinueRequest(BaseModel):
    observations: list[tuple[int, int]] = Field(
        ..., description="ALL observations so far (initial + any added queries)"
    )
    families: list[str] | None = Field(None)
    query_pool: list[int] | None = Field(None)


class ActiveResponse(BaseModel):
    n_candidates: int
    is_unique: bool
    is_failed: bool
    family_split: dict[str, int]
    entropy_bits: float
    suggested_query: int | None
    info_gain_bits: float | None
    predicted_outcomes: dict[str, int] | None
    candidates_preview: list[str]
    k_used: int
    elapsed_ms: float


def _active_session_to_response(session: ActiveSession, suggestion: dict | None) -> ActiveResponse:
    return ActiveResponse(
        n_candidates=session.n_candidates,
        is_unique=session.is_unique,
        is_failed=session.is_failed,
        family_split=session.family_distribution(),
        entropy_bits=session.current_entropy_bits(),
        suggested_query=(suggestion or {}).get("suggested_x") if suggestion else None,
        info_gain_bits=(suggestion or {}).get("info_gain_bits") if suggestion else None,
        predicted_outcomes={
            str(k): v for k, v in (suggestion or {}).get("predicted_outcomes", {}).items()
        }
        if suggestion
        else None,
        candidates_preview=[repr(c) for c in session.candidates[:10]],
        k_used=session.k_used(),
        elapsed_ms=session.elapsed_ms,
    )


@app.post("/induce/active", response_model=ActiveResponse)
def induce_active(req: ActiveContinueRequest):
    """Active rule-recovery: given current observations, return next-best query suggestion.

    The client sends ALL observations so far (this endpoint is stateless). The server
    builds a candidate pool consistent with those observations, then returns the input
    that maximizes expected information gain.

    When n_candidates == 1, the recovery is unique and the user can predict any future
    output via the single surviving candidate.
    """
    if len(req.observations) < 2:
        raise HTTPException(400, "Need at least 2 initial observations to start active session")

    session = ActiveSession(
        observations=[(int(x), int(y)) for x, y in req.observations],
        families=req.families,
    )

    if session.is_unique or session.is_failed:
        return _active_session_to_response(session, suggestion=None)

    suggestion = session.suggest_query(query_pool=req.query_pool)
    return _active_session_to_response(session, suggestion)


@app.post("/explain/text", response_model=ExplainResponse)
def explain_text(req: InduceTextRequest):
    """Verbose trace, free-form text input. Used by the frontend dashboard."""
    parsed = parse_input(req.text)
    if not parsed["examples"]:
        raise HTTPException(
            400, f"No examples parsed from input (format detected: {parsed['format_detected']})"
        )
    if parsed["query"] is None:
        raise HTTPException(
            400, "No query found in input. Add a line like 'query: 50' or '50 -> ?'."
        )
    result = _run_pipeline(
        examples=parsed["examples"],
        query=parsed["query"],
        threshold=req.threshold,
        use_llm_fallback=req.use_llm_fallback,
        verbose=True,
    )
    stages = _build_explain_stages(result)
    return ExplainResponse(
        answer=result["answer"],
        verified=result["verified"],
        elapsed_ms=result["elapsed_ms"],
        stages=stages,
        final={
            "answer": result["answer"],
            "verified": result["verified"],
            "geometry": result["geometry"],
            "family": result["family"],
            "solver_used": result["solver_used"],
            "rationale": result["rationale"],
        },
    )


# ============================================================
# /explain — verbose pipeline trace
# ============================================================


@app.post("/explain", response_model=ExplainResponse)
def explain(req: InduceRequest):
    """Same pipeline as /induce, but returns the verbose 5-stage trace for UI rendering."""
    result = _run_pipeline(
        examples=req.examples,
        query=req.query,
        threshold=req.threshold,
        use_llm_fallback=req.use_llm_fallback,
        verbose=True,
    )
    stages = _build_explain_stages(result)
    return ExplainResponse(
        answer=result["answer"],
        verified=result["verified"],
        elapsed_ms=result["elapsed_ms"],
        stages=stages,
        final={
            "answer": result["answer"],
            "verified": result["verified"],
            "geometry": result["geometry"],
            "family": result["family"],
            "solver_used": result["solver_used"],
            "rationale": result["rationale"],
        },
    )


# ============================================================
# /families — capability catalog
# ============================================================


@app.get("/families")
def families(category: str | None = None):
    """List all supported families with full metadata. Optional ?category=algebraic|spatial."""
    return {
        "count": len(FAMILIES),
        "families": list_families(category),
    }


@app.get("/families/{family_id}")
def family_detail(family_id: str):
    f = get_family(family_id)
    if not f:
        raise HTTPException(404, f"Unknown family: {family_id}")
    return f


@app.get("/capability")
def capability():
    """Compact capability matrix for the frontend heatmap."""
    return capability_matrix()


# ============================================================
# /demos — prebuilt demo cases
# ============================================================


@app.get("/demos")
def demos():
    """List all prebuilt demos (compact metadata)."""
    return {
        "count": len(DEMOS),
        "demos": list_demos(),
    }


@app.get("/demos/{demo_id}")
def demo_detail(demo_id: str):
    """Full demo payload including examples and expected answer."""
    d = get_demo(demo_id)
    if not d:
        raise HTTPException(404, f"Unknown demo: {demo_id}")
    return d


@app.post("/demos/{demo_id}/run")
def demo_run(demo_id: str):
    """Run a prebuilt demo through the full /explain pipeline."""
    import os

    d = get_demo(demo_id)
    if not d:
        raise HTTPException(404, f"Unknown demo: {demo_id}")
    if d.get("requires_api_key") and not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            503,
            f"Demo '{demo_id}' takes the spatial path which requires an Anthropic API key. "
            f"Set ANTHROPIC_API_KEY and retry.",
        )
    result = _run_pipeline(
        examples=d["examples"],
        query=d["query"],
        verbose=True,
    )
    stages = _build_explain_stages(result)
    return {
        "demo": {"id": d["id"], "title": d["title"], "real_world": d["real_world"]},
        "expected_answer": d["expected_answer"],
        "true_params": d.get("true_params"),
        "matches_expected": result["answer"] == d["expected_answer"],
        "answer": result["answer"],
        "verified": result["verified"],
        "elapsed_ms": result["elapsed_ms"],
        "stages": stages,
    }
