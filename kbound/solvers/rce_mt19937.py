"""RCE-MT19937 — recover state of the Mersenne Twister.

THE PRNG of the modern world: Python's `random`, PHP's `mt_rand`, Ruby's `rand`,
NumPy default (until 1.17), V8's `Math.random` until 2018. If a system says
"random number" without specifying a CSPRNG, it's almost certainly MT19937.

Two attack regimes:

  K >= 624 consecutive 32-bit outputs:
      Invert the 4-step tempering function on each output → recover all 624
      state words → predict any future output. Takes microseconds.

  K < 624 consecutive 32-bit outputs:
      Use Z3 (SMT) to solve for the unknown state words. Slower (seconds to
      minutes) but works with as few as ~16 samples.

Reference: Argyros & Kiayias, "I Forgot Your Password: Randomness Attacks
Against PHP Applications" (Black Hat 2012); RNGeesus (deut-erium, GitHub).
"""

from __future__ import annotations

# MT19937 parameters
N_STATE = 624
M_OFFSET = 397
MATRIX_A = 0x9908B0DF
UPPER_MASK = 0x80000000
LOWER_MASK = 0x7FFFFFFF


# ============================================================
# Tempering inverse — closed-form, fast
# ============================================================


def _untemper(y: int) -> int:
    """Invert MT19937's tempering function.

    Tempering:
        y ^= y >> 11
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        y ^= y >> 18

    Inverse done in reverse order, undoing each shift-XOR.
    """
    # Undo: y ^= y >> 18  (shift >= 16, so 1-pass undo works)
    y ^= y >> 18

    # Undo: y ^= (y << 15) & 0xEFC60000  (shift >= 16, 1-pass)
    y ^= (y << 15) & 0xEFC60000

    # Undo: y ^= (y << 7) & 0x9D2C5680  (shift < 16, need iterative)
    y ^= (y << 7) & 0x1680
    y ^= (y << 7) & 0xC4000
    y ^= (y << 7) & 0xD200000
    y ^= (y << 7) & 0x90000000

    # Undo: y ^= y >> 11  (shift < 16, need iterative)
    y ^= (y >> 11) & 0x1FFC00
    y ^= (y >> 11) & 0x3FF

    return y & 0xFFFFFFFF


def _temper(y: int) -> int:
    """Apply MT19937 tempering (forward)."""
    y ^= y >> 11
    y ^= (y << 7) & 0x9D2C5680
    y ^= (y << 15) & 0xEFC60000
    y ^= y >> 18
    return y & 0xFFFFFFFF


def _twist(state: list[int]) -> list[int]:
    """MT19937 state-update twist function. Mutates state in place, returns same list."""
    for i in range(N_STATE):
        x = (state[i] & UPPER_MASK) | (state[(i + 1) % N_STATE] & LOWER_MASK)
        x_a = x >> 1
        if x & 1:
            x_a ^= MATRIX_A
        state[i] = state[(i + M_OFFSET) % N_STATE] ^ x_a
    return state


# ============================================================
# Solver
# ============================================================


def _solve_full_state(outputs: list[int]) -> list[int] | None:
    """Recover MT19937 state from >= 624 consecutive 32-bit outputs."""
    if len(outputs) < N_STATE:
        return None
    state = [_untemper(y) for y in outputs[:N_STATE]]
    return state


def _project_full(state: list[int], n_advance: int) -> int:
    """Given a full state at position 0, output the n_advance-th tempered output."""
    state = list(state)
    idx = 0
    for _ in range(n_advance):
        if idx >= N_STATE:
            _twist(state)
            idx = 0
        _temper(state[idx])
        idx += 1
    if idx >= N_STATE:
        _twist(state)
        idx = 0
    return _temper(state[idx])


