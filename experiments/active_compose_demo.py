"""Active Compositional Discovery — the killer demo.

Shows: starting with K=2 ambiguous observations of an UNKNOWN COMPOSITION, the
system enumerates consistent compositions, suggests queries to disambiguate,
and converges to a unique composition with a depth-bound certificate.

This is the genuine novel artifact: active query × compositional synthesis.
"""
import time
import sys
sys.path.insert(0, "/Users/kazdov/code/OriginalKazdov")

from kbound.compositional.active_compose import ActiveCompositionSession


def run(name, true_fn, initial_obs, max_iter=8):
    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"{'='*70}")
    print(f"  Initial observations: {initial_obs}")

    t0 = time.perf_counter()
    session = ActiveCompositionSession(initial_obs)
    print(f"  After K={len(initial_obs)}: {session.n_candidates} consistent compositions")
    print(f"     family split: {session.family_distribution()}")
    print(f"     depth-bound cert: max safe depth = {session.cert['max_depth_safe']}")
    if session.candidates and session.n_candidates <= 8:
        print(f"     candidates:")
        for c in session.candidates:
            print(f"       - {repr(c)}")

    for step in range(max_iter):
        if session.is_unique:
            print(f"  ✓ UNIQUE composition recovered after K={len(session.observations)}.")
            print(f"    {repr(session.candidates[0])}")
            break
        if session.is_failed:
            print(f"  ✗ NO compositions remain (over-constrained).")
            break

        s = session.suggest_query()
        x_q = s["suggested_x"]
        if x_q is None:
            print(f"  ⊘ Stuck: no further info gain possible. {s.get('reason')}")
            break
        print(f"  → suggest x={x_q} (info gain {s['info_gain_bits']:.2f} bits, "
              f"split: {len(s['predicted_outcomes'])} outcome buckets)")
        y_q = true_fn(x_q)
        session.add_observation(x_q, y_q)
        print(f"      observed ({x_q}, {y_q}) → {session.n_candidates} candidates")

    elapsed = (time.perf_counter() - t0) * 1000
    print(f"  Total time: {elapsed:.0f}ms, K={len(session.observations)}")


# ============================================================
# Cases that benchmark the system
# ============================================================

# Case 1: simple LCG
run("Simple LCG (sanity)",
    true_fn=lambda x: (3 * x + 2) % 7,
    initial_obs=[(0, 2), (1, 5), (2, 1)])

# Case 2: truncated LCG — depth-2 composition
run("Truncated LCG: ((5x+1) mod 13) mod 4",
    true_fn=lambda x: ((5 * x + 1) % 13) % 4,
    initial_obs=[(0, 1), (1, 2), (2, 3)])

# Case 3: polynomial via Power+Affine
run("Polynomial composition: (2·x² + 3) mod 11",
    true_fn=lambda x: (2 * x * x + 3) % 11,
    initial_obs=[(0, 3), (1, 5), (2, 0)])

# Case 4: XOR + AffineMod (4 params)
run("XOR + Affine: (3·(x ^ 5) + 2) mod 7",
    true_fn=lambda x: (3 * (x ^ 5) + 2) % 7,
    initial_obs=[(0, 3), (1, 5), (2, 0)])

# Case 5: Hard — start with K=2, depth-2 ambiguity
run("HARD: K=2 with depth-2 search",
    true_fn=lambda x: (4 * x + 1) % 13,
    initial_obs=[(0, 1), (5, 8)])

print("\n" + "=" * 70)
print("Summary")
print("=" * 70)
print("""
This demonstrates Active Compositional Discovery: an iterative system that
maintains a posterior over candidate COMPOSITIONS (not just atomic rules) and
selects queries via expected info gain to disambiguate. To my knowledge no
existing tool combines compositional discovery with active query, with a
depth-bound certificate from the K-shot count.

The atoms (affine_mod, mod_reduce, power, etc.) are textbook. The system that
enumerates compositions, maintains posterior, scores queries by info gain over
the composition space, and certifies depth-feasibility from K is — as far as I
have surveyed — new.
""")
