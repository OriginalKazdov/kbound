"""End-to-end audit test of the 3 new PRNG solvers via the live API."""
import json
import urllib.request
import time

API = "http://localhost:8765/internal/explain/text"


def post_explain(text):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(API, data=body,
                                  headers={"content-type": "application/json"},
                                  method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def fmt(text):
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(API, data=body,
                                  headers={"content-type": "application/json"},
                                  method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


# ============================================================
# CASE 1 — Glibc rand() Form A: web app session token RNG
# ============================================================
print("=== CASE 1: Glibc rand() — Form A (raw seed, e.g. weak C session token) ===")
GLIBC_A, GLIBC_C, GLIBC_M = 1103515245, 12345, 1 << 31
seed = 0x12345678
states = [seed]
for _ in range(20):
    states.append((GLIBC_A * states[-1] + GLIBC_C) & (GLIBC_M - 1))
text = "\n".join(f"{i} → {states[i]}" for i in range(8)) + "\n15 → ?"
t0 = time.perf_counter()
res = post_explain(text)
elapsed = (time.perf_counter() - t0) * 1000
expected = states[15]
print(f"  expected: {expected}")
print(f"  Kazdov:   {res['answer']} ({'✓' if res['answer']==expected else '✗'})")
print(f"  family:   {res['final']['family']}")
print(f"  solver:   {res['final']['solver_used']}")
print(f"  time:     {elapsed:.0f}ms")
print()

# ============================================================
# CASE 2 — Java Random nextInt() unsigned (Minecraft-style seed crack)
# ============================================================
print("=== CASE 2: Java Random — Minecraft-class seed crack ===")
JAVA_A, JAVA_B, JAVA_M = 0x5DEECE66D, 0xB, 1 << 48
seed = 0x123456789ABC
state = (seed ^ JAVA_A) & (JAVA_M - 1)
outputs = []
cur = state
for _ in range(20):
    cur = (JAVA_A * cur + JAVA_B) & (JAVA_M - 1)
    outputs.append(cur >> 16)
text = "\n".join(f"{i} → {outputs[i]}" for i in range(8)) + "\n15 → ?"
t0 = time.perf_counter()
res = post_explain(text)
elapsed = (time.perf_counter() - t0) * 1000
expected = outputs[15]
print(f"  expected: {expected}")
print(f"  Kazdov:   {res['answer']} ({'✓' if res['answer']==expected else '✗'})")
print(f"  family:   {res['final']['family']}")
print(f"  solver:   {res['final']['solver_used']}")
print(f"  time:     {elapsed:.0f}ms")
print()

# ============================================================
# CASE 3 — MT19937 (Python random) — 624 consecutive 32-bit outputs
# ============================================================
print("=== CASE 3: MT19937 — Python random.getrandbits(32) full state ===")
import random
random.seed(0xCAFE)
outputs = [random.getrandbits(32) for _ in range(700)]
# Build text: 624 observations + query at index 650
lines = [f"{i} → {outputs[i]}" for i in range(624)]
lines.append("650 → ?")
text = "\n".join(lines)
t0 = time.perf_counter()
res = post_explain(text)
elapsed = (time.perf_counter() - t0) * 1000
expected = outputs[650]
print(f"  expected: {expected}")
print(f"  Kazdov:   {res['answer']} ({'✓' if res['answer']==expected else '✗'})")
print(f"  family:   {res['final']['family']}")
print(f"  solver:   {res['final']['solver_used']}")
print(f"  time:     {elapsed:.0f}ms")
print(f"  payload size: {len(text):,} chars (full 624-state observation)")
print()

print("=" * 60)
print("Summary: 3 new PRNG families wired end-to-end")
print("=" * 60)
