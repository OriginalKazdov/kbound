"""Smoke test of the induction compiler core (without FastAPI)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kbound.classifier.oracle_classifier import classify_geometry
from kbound.classifier.family_id import identify_family
from kbound.solvers.dispatcher import dispatch


def test_case(name, examples, query, expected_geometry=None):
    print(f"\n=== {name} ===")
    geom = classify_geometry(examples)
    print(f"  geometry: {geom['geometry']}")
    print(f"  features: {geom['features']}")
    print(f"  recommended_model: {geom['recommended_model']} ({geom['recommended_accuracy']})")
    family = None
    if geom["geometry"] in ("algebraic", "borderline"):
        family = identify_family(examples, geom)
        print(f"  family: {family}")
    result = dispatch(geom["geometry"], family, examples, query, use_llm_fallback=True)
    print(f"  solver: {result['solver_used']}")
    print(f"  answer: {result['answer']}")
    print(f"  confidence: {result['confidence']}")
    print(f"  rationale: {result['rationale'][:140]}...")
    if expected_geometry:
        assert geom["geometry"] == expected_geometry, f"expected {expected_geometry}, got {geom['geometry']}"
        print(f"  ✓ geometry matches expected")


# Test 1: spatial threshold (1D)
test_case(
    "spatial 1D threshold (loan approval)",
    examples=[(174, 1), (192, 1), (36, 0), (90, 0), (151, 1), (62, 0), (200, 1), (28, 0),
              (113, 1), (47, 0), (180, 1), (75, 0), (160, 1), (44, 0), (188, 1), (66, 0)],
    query=120,
    expected_geometry="spatial",
)

# Test 2: LCG mod-m (algebraic — RCE should solve)
# y = (3*x + 2) mod 7  for x in some set
import random
rng = random.Random(42)
m, a, c = 7, 3, 2
xs = rng.sample(range(100), 16)
ys = [(a * x + c) % m for x in xs]
qx = 50
qy_true = (a * qx + c) % m
test_case(
    f"algebraic LCG (true: a={a}, c={c}, m={m}, query={qx} → {qy_true})",
    examples=list(zip(xs, ys)),
    query=qx,
    expected_geometry="algebraic",
)

# Test 3: Modular hash (algebraic — RCE should solve)
m, a, c = 11, 2, 5
xs = rng.sample(range(200), 16)
ys = [(a * x + c) % m for x in xs]
qx = 75
qy_true = (a * qx + c) % m
test_case(
    f"algebraic LCG (true: a={a}, c={c}, m={m}, query={qx} → {qy_true})",
    examples=list(zip(xs, ys)),
    query=qx,
    expected_geometry="algebraic",
)

# Test 4: Conjunctive 2D (spatial)
test_case(
    "spatial conjunctive 2D (AND of thresholds)",
    examples=[((150, 100), 1), ((150, 50), 0), ((20, 150), 0), ((180, 180), 1),
              ((60, 60), 0), ((140, 110), 1), ((90, 70), 0), ((155, 120), 1),
              ((30, 30), 0), ((170, 100), 1), ((45, 80), 0), ((130, 90), 0),
              ((175, 105), 1), ((50, 95), 0), ((165, 130), 1), ((25, 25), 0)],
    query=(160, 110),
    expected_geometry="spatial",
)


# Test 5: Polycoef y = (a*x² + b*x + c) mod p (algebraic)
m, a, b, c = 13, 2, 3, 5
xs = rng.sample(range(50), 16)
ys = [(a * x*x + b * x + c) % m for x in xs]
qx = 10
qy_true = (a * qx*qx + b * qx + c) % m
test_case(
    f"algebraic Polycoef (true: a={a}, b={b}, c={c}, p={m}, query={qx} → {qy_true})",
    examples=list(zip(xs, ys)),
    query=qx,
    expected_geometry="algebraic",
)


# Test 6: ModAdd y = (x1 + x2) mod p (2-input)
m = 11
xs2 = [(rng.randrange(50), rng.randrange(50)) for _ in range(16)]
ys2 = [(a + b) % m for a, b in xs2]
qx2 = (15, 23)
qy2_true = (15 + 23) % m
test_case(
    f"algebraic ModAdd 2-input (true: p={m}, query={qx2} → {qy2_true})",
    examples=list(zip(xs2, ys2)),
    query=qx2,
    expected_geometry="algebraic",
)

# Test 7: Fibonacci mod m (recurrence)
m = 7
def fib_mod(n, m):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, (a + b) % m
    return a
ns_fib = list(range(16))
vals_fib = [fib_mod(n, m) for n in ns_fib]
qn_fib = 18
qv_fib_true = fib_mod(qn_fib, m)
test_case(
    f"algebraic Fibonacci mod {m} (query position={qn_fib} → {qv_fib_true})",
    examples=list(zip(ns_fib, vals_fib)),
    query=qn_fib,
    expected_geometry="algebraic",
)


# Test 8: ModMul y = (a*x) mod p
m, a = 13, 5
xs = rng.sample(range(100), 16)
ys = [(a * x) % m for x in xs]
qx = 22
qy_true = (a * qx) % m
test_case(
    f"algebraic ModMul (true: a={a}, p={m}, query={qx} → {qy_true})",
    examples=list(zip(xs, ys)),
    query=qx,
    expected_geometry="algebraic",
)

# Test 9: ModInv y = x^(-1) mod p
m = 17
def modinv(a, m):
    a = a % m
    if a == 0: return None
    old_r, r, old_s, s = a, m, 1, 0
    while r != 0:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
    return old_s % m if old_r == 1 else None
xs = [x for x in rng.sample(range(1, 50), 16) if modinv(x, m) is not None][:16]
ys = [modinv(x, m) for x in xs]
qx = 7
qy_true = modinv(qx, m)
test_case(
    f"algebraic ModInv (true: p={m}, query={qx} → {qy_true})",
    examples=list(zip(xs, ys)),
    query=qx,
    expected_geometry="algebraic",
)

# Test 10: ModExp y = a^x mod p (RSA primitive)
m, a = 11, 3
xs = list(range(2, 18))  # exponents
ys = [pow(a, x, m) for x in xs]
qx = 20
qy_true = pow(a, qx, m)
test_case(
    f"algebraic ModExp (true: a={a}, p={m}, query={qx} → {qy_true})",
    examples=list(zip(xs, ys)),
    query=qx,
    expected_geometry="algebraic",
)


# Test 11: Boolean XOR (2-input, binary). Note: geometry returns "spatial" because
# the truth table fits a depth-3 axis-aligned tree, but Boolean override in
# dispatcher routes to RCE-Boolean for exact symbolic solution.
test_case(
    "Boolean XOR (true: y = a XOR b, query=(1,1) → 0)",
    examples=[((0,0), 0), ((0,1), 1), ((1,0), 1), ((1,1), 0),
              ((0,0), 0), ((0,1), 1), ((1,0), 1), ((1,1), 0),
              ((0,0), 0), ((0,1), 1), ((1,0), 1), ((1,1), 0),
              ((0,0), 0), ((0,1), 1), ((1,0), 1), ((1,1), 0)],
    query=(1, 1),
    expected_geometry="spatial",  # spatial via tree fit; solver = Boolean override
)

# Test 12: Boolean NAND (2-input)
test_case(
    "Boolean NAND (true: y = NOT (a AND b), query=(1,0) → 1)",
    examples=[((0,0), 1), ((0,1), 1), ((1,0), 1), ((1,1), 0),
              ((0,0), 1), ((0,1), 1), ((1,0), 1), ((1,1), 0),
              ((0,0), 1), ((0,1), 1), ((1,0), 1), ((1,1), 0),
              ((0,0), 1), ((0,1), 1), ((1,0), 1), ((1,1), 0)],
    query=(1, 0),
    expected_geometry="spatial",
)

# Test 13: 4-bit parity. Note: classify_geometry may flag spatial.
def parity(bits): return sum(bits) % 2
xs = [tuple(rng.choice([0, 1]) for _ in range(4)) for _ in range(16)]
ys = [parity(x) for x in xs]
qx = (1, 0, 1, 1)
qy_true = parity(qx)
test_case(
    f"4-bit Parity (query={qx} → {qy_true})",
    examples=list(zip(xs, ys)),
    query=qx,
    expected_geometry=None,  # don't assert — could go either way
)

print("\n\n✓ All smoke tests completed.")
