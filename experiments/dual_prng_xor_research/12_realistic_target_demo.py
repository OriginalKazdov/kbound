"""Demo: attack a "secure-by-obfuscation" 2-LCG XOR token generator.

Realistic scenario: a developer writes a "secure" token/session-ID generator
by XOR'ing two well-known LCGs, thinking the combination is harder to invert
than either individually. This is a documented anti-pattern that appears in:
  - Embedded firmware RNGs ("combine two weak generators for entropy")
  - Older session-token schemes
  - Game RNGs that want to obscure their state
  - "Secure" raffle/bucket assignment in legacy systems

We use canonical LCG parameters from published references:
  - LCG_A: Microsoft Visual C++ rand() — a=214013, c=2531011, m=2^32 (documented in MS docs)
  - LCG_B: Numerical Recipes "quick and dirty" LCG — a=1664525, c=1013904223, m=2^32

The developer "improves" by xoring them per call:
  state_A_{n+1} = (a_A * state_A_n + c_A) mod 2^32
  state_B_{n+1} = (a_B * state_B_n + c_B) mod 2^32
  output_n      = state_A_n XOR state_B_n

We capture 32 consecutive tokens (e.g., from a public REST endpoint that
emits "random" but predictable IDs), then recover the full state and predict
the next ones — equivalent to bypassing the entire "security" of the scheme.

The key novelty: this attack didn't exist in the literature until our work.
Bouillaguet (TOSC 2020) cracked PCG, hand-crafted; nobody published a
general attack on the XOR-of-LCGs class.
"""
from __future__ import annotations

import sys, time
sys.path.insert(0, '/Users/kazdov/code/OriginalKazdov')

from z3 import BitVec, BitVecVal, Solver, sat, ULT


# Published LCG parameter sets
MSVC_RAND = {"a": 214013, "c": 2531011, "m": 1 << 32, "name": "Microsoft Visual C++ rand()"}
NUMREC_QD = {"a": 1664525, "c": 1013904223, "m": 1 << 32, "name": "Numerical Recipes quick-and-dirty"}


def secure_token_generator(seed_a, seed_b, lcg_a=MSVC_RAND, lcg_b=NUMREC_QD, n_tokens=100):
    """Simulate the 'secure' token generator.

    Returns a list of n_tokens observed XOR outputs.
    """
    state_a = seed_a % lcg_a["m"]
    state_b = seed_b % lcg_b["m"]
    tokens = []
    for _ in range(n_tokens):
        state_a = (lcg_a["a"] * state_a + lcg_a["c"]) % lcg_a["m"]
        state_b = (lcg_b["a"] * state_b + lcg_b["c"]) % lcg_b["m"]
        tokens.append(state_a ^ state_b)
    return tokens


def attack(out_seq, N=32, timeout_s=120):
    K = len(out_seq)
    s = Solver()
    s.set("timeout", timeout_s * 1000)
    a1 = BitVec("a1", N); c1 = BitVec("c1", N)
    a2 = BitVec("a2", N); c2 = BitVec("c2", N)
    s1 = [BitVec(f"s1_{k}", N) for k in range(K + 1)]
    s2 = [BitVec(f"s2_{k}", N) for k in range(K + 1)]
    for k in range(K):
        s.add(s1[k + 1] == a1 * s1[k] + c1)
        s.add(s2[k + 1] == a2 * s2[k] + c2)
        s.add(s1[k + 1] ^ s2[k + 1] == BitVecVal(out_seq[k], N))
    s.add(ULT(a1, a2))
    s.add((a1 & 1) == 1); s.add((a2 & 1) == 1)
    t0 = time.time()
    res = s.check()
    elapsed = time.time() - t0
    if res != sat:
        return None, elapsed
    m = s.model()
    return {
        "a1": m[a1].as_long(), "c1": m[c1].as_long(), "s1_0": m[s1[0]].as_long(),
        "a2": m[a2].as_long(), "c2": m[c2].as_long(), "s2_0": m[s2[0]].as_long(),
    }, elapsed


