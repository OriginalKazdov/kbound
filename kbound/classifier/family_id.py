"""Family identifier — classifies algebraic subfamily.

Given a task already classified as algebraic, identify the specific family:
  - lcg          : y = (a*x + c) mod m         (single-input small-m LCG)
  - polycoef     : y = (a*x^2 + b*x + c) mod p (polynomial coefficient recovery)
  - mod_p_add    : y = (x_i + x_j) mod p       (modular addition, 2-input)
  - glibc        : the canonical glibc rand() LCG (m=2^31)
  - java_random  : java.util.Random LCG (m=2^48, top-32-bit truncation)
  - mt19937      : Mersenne Twister (Python random, PHP mt_rand, etc.)
  - boolean_2input / parity_kbit / recurrence_*
  - unknown      : algebraic but family not identified

For v0 we use heuristic detection. Future: train a meta-classifier.
"""

from __future__ import annotations


def _to_vec(x):
    if isinstance(x, (int, float)):
        return [int(x)]
    return [int(v) for v in x]


def _try_fit_lcg(xs: list[int], ys: list[int], max_m: int = 200) -> tuple[bool, dict]:
    """Try to fit y = (a*x + c) mod m for small m. Returns (matched, params).

    Note: m only constrains ys (since ys are mod m), not xs.
    """
    if len(set(ys)) < 2:
        return False, {}
    K = len(xs)
    best = (0.0, None)
    # m must be > max(ys), but xs can be larger
    y_max = max(ys)
    for m in range(max(2, y_max + 1), max_m):
        for a in range(1, m):
            for c in range(0, m):
                preds = [(a * x + c) % m for x in xs]
                acc = sum(p == y for p, y in zip(preds, ys, strict=False)) / K
                if acc > best[0]:
                    best = (acc, {"a": a, "c": c, "m": m})
                    if acc > 0.95:
                        return True, best[1]
            if best[0] > 0.95:
                break
        if best[0] > 0.95:
            break
    if best[0] > 0.85:
        return True, best[1]
    return False, {}


