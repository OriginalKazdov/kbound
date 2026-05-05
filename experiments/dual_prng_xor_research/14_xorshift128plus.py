"""xorshift128+ state recovery via Z3 SMT.

xorshift128+ is the algorithm behind Math.random() in V8 (Node.js, Chrome),
Safari (JSC), Firefox (SpiderMonkey 2015-2018), Rust's `rand_xoshiro::Xorshift128Plus`,
and many other JS/Rust environments. Real-world impact: every browser app's
client-side "random" choices, A/B test bucketings, Math.random()-derived
session IDs, etc.

The algorithm (Vigna 2014, "Further scramblings of Marsaglia's xorshift"):

    state = (s0, s1) — two 64-bit words
    next state:
        s1' = s0
        s0' = s1
        s0' ^= s0' << 23
        s0' ^= s0' >> 17
        s0' ^= s1' ^ (s1' >> 26)
        new_state = (s0', s1')
    output = (s0 + s1) mod 2^64    # before the state update? or after? Vigna: s0+s1 of NEW state

Note: V8 specifically uses xorshift128+ but caches a POOL of 64 outputs and
serves them in REVERSE order, so a direct attack on consecutive Math.random()
calls needs to invert that order. We attack the underlying generator first.

References:
  - Vigna 2014 "Further scramblings": https://arxiv.org/abs/1404.0390
  - V8 blog: https://v8.dev/blog/math-random
  - d0nutptr/v8_rand_buster (textbook V8 attack via Z3)
  - Goddard "Hacking the JS Lottery": uses Z3 directly
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT, LShR


N = 64
MASK = (1 << 64) - 1


def xorshift128plus_step(s0: int, s1: int) -> tuple[int, int]:
    """One step of xorshift128+. Returns (new_s0, new_s1, output)."""
    # Per Vigna: t = s0; s = s1; s1' = s; s0' = ... using t and s
    # Actual implementation (from the canonical reference):
    s1, s0 = s0, s1  # rotate
    s0 ^= (s0 << 23) & MASK
    s0 ^= (s0 >> 17)
    s0 ^= s1 ^ (s1 >> 26)
    return s0, s1


def xorshift128plus_output(s0: int, s1: int) -> int:
    """Output is s0 + s1 mod 2^64 of the NEW state (after step)."""
    return (s0 + s1) & MASK


def gen_xorshift128plus(seed_s0: int, seed_s1: int, n: int) -> list[int]:
    """Generate n consecutive xorshift128+ outputs from a starting state."""
    s0, s1 = seed_s0, seed_s1
    outs = []
    for _ in range(n):
        s0, s1 = xorshift128plus_step(s0, s1)
        outs.append(xorshift128plus_output(s0, s1))
    return outs


def attack_xorshift128plus(out_seq: list[int], timeout_s: int = 60) -> dict | None:
    K = len(out_seq)
    s = Solver()
    s.set("timeout", timeout_s * 1000)

    s0 = [BitVec(f"s0_{k}", N) for k in range(K + 1)]
    s1 = [BitVec(f"s1_{k}", N) for k in range(K + 1)]

    for k in range(K):
        # State transition: rotate-then-mix
        new_s1 = s0[k]               # = old s0
        t = s1[k]                    # = old s1, will become new s0
        t = t ^ (t << 23)
        t = t ^ LShR(t, 17)
        t = t ^ new_s1 ^ LShR(new_s1, 26)
        # new_s0 = t
        s.add(s0[k + 1] == t)
        s.add(s1[k + 1] == new_s1)
        # Output constraint: out[k] = (new_s0 + new_s1) mod 2^64
        s.add(s0[k + 1] + s1[k + 1] == BitVecVal(out_seq[k], N))

    t0 = time.time()
    res = s.check()
    elapsed = time.time() - t0
    if res != sat:
        return {"status": str(res), "elapsed_s": elapsed}
    m = s.model()
    return {
        "status": "sat",
        "elapsed_s": elapsed,
        "s0_initial": m[s0[0]].as_long(),
        "s1_initial": m[s1[0]].as_long(),
    }


# Test
SEED_S0 = 0xDEADBEEFCAFEBABE
SEED_S1 = 0x0123456789ABCDEF

# Need few outputs — xorshift128+ has 128-bit state, K=4 outputs gives 256 bits constraint
print(f"True initial state: s0={hex(SEED_S0)}, s1={hex(SEED_S1)}")

for K in [3, 4, 5, 8, 16]:
    outs = gen_xorshift128plus(SEED_S0, SEED_S1, K + 5)
    observed = outs[:K]
    future_truth = outs[K:K + 5]
    print(f"\n=== K={K} observations ===")
    res = attack_xorshift128plus(observed, timeout_s=120)
    if res["status"] != "sat":
        print(f"  status: {res['status']}, elapsed: {res['elapsed_s']:.2f}s")
        continue
    print(f"  recovered: s0={hex(res['s0_initial'])}, s1={hex(res['s1_initial'])}")
    print(f"  elapsed: {res['elapsed_s']:.2f}s")
    # Verify
    pred = gen_xorshift128plus(res["s0_initial"], res["s1_initial"], K + 5)
    obs_match = pred[:K] == observed
    fut_match = pred[K:K + 5] == future_truth
    print(f"  observed match: {'✓' if obs_match else '✗'}")
    print(f"  future predict: {'✓ FULL CRACK' if fut_match else '✗ ambiguous'}")
    if obs_match and fut_match:
        # Stop at first success
        print(f"\n  Minimum K for unique recovery: {K}")
        break