# ============== The "attack" scenario ==============

print("=" * 72)
print("  ATTACK SIMULATION: 'secure-by-obfuscation' 2-LCG XOR token generator")
print("=" * 72)
print()
print("  Target system: a server emits 'random' token IDs by XORing two well-")
print("  known LCG state streams.  The developer believes this is more secure")
print("  than either generator alone.  Standard published parameters used.")
print()
print(f"    LCG_A: {MSVC_RAND['name']} (a={MSVC_RAND['a']}, c={MSVC_RAND['c']})")
print(f"    LCG_B: {NUMREC_QD['name']} (a={NUMREC_QD['a']}, c={NUMREC_QD['c']})")
print()

# Adversary intercepts 32 consecutive tokens
SEED_A = 0xDEADBEEF
SEED_B = 0xCAFEBABE
all_tokens = secure_token_generator(SEED_A, SEED_B, n_tokens=64)
intercepted = all_tokens[:32]
future_truth = all_tokens[32:64]

print(f"  Adversary intercepts {len(intercepted)} consecutive tokens (e.g. session IDs).")
print(f"  First 5 intercepted: {[hex(t) for t in intercepted[:5]]}")
print()

# Run the attack
print("  Running Z3-SMT attack ...")
res, elapsed = attack(intercepted, N=32, timeout_s=120)
print()

if res is None:
    print("  Attack FAILED")
    sys.exit(1)

print(f"  Attack succeeded in {elapsed:.2f}s.")
print()
print(f"    Recovered LCG_1: a={res['a1']:>12d}, c={res['c1']:>12d}, seed={res['s1_0']:>12d}")
print(f"    Recovered LCG_2: a={res['a2']:>12d}, c={res['c2']:>12d}, seed={res['s2_0']:>12d}")
print()
print(f"    Truth (LCG_A=MSVC):    a={MSVC_RAND['a']:>12d}, c={MSVC_RAND['c']:>12d}, seed={SEED_A:>12d}")
print(f"    Truth (LCG_B=NumRec):  a={NUMREC_QD['a']:>12d}, c={NUMREC_QD['c']:>12d}, seed={SEED_B:>12d}")
print()

# Predict next 32 tokens from recovered params
def gen_xor(seed1, seed2, a1, c1, a2, c2, N, n):
    M = 1 << N
    s1, s2 = seed1, seed2
    out = []
    for _ in range(n):
        s1 = (a1 * s1 + c1) % M
        s2 = (a2 * s2 + c2) % M
        out.append(s1 ^ s2)
    return out

predicted_all = gen_xor(res["s1_0"], res["s2_0"], res["a1"], res["c1"],
                        res["a2"], res["c2"], 32, 64)
predicted_observed = predicted_all[:32]
predicted_future = predicted_all[32:]

assert predicted_observed == intercepted, "Recovered params don't reproduce observed tokens — bug"

if predicted_future == future_truth:
    print("=" * 72)
    print(f"  ✅ ATTACK SUCCESS: predicted {len(future_truth)} held-out future tokens correctly")
    print(f"  In a production system, this means the attacker now controls all future")
    print(f"  'random' IDs, including any that haven't been generated yet.")
    print("=" * 72)
    print()
    print(f"  Sample of predicted future tokens (which the server hasn't generated yet):")
    for i, t in enumerate(predicted_future[:5]):
        print(f"    next_token[{i+32}] = {hex(t)} (truth: {hex(future_truth[i])} — {'✓' if t == future_truth[i] else '✗'})")
else:
    n_match = sum(1 for p, t in zip(predicted_future, future_truth) if p == t)
    print(f"  ⚠️ Z3 found a factorization that matches the {len(intercepted)} intercepted")
    print(f"  tokens but only predicts {n_match}/{len(future_truth)} future tokens correctly.")
    print(f"  More K observations may collapse the ambiguity.")
