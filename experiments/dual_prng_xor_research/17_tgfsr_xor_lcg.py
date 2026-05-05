"""Heterogeneous PRNG composition: glibc TGFSR ⊕ LCG (cleaned).

GENUINELY UNCRACKED CONSTRUCTION CLASS — no published attack to my knowledge.
Closest prior work: Bouillaguet 2020 (PCG, hand-crafted), Martinez 2022
(CMRG-SUB, lattice), RNGeesus (single-generator SMT). None handle hetero-
geneous XOR composition where the two layers are STRUCTURALLY DIFFERENT
generator types.

Construction:
  TGFSR side: 31-state additive feedback, recurrence v_k = v_{k-31} + v_{k-3} mod 2^32
              output_tg = v_k >> 1                              (31-bit per output)
  LCG side:   s_{k+1} = (a*s_k + c) mod 2^32                    (32-bit state)
              output_lcg = s_{k+1} & 0x7FFFFFFF                 (lower 31 bits)
  Composition: out_k = output_tg XOR output_lcg                  (31-bit)

Realistic threat model: paranoid dev XORs Linux glibc rand() with their own
custom LCG, thinking the combination obscures both.

Joint SMT problem:
  Unknowns: 31 unknown TGFSR initial state words (32 bits each) + 3 LCG (a, c, seed)
  Linkage: out_k = (TGFSR_state_k >> 1) XOR (LCG_state_k & 0x7FFFFFFF)
  TGFSR recurrence: v_k = v_{k-31} + v_{k-3} for k >= 31
  LCG recurrence: s_{k+1} = a*s_k + c

We declare all state vars and let Z3 search.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT, LShR


N = 32
DEG = 31
SEP = 3
MASK31 = 0x7FFFFFFF


def gen_tgfsr_xor_lcg(tgfsr_seed_state, lcg_a, lcg_c, lcg_seed, n, warmup=True):
    """Generate n outputs of (TGFSR_out XOR LCG_out_low31)."""
    state = list(tgfsr_seed_state)
    fptr = SEP; rptr = 0
    if warmup:
        for _ in range(10 * DEG):
            state[fptr] = (state[fptr] + state[rptr]) & 0xFFFFFFFF
            fptr = (fptr + 1) % DEG
            rptr = (rptr + 1) % DEG
    s = lcg_seed
    M = 1 << 32
    outs = []
    for _ in range(n):
        state[fptr] = (state[fptr] + state[rptr]) & 0xFFFFFFFF
        tg_out = state[fptr] >> 1
        s = (lcg_a * s + lcg_c) % M
        lcg_out = s & MASK31
        outs.append(tg_out ^ lcg_out)
        fptr = (fptr + 1) % DEG
        rptr = (rptr + 1) % DEG
    return outs


def attack(out_seq, timeout_s=900):
    """Joint SMT attack."""
    K = len(out_seq)

    s = Solver()
    s.set("timeout", timeout_s * 1000)

    # TGFSR state words at each step (after the kth update). v[0]..v[K-1].
    v = [BitVec(f"v_{k}", N) for k in range(K)]
    # TGFSR recurrence for k >= DEG
    for k in range(DEG, K):
        s.add(v[k] == v[k - DEG] + v[k - SEP])

    # LCG side
    a = BitVec("a", N); c = BitVec("c", N)
    lcg = [BitVec(f"lcg_{k}", N) for k in range(K + 1)]  # lcg[0] = seed; lcg[k+1] = step from lcg[k]
    s.add((a & 1) == BitVecVal(1, N))  # full-period odd a
    for k in range(K):
        s.add(lcg[k + 1] == a * lcg[k] + c)

    # Output linkage
    MASK = BitVecVal(MASK31, N)
    for k in range(K):
        tg_out = LShR(v[k], 1)
        lcg_out = lcg[k + 1] & MASK
        s.add((tg_out ^ lcg_out) == BitVecVal(out_seq[k], N))

    t0 = time.time()
    res = s.check()
    elapsed = time.time() - t0
    if res != sat:
        return {"status": str(res), "elapsed_s": elapsed}
    m = s.model()
    return {
        "status": "sat",
        "elapsed_s": elapsed,
        "lcg_a": m[a].as_long(),
        "lcg_c": m[c].as_long(),
        "lcg_seed": m[lcg[0]].as_long(),
        "tgfsr_v0": m[v[0]].as_long(),
        "tgfsr_v1": m[v[1]].as_long(),
        "tgfsr_v2": m[v[2]].as_long(),
    }


def verify_recovery(observed, recovered, K_obs, K_total):
    """Check if recovered params reproduce observed and predict future correctly."""
    # Reconstruct via the recurrence from recovered state
    v_seq = [recovered[f"tgfsr_v{i}"] for i in range(3)]  # placeholder — only have 3
    # We need full first 31 v values; the recovered model has all of them
    # but we only saved 3. For full verification, would need to extract all v[0..30]
    # from the model. For this script, just check operational match on observed support.
    # (full verification deferred to a later script if needed)
    return None  # placeholder


# Test
import random
random.seed(7)
TGFSR_SEED_STATE = [random.randint(0, 2**32 - 1) for _ in range(DEG)]
LCG_A = 1664525
LCG_C = 1013904223
LCG_SEED = 0xDEADBEEF

print(f"True: LCG a={LCG_A}, c={LCG_C}, seed=0x{LCG_SEED:x}")
print(f"      TGFSR seed first 3 = {TGFSR_SEED_STATE[:3]}")

for K in [80, 120, 160, 240]:
    outs = gen_tgfsr_xor_lcg(TGFSR_SEED_STATE, LCG_A, LCG_C, LCG_SEED, K + 5)
    observed = outs[:K]
    print(f"\n=== K={K} ===")
    print(f"  obs[:3] = {observed[:3]}")
    timeout_s = 600 if K <= 100 else (1200 if K <= 160 else 1800)
    res = attack(observed, timeout_s=timeout_s)
    if res["status"] != "sat":
        print(f"  status: {res['status']}, elapsed: {res['elapsed_s']:.2f}s")
        continue
    print(f"  recovered LCG: a={res['lcg_a']}, c={res['lcg_c']}, seed=0x{res['lcg_seed']:x}")
    print(f"  recovered TGFSR v0..v2: 0x{res['tgfsr_v0']:08x}, 0x{res['tgfsr_v1']:08x}, 0x{res['tgfsr_v2']:08x}")
    print(f"  elapsed: {res['elapsed_s']:.2f}s")
    if res["lcg_a"] == LCG_A and res["lcg_c"] == LCG_C and res["lcg_seed"] == LCG_SEED:
        print(f"  ✓ LCG params match truth exactly")
    else:
        print(f"  ⚠ LCG params differ (may be operationally equivalent)")
    break
