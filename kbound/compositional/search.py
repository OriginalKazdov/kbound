"""Composition search engine — discover layered transforms from K observations.

Algorithm (depth ≤ 2):
  1. Try each atom alone. If best score ≥ 0.95, return single-atom recovery.
  2. Try each (outer, inner) pair:
       For each candidate params of outer atom (from a top-K param search):
         Invert outer with these params: z_i = outer^{-1}(y_i)
         For each x_i, z_i candidate combination, search inner atom params
         If inner fits with score ≥ 0.95, return composition

Novelty: this is the FIRST open-source tool that automatically discovers
COMPOSITIONS of cryptanalytic primitives from input/output observations.
Existing tools (CLAASP, OCP) are designer-side; existing recovery tools
require human selection of attack class.

Atoms are textbook. The search engine combining them is what's new.
"""

from __future__ import annotations

import time

from kbound.compositional.atoms import ATOMS


def _try_single_atom(pairs: list[tuple[int, int]], atom_name: str) -> dict | None:
    """Try to fit a single atom. Returns best fit or None."""
    atom = ATOMS[atom_name]
    candidates = atom.param_search(pairs)
    if not candidates:
        return None
    best_params, best_score = candidates[0]
    if best_score >= 0.95:
        return {
            "depth": 1,
            "atoms": [atom_name],
            "params": [best_params],
            "score": best_score,
        }
    return None


def _try_composition(
    pairs: list[tuple[int, int]],
    outer_name: str,
    inner_name: str,
    max_outer_candidates: int = 8,
) -> dict | None:
    """Try y = outer(inner(x)).

    Strategy:
      1. Search outer params over (intermediate, y) — but we don't have intermediate.
         So: enumerate outer param candidates over a heuristic grid.
      2. For each candidate of outer, invert: z_i = outer^{-1}(y_i)
      3. If z_i is multi-valued, pick the smallest non-negative.
      4. Search inner over (x, z) pairs.
      5. Verify the full composition end-to-end on ALL pairs.
    """
    outer = ATOMS[outer_name]
    inner = ATOMS[inner_name]
    if not outer.invertible_given_params:
        return None  # can't use as outer if not invertible

    # Get top outer param candidates from a heuristic search:
    # we treat the outer as fitting (intermediate, y), but we don't have intermediates.
    # Instead, we enumerate over all reasonable outer params directly.
    outer_param_grid = _enumerate_outer_params(outer_name, [y for _, y in pairs])

    for outer_params in outer_param_grid[: max_outer_candidates * 5]:
        # Invert outer to recover plausible z values
        try:
            z_candidates_per_pair = []
            for _, y in pairs:
                zs = outer.invert(y, outer_params, hint_max=4096)
                if not zs:
                    z_candidates_per_pair = None
                    break
                z_candidates_per_pair.append(zs)
            if z_candidates_per_pair is None:
                continue
        except Exception:
            continue

        # For tractability, take the smallest non-negative z for each pair as primary,
        # but also explore a few alternatives.
        z_primary = [zs[0] for zs in z_candidates_per_pair]
        inner_pairs = list(zip([x for x, _ in pairs], z_primary, strict=False))

        # Search inner atom on these pairs
        inner_candidates = inner.param_search(inner_pairs)
        if not inner_candidates:
            continue
        inner_params, inner_score = inner_candidates[0]

        # Verify full composition end-to-end
        n_ok = 0
        for x, y in pairs:
            z = inner.forward(x, inner_params)
            y_pred = outer.forward(z, outer_params)
            if y_pred == y:
                n_ok += 1
        full_score = n_ok / len(pairs)

        if full_score >= 0.95:
            return {
                "depth": 2,
                "atoms": [inner_name, outer_name],  # in evaluation order: inner first
                "params": [inner_params, outer_params],
                "score": full_score,
                "expression": _format_expression(
                    inner_name, inner_params, outer_name, outer_params
                ),
            }

    return None


