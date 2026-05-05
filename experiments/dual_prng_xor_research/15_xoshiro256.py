"""xoshiro256** state recovery via Z3 SMT.

xoshiro256** (and its sibling xoshiro256++) is the default RNG in:
  - NumPy >= 1.17 (np.random.default_rng) — most ML / scientific Python code
  - Rust's `rand` crate default (StdRng since v0.8)
  - PHP mt_rand replacement candidate
  - .NET Random class (since .NET 6)

The algorithm (Vigna & Blackman 2018):

    state = (s0, s1, s2, s3) — four 64-bit words
    output = rotl(s1 * 5, 7) * 9        (xoshiro256**)
       or = rotl(s0 + s3, 23) + s0       (xoshiro256++)
    next state:
        t = s1 << 17
        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= t
        s3 = rotl(s3, 45)

256-bit state, K=4 outputs gives 256 bits of constraint. Z3 should crack.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, LShR, RotateLeft


N = 64
MASK = (1 << 64) - 1


def rotl_python(x, k, w=64):
    x &= (1 << w) - 1
    return ((x << k) | (x >> (w - k))) & ((1 << w) - 1)


def xoshiro256ss_step(state):
    s0, s1, s2, s3 = state
    output = (rotl_python(s1 * 5 & MASK, 7) * 9) & MASK
    t = (s1 << 17) & MASK
    s2 ^= s0
    s3 ^= s1
    s1 ^= s2
    s0 ^= s3
    s2 ^= t
    s3 = rotl_python(s3, 45)
    return (s0, s1, s2, s3), output


def gen_xoshiro256ss(seed_state, n):
    state = tuple(seed_state)
    outs = []
    for _ in range(n):
        state, o = xoshiro256ss_step(state)
        outs.append(o)
    return outs


def attack_xoshiro256ss(out_seq, timeout_s=120):
    K = len(out_seq)
    s = Solver()
    s.set("timeout", timeout_s * 1000)

    # State word vars at each step
    s0 = [BitVec(f"s0_{k}", N) for k in range(K + 1)]
    s1 = [BitVec(f"s1_{k}", N) for k in range(K + 1)]
    s2 = [BitVec(f"s2_{k}", N) for k in range(K + 1)]
    s3 = [BitVec(f"s3_{k}", N) for k in range(K + 1)]

    for k in range(K):
        # Output: rotl(s1[k] * 5, 7) * 9
        out_z3 = RotateLeft(s1[k] * 5, 7) * 9
        s.add(out_z3 == BitVecVal(out_seq[k], N))

        # State transition
        t = s1[k] << 17
        new_s2_pre = s2[k] ^ s0[k]
        new_s3_pre = s3[k] ^ s1[k]
        new_s1 = s1[k] ^ new_s2_pre
        new_s0 = s0[k] ^ new_s3_pre
        new_s2 = new_s2_pre ^ t
        new_s3 = RotateLeft(new_s3_pre, 45)

        s.add(s0[k + 1] == new_s0)
        s.add(s1[k + 1] == new_s1)
        s.add(s2[k + 1] == new_s2)
        s.add(s3[k + 1] == new_s3)

    t0 = time.time()
    res = s.check()
    elapsed = time.time() - t0
    if res != sat:
        return {"status": str(res), "elapsed_s": elapsed}
    m = s.model()
    return {
        "status": "sat",
        "elapsed_s": elapsed,
        "s0": m[s0[0]].as_long(),
        "s1": m[s1[0]].as_long(),
        "s2": m[s2[0]].as_long(),
        "s3": m[s3[0]].as_long(),
    }


# Test
SEED = (0xDEADBEEFCAFEBABE, 0x0123456789ABCDEF, 0xFEEDFACEDEADC0DE, 0xBAADF00DBAADBEEF)
print(f"True state: s0={hex(SEED[0])}, s1={hex(SEED[1])}, s2={hex(SEED[2])}, s3={hex(SEED[3])}")

for K in [4, 5, 6, 8, 12, 16]:
    outs = gen_xoshiro256ss(SEED, K + 5)
    observed = outs[:K]
    future = outs[K:K + 5]
    print(f"\n=== K={K} observations ===")
    res = attack_xoshiro256ss(observed, timeout_s=120)
    if res["status"] != "sat":
        print(f"  status: {res['status']}, elapsed: {res['elapsed_s']:.2f}s")
        continue
    print(f"  recovered: s0={hex(res['s0'])}, s1={hex(res['s1'])}, s2={hex(res['s2'])}, s3={hex(res['s3'])}")
    print(f"  elapsed: {res['elapsed_s']:.2f}s")
    pred = gen_xoshiro256ss((res["s0"], res["s1"], res["s2"], res["s3"]), K + 5)
    obs_match = pred[:K] == observed
    fut_match = pred[K:K + 5] == future
    print(f"  observed: {'✓' if obs_match else '✗'}, future: {'✓ FULL CRACK' if fut_match else '✗ ambiguous'}")
    if obs_match and fut_match:
        print(f"\n  Minimum K for full crack: {K}")
        break
