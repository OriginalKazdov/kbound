"""RCE-Java — recover state of Java's java.util.Random.

The default PRNG in Java / Kotlin / Android. Behind every Minecraft world seed,
many Android app session tokens, and a long tail of server-side Java code.

    seed = (seed * 0x5DEECE66D + 0xB) & ((1 << 48) - 1)

Output methods:
    nextInt():        returns top 32 bits of the new seed (signed int)
    nextInt(n):       calls next(31) (top 31 bits) and reduces mod n
    nextLong():       two next(32) calls combined
    nextBoolean():    next(1) (top bit)

Recovery (Minecraft-style attack):
    Given two consecutive next(32) outputs (y_0, y_1):
        seed_0 = (high16 || y_0)   for some 16-bit high16 (unknown)
        seed_1 = step(seed_0)      = (a * seed_0 + b) & 0xFFFFFFFFFFFF
        next(32) of seed_1 == y_1  i.e. seed_1 >> 16 == y_1

    Brute-force high16 (2^16 candidates), check seed_1 >> 16 == y_1.

This is the canonical "Minecraft seed crack" — works in well under a second.
"""

from __future__ import annotations

JAVA_A = 0x5DEECE66D
JAVA_B = 0xB
JAVA_M = 1 << 48
JAVA_MASK = JAVA_M - 1


def _step(seed: int) -> int:
    return (JAVA_A * seed + JAVA_B) & JAVA_MASK


def _next32(seed: int) -> int:
    """Java's next(32): returns top 32 bits of the *new* seed as signed int."""
    new_seed = _step(seed)
    val = new_seed >> 16
    # Convert to signed 32-bit
    if val >= (1 << 31):
        val -= 1 << 32
    return val


def _next32_unsigned(seed: int) -> int:
    """Top 32 bits of new seed, unsigned (for raw observation)."""
    return _step(seed) >> 16


def solve_java(examples: list[tuple], query) -> dict:
    """Recover the java.util.Random state from K >= 2 consecutive next(32) outputs.

    Accepts both signed (Java int) and unsigned 32-bit observations — auto-detects
    by checking if any output is negative.
    """
    if len(examples) < 2:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "need at least 2 consecutive outputs",
            "details": {},
        }

    sorted_ex = sorted(examples, key=lambda e: e[0])
    xs = [int(e[0]) for e in sorted_ex]
    ys = [int(e[1]) for e in sorted_ex]

    # Detect signed vs unsigned encoding
    has_negative = any(y < 0 for y in ys)
    if has_negative:
        ys_unsigned = [y + (1 << 32) if y < 0 else y for y in ys]
    else:
        ys_unsigned = ys

    # Need consecutive observations
    if not all(xs[i + 1] - xs[i] == 1 for i in range(len(xs) - 1)):
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "need consecutive call indices",
            "details": {},
        }

    # Each y is the top 32 bits of a 48-bit state. Need to brute-force the missing 16 low bits.
    # Strategy: for the seed *that produced y_0* (call it seed_1, since next() steps first),
    # we have seed_1 >> 16 == ys_unsigned[0]. Brute-force the low 16 bits of seed_1.
    y0 = ys_unsigned[0]
    found_seed_after_first_call = None
    for low16 in range(1 << 16):
        seed_1 = (y0 << 16) | low16
        # Now verify subsequent observations match by stepping
        cur = seed_1
        ok = True
        for i in range(1, len(ys_unsigned)):
            cur = _step(cur)
            if (cur >> 16) != ys_unsigned[i]:
                ok = False
                break
        if ok:
            found_seed_after_first_call = seed_1
            break

    if found_seed_after_first_call is None:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "no java.util.Random state matches observations",
            "details": {},
        }

    # Project forward to query call index.
    # found_seed_after_first_call is the state that PRODUCED ys[0] (i.e. state at
    # call index xs[0]). To produce ys at call index `target`, step `target - xs[0]`
    # times from this state.
    target_idx = int(query)
    if target_idx < xs[0]:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "query index < first observed",
            "details": {},
        }
    cur = found_seed_after_first_call
    steps_to_advance = target_idx - xs[0]
    for _ in range(steps_to_advance):
        cur = _step(cur)

    out_unsigned = cur >> 16
    if has_negative:
        out_signed = out_unsigned - (1 << 32) if out_unsigned >= (1 << 31) else out_unsigned
        out = out_signed
    else:
        out = out_unsigned

    return {
        "predicted_y": out,
        "consistency_score": 1.0,
        "a": JAVA_A,
        "b": JAVA_B,
        "m": JAVA_M,
        "details": {
            "recovered_state_low16": found_seed_after_first_call & 0xFFFF,
            "encoding": "signed" if has_negative else "unsigned",
        },
    }