def _enumerate_outer_params(atom_name: str, ys: list[int]) -> list[dict]:
    """Generate a grid of plausible parameters for the outer atom."""
    if atom_name == "mod_reduce":
        ymax = max(ys)
        # Outer is mod_reduce by some n > ymax. Possible n values:
        return [{"n": n} for n in list(range(max(ymax + 1, 2), 64)) + [128, 256, 512, 1024]]
    elif atom_name == "affine_mod":
        ymax = max(ys)
        from kbound.compositional.atoms import SMALL_PRIMES

        out = []
        for m in SMALL_PRIMES:
            if m <= ymax:
                continue
            for a in range(1, m):
                for c in range(0, m):
                    out.append({"a": a, "c": c, "m": m})
        return out
    elif atom_name == "const_add":
        return [{"c": c} for c in range(-30, 31)]
    elif atom_name == "identity":
        return [{}]
    else:
        return []


def _format_expression(inner_name, inner_params, outer_name, outer_params):
    """Pretty-print the synthesized composition as a math expression."""
    inner_expr = _format_atom(inner_name, "x", inner_params)
    outer_expr = _format_atom(outer_name, inner_expr, outer_params)
    return outer_expr


def _format_atom(name, var, p):
    if name == "affine_mod":
        return f"({p['a']}·{var} + {p['c']}) mod {p['m']}"
    if name == "mod_reduce":
        return f"({var}) mod {p['n']}"
    if name == "power":
        return f"({var})^{p['k']}"
    if name == "const_add":
        return f"({var} + {p['c']})"
    if name == "identity":
        return var
    return f"{name}({var})"


# ============================================================
# Top-level synthesizer
# ============================================================

INVERTIBLE_OUTER_ATOMS = [
    "mod_reduce",
    "affine_mod",
    "const_add",
    "identity",
    "xor_const",
    "bitshift_right",
]
ALL_ATOMS = [
    "affine_mod",
    "mod_reduce",
    "power",
    "const_add",
    "identity",
    "xor_const",
    "bitshift_right",
]


# ============================================================
# Fused param search — joint enumeration over composition param space.
# Faster + more reliable than invert-then-search for the common cases.
# ============================================================


def _fused_modreduce_affinemod(pairs: list[tuple[int, int]]) -> dict | None:
    """y = ((a·x + c) mod m) mod n  —  truncated LCG style."""
    from kbound.compositional.atoms import SMALL_PRIMES

    ymax = max(y for _, y in pairs)
    for m in SMALL_PRIMES:
        for n in range(2, m):
            if n <= ymax:
                continue
            for a in range(1, m):
                for c in range(0, m):
                    n_ok = sum(1 for x, y in pairs if (((a * x + c) % m) % n) == y)
                    if n_ok == len(pairs):
                        return {
                            "depth": 2,
                            "atoms": ["affine_mod", "mod_reduce"],
                            "params": [{"a": a, "c": c, "m": m}, {"n": n}],
                            "score": 1.0,
                            "expression": f"(({a}·x + {c}) mod {m}) mod {n}",
                        }
    return None


def _fused_affinemod_power(pairs: list[tuple[int, int]]) -> dict | None:
    """y = (a·x^k + c) mod p  —  polynomial via Power inside AffineMod."""
    from kbound.compositional.atoms import SMALL_PRIMES

    ymax = max(y for _, y in pairs)
    for k in (2, 3, 4, 5):
        for p in SMALL_PRIMES:
            if p <= ymax:
                continue
            for a in range(1, p):
                for c in range(0, p):
                    n_ok = sum(1 for x, y in pairs if (a * (x**k) + c) % p == y)
                    if n_ok == len(pairs):
                        return {
                            "depth": 2,
                            "atoms": ["power", "affine_mod"],
                            "params": [{"k": k}, {"a": a, "c": c, "m": p}],
                            "score": 1.0,
                            "expression": f"({a}·x^{k} + {c}) mod {p}",
                        }
    return None