def identify_family(examples: list[tuple], geom_result: dict) -> str:
    """Identify algebraic subfamily."""
    xs_raw = [e[0] for e in examples]
    ys = [int(e[1]) for e in examples]
    features = geom_result.get("features", {})

    arity = features.get("input_arity", 1)

    # 2-input cases
    if arity == 2:
        # Boolean (binary inputs / outputs only)
        all_binary = all(int(b) in (0, 1) for x in xs_raw for b in x) and all(
            int(y) in (0, 1) for y in ys
        )
        if all_binary:
            from kbound.solvers.rce_boolean import solve_boolean_2input

            bool_result = solve_boolean_2input(list(zip(xs_raw, ys, strict=False)), query=(0, 0))
            if bool_result.get("consistency_score", 0) > 0.95:
                return "boolean_2input"

        # Check for modular addition: y = (x1 + x2) mod p for some p
        for p in range(2, 30):
            preds = [(x[0] + x[1]) % p for x in xs_raw]
            acc = sum(pp == y for pp, y in zip(preds, ys, strict=False)) / len(ys)
            if acc > 0.85:
                return "mod_p_add"
        return "unknown_2input"

    # K-bit input (parity check)
    if arity > 2:
        all_binary = all(int(b) in (0, 1) for x in xs_raw for b in x) and all(
            int(y) in (0, 1) for y in ys
        )
        if all_binary:
            from kbound.solvers.rce_boolean import solve_parity_kbit

            par_result = solve_parity_kbit(list(zip(xs_raw, ys, strict=False)), query=xs_raw[0])
            if par_result.get("consistency_score", 0) > 0.95:
                return "parity_kbit"

    # NOTE: Recurrence check moved AFTER more specific algebraic detectors below.
    # Exponential sequences and modular sequences satisfy SOME linear recurrence,
    # so we want to detect their simpler primitive structure first.

    # 1-input cases
    xs = [_to_vec(x)[0] for x in xs_raw]

    # === Well-known PRNG detection (large moduli) — try BEFORE small-m fallback ===
    # These check the canonical fixed parameters of widely-deployed PRNGs.

    # MT19937 — only meaningful if K >= 624 consecutive 32-bit outputs
    if (
        len(xs) >= 624
        and all(0 <= int(y) < (1 << 32) for y in ys)
        and len(set(xs)) == len(xs)
        and all(xs[i + 1] - xs[i] == 1 for i in range(len(xs) - 1))
    ):
        from kbound.solvers.rce_mt19937 import solve_mt19937

        mt_result = solve_mt19937(list(zip(xs, ys, strict=False)), query=xs[-1] + 1)
        if mt_result.get("consistency_score", 0) > 0.95:
            return "mt19937"

    # glibc rand() — outputs in [0, 2^31), consecutive seed-step matches
    if all(0 <= int(y) < (1 << 31) for y in ys) and any(
        int(y) >= (1 << 16) for y in ys
    ):  # at least one large value to disambiguate
        from kbound.solvers.rce_glibc import solve_glibc

        glibc_result = solve_glibc(list(zip(xs, ys, strict=False)), query=xs[-1] + 1)
        if (
            glibc_result.get("consistency_score", 0) > 0.95
            and glibc_result.get("form") == "A_raw_seed"
        ):
            return "glibc"

    # Java Random — 32-bit (signed or unsigned) outputs, brute-force 2^16 low bits
    if (
        len(xs) >= 3
        and len(set(xs)) == len(xs)
        and all(xs[i + 1] - xs[i] == 1 for i in range(len(xs) - 1))
        and all(-(1 << 31) <= int(y) < (1 << 32) for y in ys)
        and any(abs(int(y)) >= (1 << 24) for y in ys)
    ):  # 24-bit threshold avoids false positives on tiny LCGs
        from kbound.solvers.rce_java import solve_java

        java_result = solve_java(list(zip(xs, ys, strict=False)), query=xs[-1] + 1)
        if java_result.get("consistency_score", 0) > 0.95:
            return "java_random"

    # glibc rand() Form B (windowed 15-bit) — only fires if no other family matches
    if (
        len(xs) >= 4
        and len(set(xs)) == len(xs)
        and all(xs[i + 1] - xs[i] == 1 for i in range(len(xs) - 1))
        and all(0 <= int(y) < (1 << 15) for y in ys)
    ):
        from kbound.solvers.rce_glibc import solve_glibc

        glibc_result = solve_glibc(list(zip(xs, ys, strict=False)), query=xs[-1] + 1)
        if (
            glibc_result.get("consistency_score", 0) > 0.95
            and glibc_result.get("form") == "B_windowed_15bit"
        ):
            return "glibc_windowed"

    # glibc TGFSR (TYPE_3, additive feedback shift register) — the post-glibc-2.0 default.
    # Recurrence v_k = v_{k-31} + v_{k-3} mod 2^32, output = v_k >> 1. Cracked via
    # LSB-recovery + GF(2) Gaussian elimination. Needs K >= ~63 consecutive outputs;
    # 100+ for reliable rank-31 recovery.
    if (
        len(xs) >= 63
        and len(set(xs)) == len(xs)
        and all(xs[i + 1] - xs[i] == 1 for i in range(len(xs) - 1))
        and all(0 <= int(y) < (1 << 31) for y in ys)
    ):
        from kbound.solvers.rce_glibc_tgfsr import solve_glibc_tgfsr

        tgfsr_result = solve_glibc_tgfsr(list(zip(xs, ys, strict=False)), query=xs[-1] + 1)
        if tgfsr_result.get("consistency_score", 0) > 0.95:
            return "glibc_tgfsr"

    # === Standard algebraic family checks ===

    # ModInv (cheap to check) — y = x^(-1) mod p, so x*y ≡ 1
    from kbound.solvers.rce_modinv import solve_modinv_symbolic

    modinv_result = solve_modinv_symbolic(list(zip(xs, ys, strict=False)), query=xs[0])
    if modinv_result.get("consistency_score", 0) > 0.85:
        return "modinv"

    # ModMul — try y = (a*x) mod p (LCG with c=0 is special case; handled here too)
    from kbound.solvers.rce_modmul import solve_modmul_symbolic

    modmul_result = solve_modmul_symbolic(list(zip(xs, ys, strict=False)), query=xs[0])
    if modmul_result.get("consistency_score", 0) > 0.95:
        # Only claim modmul if PERFECT — LCG with c≠0 will partially fit
        return "modmul"

    # ModExp — y = a^x mod p
    from kbound.solvers.rce_modexp import solve_modexp_symbolic

    modexp_result = solve_modexp_symbolic(list(zip(xs, ys, strict=False)), query=xs[0])
    if modexp_result.get("consistency_score", 0) > 0.85:
        return "modexp"

    # Small-modulus LCG (FUNCTION FORM) — y = (a·x + c) mod m for m ≤ ~200.
    # Runs BEFORE the Boyar attack so users who pass `[(i, f(i))]` get back
    # the function form `(a, c, m)` rather than the operationally-equivalent
    # state-machine recovery Boyar gives. Boyar still fires for large m
    # (where this small-modulus search fails) right below.
    matched, _ = _try_fit_lcg(xs, ys)
    if matched:
        return "lcg"

    # Generic LCG (Boyar 1989) — recover (a, c, m) from K >= 6 consecutive outputs.
    # Fallback for large moduli the small-modulus search above cannot reach: NumRec
    # mod 2^32, custom 32/64-bit generators, leaked random IDs, etc. When inputs
    # are consecutive call indices and outputs are LCG-state-shaped, this returns
    # the state-machine form (a=1, c=step) — operationally equivalent to the
    # function form on the support but different on extrapolation.
    if (
        len(xs) >= 6
        and len(set(xs)) == len(xs)
        and all(xs[i + 1] - xs[i] == 1 for i in range(len(xs) - 1))
    ):
        from kbound.solvers.rce_lcg_generic import solve_lcg_generic

        lcg_g_result = solve_lcg_generic(list(zip(xs, ys, strict=False)), query=xs[-1] + 1)
        if lcg_g_result.get("consistency_score", 0) > 0.95:
            return "lcg_generic"

    # Polycoef check — try (a*x² + b*x + c) mod p
    from kbound.solvers.rce_polycoef import solve_polycoef_symbolic

    poly_result = solve_polycoef_symbolic(list(zip(xs, ys, strict=False)), query=xs[0])
    if poly_result.get("consistency_score", 0) > 0.85:
        return "polycoef"

    # Cubic check — try (a·x³ + b·x² + c·x + d) mod p (MiMC starter / AO primitives)
    if len(xs) >= 4:
        from kbound.solvers.rce_cubic import solve_cubic_symbolic

        cubic_result = solve_cubic_symbolic(list(zip(xs, ys, strict=False)), query=xs[0])
        if cubic_result.get("consistency_score", 0) > 0.95:  # higher bar — cubic over-fits easily
            return "cubic"

    # Generic polynomial (Vandermonde-determinant-gcd) — recover unknown-modulus
    # quadratic or cubic from K >= degree+2 points. Catches mod 100003+, mod 2^32+,
    # bespoke big-prime polynomials. Runs after small-mod checks so we still surface
    # the cheap path when applicable.
    if len(xs) >= 4:
        from kbound.solvers.rce_polycoef_generic import solve_polycoef_generic

        poly_g_result = solve_polycoef_generic(list(zip(xs, ys, strict=False)), query=xs[0])
        if poly_g_result.get("consistency_score", 0) > 0.95:
            return "polycoef_generic"

    # Recurrence check (last resort — fits any linear-recurrence sequence including
    # exponentials, but those are caught earlier as more specific families)
    x_min, x_max = min(xs), max(xs)
    looks_like_positions = (x_max - x_min < 50) and (len(set(xs)) == len(xs))
    if looks_like_positions:
        from kbound.solvers.rce_recurrence import solve_recurrence_symbolic

        rec_result = solve_recurrence_symbolic(
            list(zip(xs, ys, strict=False)), query=xs[0], fibonacci_only=True
        )
        if rec_result.get("consistency_score", 0) > 0.85:
            return "recurrence_fib"
        rec_result = solve_recurrence_symbolic(
            list(zip(xs, ys, strict=False)), query=xs[0], fibonacci_only=False
        )
        if rec_result.get("consistency_score", 0) > 0.85:
            return "recurrence_linear"

    # Generic linear recurrence (Hankel-det-gcd) — recover unknown-modulus order-2 or
    # order-3 recurrence from K >= 5 (or 7) consecutive position-value pairs. Catches
    # large-modulus cases the small-prime brute force above can't reach.
    consecutive = (
        len(xs) >= 5
        and len(set(xs)) == len(xs)
        and all(xs[i + 1] - xs[i] == 1 for i in range(len(xs) - 1))
    )
    if consecutive:
        from kbound.solvers.rce_recurrence_generic import solve_recurrence_generic

        rec_g_result = solve_recurrence_generic(list(zip(xs, ys, strict=False)), query=xs[-1] + 1)
        if rec_g_result.get("consistency_score", 0) > 0.95:
            return "recurrence_generic"

    # Default
    return "unknown"
