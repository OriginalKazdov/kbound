"""RCE-Glibc — recover seed for the simple glibc rand() LCG.

The classic glibc rand() (TYPE_0, the simple variant): every C/C++ programmer's
default for "give me a random number". A staggering number of CTF challenges,
embedded firmwares, and "quick prototype" servers use this as their RNG.

    seed_{n+1} = (1103515245 * seed_n + 12345) & 0x7FFFFFFF
    output_n   = seed_n  (or seed_n & 0x7FFF in some implementations — see below)

Two observed forms:
    A) raw: rand() returns seed_n directly (range [0, 2^31))
    B) windowed: returns seed_n & 0x7FFF (range [0, 2^15)) — older glibc / many
       embedded libcs

Recovery from K >= 2 *consecutive* outputs:
    Form A: trivial, params known, just verify and predict.
    Form B: brute-force the missing 16 high bits of the seed (2^16 candidates).

Note: modern glibc (>= 2.2) uses TYPE_3, a feedback-shift-register variant. We
do NOT cover that. We cover the canonical "simple LCG" that everyone *thinks*
glibc rand() is.
"""

from __future__ import annotations

GLIBC_A = 1103515245
GLIBC_C = 12345
GLIBC_M = 1 << 31  # 2^31


def _step(seed: int) -> int:
    return (GLIBC_A * seed + GLIBC_C) & (GLIBC_M - 1)


def solve_glibc(examples: list[tuple], query) -> dict:
    """Recover the glibc rand() state from K >= 2 consecutive outputs.

    Inputs are interpreted as call indices (n=0, 1, 2, ...). Outputs are the
    rand() return values at those indices.

    Returns: predicted_y for the query index + recovered (a, c, m) + form.
    """
    if not examples or len(examples) < 2:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "need at least 2 consecutive outputs",
            "details": {},
        }

    # Sort by input (call index) to get consecutive samples
    sorted_ex = sorted(examples, key=lambda e: e[0])
    xs = [int(e[0]) for e in sorted_ex]
    ys = [int(e[1]) for e in sorted_ex]

    # Form A: raw seed output (range [0, 2^31))
    formA_ok = all(0 <= y < GLIBC_M for y in ys)
    if formA_ok:
        # Check: ys[i+1] = step(ys[i]) for indices that are adjacent
        consistent = []
        for i in range(len(xs) - 1):
            if xs[i + 1] - xs[i] != 1:
                continue
            consistent.append(_step(ys[i]) == ys[i + 1])
        if consistent and all(consistent):
            # Project forward to query
            target_idx = int(query)
            cur_idx = xs[-1]
            cur_state = ys[-1]
            steps = target_idx - cur_idx
            if steps < 0:
                # Going backward: not supported in v0 (would need modular inverse)
                return {
                    "predicted_y": None,
                    "consistency_score": 0.0,
                    "reason": "query index < last observed index",
                    "details": {},
                }
            for _ in range(steps):
                cur_state = _step(cur_state)
            return {
                "predicted_y": cur_state,
                "consistency_score": 1.0,
                "form": "A_raw_seed",
                "a": GLIBC_A,
                "c": GLIBC_C,
                "m": GLIBC_M,
                "details": {"form": "A_raw_seed", "n_consistent_steps": len(consistent)},
            }

    # Form B: windowed (output = seed & 0x7FFF, lower 15 bits)
    formB_ok = all(0 <= y < (1 << 15) for y in ys)
    if formB_ok and len(xs) >= 3 and all(xs[i + 1] - xs[i] == 1 for i in range(len(xs) - 1)):
        # Brute force the upper 16 bits of seed_0
        y0_low = ys[0]
        for upper in range(1 << 16):
            seed = (upper << 15) | y0_low
            ok = True
            cur = seed
            for i in range(1, len(xs)):
                cur = _step(cur)
                if (cur & 0x7FFF) != ys[i]:
                    ok = False
                    break
            if ok:
                # Project forward
                target_idx = int(query)
                steps = target_idx - xs[-1]
                if steps < 0:
                    return {
                        "predicted_y": None,
                        "consistency_score": 0.0,
                        "reason": "query index < last observed index",
                        "details": {},
                    }
                for _ in range(steps):
                    cur = _step(cur)
                return {
                    "predicted_y": cur & 0x7FFF,
                    "consistency_score": 1.0,
                    "form": "B_windowed_15bit",
                    "a": GLIBC_A,
                    "c": GLIBC_C,
                    "m": GLIBC_M,
                    "details": {"form": "B_windowed_15bit", "recovered_seed_high": upper},
                }

    return {
        "predicted_y": None,
        "consistency_score": 0.0,
        "reason": "outputs do not match glibc rand() canonical LCG (form A or B)",
        "details": {},
    }