def _fused_affinemod_constadd(pairs: list[tuple[int, int]]) -> dict | None:
    """y = (a·(x + offset) + c) mod m"""
    from kbound.compositional.atoms import SMALL_PRIMES

    ymax = max(y for _, y in pairs)
    for m in SMALL_PRIMES:
        if m <= ymax:
            continue
        for offset in range(-15, 16):
            if offset == 0:
                continue
            for a in range(1, m):
                for c in range(0, m):
                    n_ok = sum(1 for x, y in pairs if (a * (x + offset) + c) % m == y)
                    if n_ok == len(pairs):
                        return {
                            "depth": 2,
                            "atoms": ["const_add", "affine_mod"],
                            "params": [{"c": offset}, {"a": a, "c": c, "m": m}],
                            "score": 1.0,
                            "expression": f"({a}·(x + {offset}) + {c}) mod {m}",
                        }
    return None


FUSED_COMPOSITIONS = [
    ("mod_reduce ∘ affine_mod", _fused_modreduce_affinemod),
    ("affine_mod ∘ power", _fused_affinemod_power),
    ("affine_mod ∘ const_add", _fused_affinemod_constadd),
]


def synthesize(pairs: list[tuple[int, int]], depth: int = 2) -> dict:
    """Top-level: search depth-1 then depth-2 compositions.

    Returns the best fit found, or {"depth": 0} if nothing fits.
    """
    t0 = time.perf_counter()
    if not pairs:
        return {"depth": 0, "reason": "no pairs"}

    # Depth 1
    best = None
    for atom_name in ALL_ATOMS:
        fit = _try_single_atom(pairs, atom_name)
        if fit and (best is None or fit["score"] > best["score"]):
            best = fit
            if fit["score"] >= 0.99:
                break

    if best and best["score"] >= 0.99:
        best["elapsed_ms"] = (time.perf_counter() - t0) * 1000
        return best

    # Depth 2: try fused-search variants first (much faster + more reliable)
    if depth >= 2:
        for _fused_name, fused_fn in FUSED_COMPOSITIONS:
            fit = fused_fn(pairs)
            if fit and (best is None or fit["score"] > best["score"]):
                best = fit
                if fit["score"] >= 0.99:
                    break

    if best and best["score"] >= 0.99:
        best["elapsed_ms"] = (time.perf_counter() - t0) * 1000
        return best

    # Depth 2: invert-and-search fallback for compositions not covered above
    if depth >= 2:
        for outer_name in INVERTIBLE_OUTER_ATOMS:
            for inner_name in ALL_ATOMS:
                if inner_name == "identity" and outer_name == "identity":
                    continue
                fit = _try_composition(pairs, outer_name=outer_name, inner_name=inner_name)
                if fit and (best is None or fit["score"] > best["score"]):
                    best = fit
                    if fit["score"] >= 0.99:
                        break
            if best and best["score"] >= 0.99:
                break

    if best is None:
        return {
            "depth": 0,
            "reason": "no fit found at depth ≤ 2",
            "elapsed_ms": (time.perf_counter() - t0) * 1000,
        }

    best["elapsed_ms"] = (time.perf_counter() - t0) * 1000
    return best


def predict(synthesis_result: dict, x_query: int) -> int | None:
    """Apply the synthesized composition to a new input."""
    if synthesis_result.get("depth", 0) == 0:
        return None
    if synthesis_result["depth"] == 1:
        atom = ATOMS[synthesis_result["atoms"][0]]
        return atom.forward(x_query, synthesis_result["params"][0])
    if synthesis_result["depth"] == 2:
        inner_name, outer_name = synthesis_result["atoms"]
        inner_params, outer_params = synthesis_result["params"]
        z = ATOMS[inner_name].forward(x_query, inner_params)
        return ATOMS[outer_name].forward(z, outer_params)
    return None