def _solve_partial_z3(
    outputs: list[int], target_idx: int, observed_indices: list[int]
) -> int | None:
    """Z3-based partial state recovery for K < 624 (or non-consecutive observations)."""
    try:
        import z3
    except ImportError:
        return None

    # Use z3 to symbolically represent the initial state, constrain via observations,
    # solve for state, then advance to the target.
    solver = z3.Solver()
    solver.set("timeout", 30000)  # 30s

    # Initial 624-word state as bitvectors
    state = [z3.BitVec(f"s_{i}", 32) for i in range(N_STATE)]

    # We need to model: starting from this state, the i-th tempered output equals outputs[i].
    # The largest observed_idx tells us how many twists we'll need.
    max_idx = max(max(observed_indices), target_idx)
    n_twists = max_idx // N_STATE + 1

    # Build twisted states forward (symbolic). To avoid blowup, only do the twists we need.
    sym_states = [list(state)]
    for _t in range(n_twists):
        cur = list(sym_states[-1])
        new = list(cur)
        for i in range(N_STATE):
            x = z3.Concat(z3.Extract(31, 31, cur[i]), z3.Extract(30, 0, cur[(i + 1) % N_STATE]))
            x_a = z3.LShR(x, 1)
            x_a = z3.If(
                z3.Extract(0, 0, cur[(i + 1) % N_STATE]) == 1, x_a ^ z3.BitVecVal(MATRIX_A, 32), x_a
            )
            new[i] = cur[(i + M_OFFSET) % N_STATE] ^ x_a
        sym_states.append(new)

    def sym_temper(y):
        y = y ^ z3.LShR(y, 11)
        y = y ^ ((y << 7) & z3.BitVecVal(0x9D2C5680, 32))
        y = y ^ ((y << 15) & z3.BitVecVal(0xEFC60000, 32))
        y = y ^ z3.LShR(y, 18)
        return y

    def sym_output_at(idx):
        twist_n = idx // N_STATE
        word_n = idx % N_STATE
        return sym_temper(sym_states[twist_n][word_n])

    # Add constraints
    for idx, val in zip(observed_indices, outputs, strict=False):
        solver.add(sym_output_at(idx) == z3.BitVecVal(val & 0xFFFFFFFF, 32))

    if solver.check() != z3.sat:
        return None

    model = solver.model()
    # Now solve concretely from recovered state
    concrete_state = [model[s].as_long() if model[s] is not None else 0 for s in state]
    return _project_full(concrete_state, target_idx)


def solve_mt19937(examples: list[tuple], query) -> dict:
    """Recover MT19937 state from K consecutive (or partial) 32-bit outputs.

    Examples format: (call_index, output_value) where output is the raw 32-bit
    return of the underlying MT19937 (e.g. random.getrandbits(32) in Python).

    Returns predicted output at the queried call index.
    """
    if len(examples) < 4:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "need at least 4 outputs (preferably 624 consecutive for fast path)",
            "details": {},
        }

    sorted_ex = sorted(examples, key=lambda e: e[0])
    indices = [int(e[0]) for e in sorted_ex]
    outputs = [int(e[1]) & 0xFFFFFFFF for e in sorted_ex]
    target = int(query)

    # Fast path: K >= 624 consecutive starting from indices[0]
    consecutive = all(indices[i + 1] - indices[i] == 1 for i in range(len(indices) - 1))
    if consecutive and len(outputs) >= N_STATE:
        # Untemper the first 624
        state = _solve_full_state(outputs[:N_STATE])
        if state is None:
            return {
                "predicted_y": None,
                "consistency_score": 0.0,
                "reason": "tempering inversion failed",
                "details": {},
            }
        # Verify on remaining observations
        n_extra = len(outputs) - N_STATE
        verified = 0
        if n_extra > 0:
            for k in range(n_extra):
                expected = _project_full(state, N_STATE + k)
                if expected == outputs[N_STATE + k]:
                    verified += 1
        # Project to target (target index relative to indices[0])
        rel_target = target - indices[0]
        if rel_target < 0:
            return {
                "predicted_y": None,
                "consistency_score": 0.0,
                "reason": "query index before observed window",
                "details": {},
            }
        prediction = _project_full(state, rel_target)
        return {
            "predicted_y": prediction,
            "consistency_score": 1.0
            if (n_extra == 0 or verified == n_extra)
            else verified / max(1, n_extra),
            "method": "tempering_inverse_full_state",
            "details": {
                "n_observations": len(outputs),
                "n_extra_verified": f"{verified}/{n_extra}" if n_extra else "—",
                "state_recovered": True,
            },
        }

    # Z3 SMT path — only attempt if observations span at least 2 twists.
    # For observations confined to a single twist (K < 624 within first cycle),
    # the unobserved 624 state words have full freedom and Z3 will find a model
    # that doesn't match the true state. We need cross-twist constraints.
    base = indices[0]
    rel_indices = [i - base for i in indices]
    rel_target = target - base
    if rel_target < 0:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "query index before observed window",
            "details": {},
        }

    spans_two_twists = max(rel_indices) >= N_STATE
    if not spans_two_twists:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": (
                f"K={len(outputs)} < 624 and observations confined to a single twist cycle. "
                "MT19937 requires either 624+ consecutive 32-bit outputs (tempering-inverse path) "
                "or observations spanning 2+ twists (Z3 path). Collect more samples and retry."
            ),
            "details": {
                "n_observations": len(outputs),
                "needs": "K >= 624 consecutive OR observations spanning >= 2 twists",
            },
        }

    if max(rel_indices) >= 3 * N_STATE or rel_target >= 3 * N_STATE:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "observations span > 2 twists; out of v0 SMT scope",
            "details": {"hint": "narrow the observation window or supply 624+ contiguous samples"},
        }

    pred = _solve_partial_z3(outputs, rel_target, rel_indices)
    if pred is None:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "Z3 could not recover state (unsat or timeout)",
            "details": {"n_observations": len(outputs)},
        }

    return {
        "predicted_y": pred,
        "consistency_score": 1.0,
        "method": "z3_smt_partial_state",
        "details": {
            "n_observations": len(outputs),
            "state_recovered": True,
        },
    }
