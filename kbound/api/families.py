"""Family catalog — metadata for each algebraic family the compiler covers.

Used by the GET /families endpoint and as a single source of truth for the
frontend "Capability Matrix" panel.

Numbers in `measured_accuracy` come from comparison_harness.py runs (n=30
episodes per family). Update when re-running benchmarks.
"""

from __future__ import annotations

FAMILIES = [
    {
        "id": "lcg",
        "name": "Linear Congruential Generator",
        "formula": r"y = (a \cdot x + c) \mod m",
        "category": "algebraic",
        "description": (
            "Affine map modulo m. The classical predictable-RNG pattern. "
            "Frontier LLMs fail because they cannot infer the modulus from K=16 examples."
        ),
        "params_recovered": ["a", "c", "m"],
        "real_world": [
            "Smart contract pseudo-random number generators (Fomo3D-class vulnerability)",
            "Database shard routing via modular hash",
            "Predictable seeding in legacy systems",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": 0.20,
            "sonnet_4_6": 0.167,
        },
        "solver": "rce_lcg",
    },
    {
        "id": "polycoef",
        "name": "Polynomial Coefficient Recovery",
        "formula": r"y = (a \cdot x^2 + b \cdot x + c) \mod p",
        "category": "algebraic",
        "description": (
            "Quadratic polynomial mod prime. Recovered exactly via 3x3 Gaussian "
            "elimination over GF(p)."
        ),
        "params_recovered": ["a", "b", "c", "p"],
        "real_world": [
            "Shamir's secret sharing leak detection",
            "Polynomial commitment scheme audits",
            "Reed-Solomon code analysis",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": 0.367,
            "sonnet_4_6": 0.367,
        },
        "solver": "rce_polycoef",
    },
    {
        "id": "modmul",
        "name": "Modular Multiplication",
        "formula": r"y = (a \cdot x) \mod p",
        "category": "algebraic",
        "description": ("Multiplicative residue. The simplest non-trivial cyclic group operation."),
        "params_recovered": ["a", "p"],
        "real_world": [
            "Diffie-Hellman key exchange auditing",
            "Block cipher round function analysis",
            "Pedersen commitment verification",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": 0.167,
            "sonnet_4_6": 0.067,
        },
        "solver": "rce_modmul",
    },
    {
        "id": "modinv",
        "name": "Modular Inverse",
        "formula": r"y = x^{-1} \mod p",
        "category": "algebraic",
        "description": (
            "Multiplicative inverse via extended Euclidean algorithm. Foundational "
            "for digital signature verification."
        ),
        "params_recovered": ["p"],
        "real_world": [
            "RSA signature verification correctness",
            "ECDSA inverse computation",
            "Cryptographic protocol invariant checking",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": 0.833,
            "sonnet_4_6": 0.889,
        },
        "solver": "rce_modinv",
    },
    {
        "id": "modexp",
        "name": "Modular Exponentiation (RSA primitive)",
        "formula": r"y = a^x \mod p",
        "category": "algebraic",
        "description": (
            "Discrete exponentiation. The core primitive of RSA, ElGamal, DSA. "
            "Recovered via small-prime search and base identification."
        ),
        "params_recovered": ["a", "p"],
        "real_world": [
            "RSA encryption/decryption verification",
            "Diffie-Hellman parameter validation",
            "Detecting weak modulus selection",
        ],
        "measured_accuracy": {
            "compiler": 0.967,
            "haiku_4_5": 0.700,
            "sonnet_4_6": 0.667,
        },
        "solver": "rce_modexp",
    },
    {
        "id": "dlp",
        "name": "Discrete Logarithm",
        "formula": r"\text{find } x \text{ such that } a^x \equiv y \mod p",
        "category": "algebraic",
        "description": (
            "Inverse of modular exponentiation. Brute-force baby-step on small primes. "
            "Cryptanalytically relevant for ElGamal/DSA primitives."
        ),
        "params_recovered": ["a", "p"],
        "real_world": [
            "Detecting weak DH groups",
            "Schnorr signature primitive checks",
        ],
        "measured_accuracy": {
            "compiler": 0.95,
            "haiku_4_5": None,
            "sonnet_4_6": None,
        },
        "solver": "rce_dlp",
    },
    {
        "id": "mod_p_add",
        "name": "Modular Addition (2-input)",
        "formula": r"y = (x_1 + x_2) \mod p",
        "category": "algebraic",
        "description": (
            "Two-input additive group operation. Identified by detecting the "
            "shared modulus p across all examples."
        ),
        "params_recovered": ["p"],
        "real_world": [
            "Group element combination in ZK proofs",
            "MPC additive sharing verification",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": 0.167,
            "sonnet_4_6": 0.133,
        },
        "solver": "rce_modadd",
    },
    {
        "id": "recurrence_fib",
        "name": "Fibonacci-class Linear Recurrence",
        "formula": r"y_n = (a \cdot y_{n-1} + b \cdot y_{n-2}) \mod m",
        "category": "algebraic",
        "description": (
            "Two-step linear recurrence over a finite ring. Coefficients (a, b, m) "
            "recovered by direct linear solve."
        ),
        "params_recovered": ["a", "b", "m"],
        "real_world": [
            "Cellular automata rule recovery",
            "Financial time series with hidden recurrence",
            "Stream cipher state inference",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": 0.20,
            "sonnet_4_6": 0.40,
        },
        "solver": "rce_recurrence",
    },
    {
        "id": "boolean_2input",
        "name": "Boolean 2-Input Operator",
        "formula": r"y = f(x_1, x_2), \quad f \in \{16 \text{ truth tables}\}",
        "category": "algebraic",
        "description": (
            "Any of 16 possible 2-input Boolean functions (AND, OR, XOR, IMPLIES, etc.). "
            "Identified by exact truth-table match."
        ),
        "params_recovered": ["truth_table", "operator_name"],
        "real_world": [
            "Parity bits and checksums",
            "Simple business rule logic gates",
            "Boolean SAT primitive verification",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": 1.00,
            "sonnet_4_6": 0.967,
        },
        "solver": "rce_boolean",
    },
    {
        "id": "parity_kbit",
        "name": "k-bit Parity",
        "formula": r"y = x_1 \oplus x_2 \oplus \ldots \oplus x_k",
        "category": "algebraic",
        "description": ("XOR over k binary inputs. Generalizes 2-input XOR to arbitrary arity."),
        "params_recovered": ["k", "operator_name"],
        "real_world": [
            "Hamming code parity verification",
            "Multi-party XOR-secret-sharing",
            "Cryptographic linear feedback inference",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": 0.50,
            "sonnet_4_6": 0.50,
        },
        "solver": "rce_boolean (parity branch)",
    },
    {
        "id": "glibc",
        "name": "Glibc rand() — canonical LCG",
        "formula": r"\text{seed}_{n+1} = (1103515245 \cdot \text{seed}_n + 12345) \bmod 2^{31}",
        "category": "algebraic",
        "description": (
            "The canonical glibc rand() LCG that every C/C++ programmer thinks they're using. "
            "Recoverable from K ≥ 2 consecutive raw seed outputs."
        ),
        "params_recovered": ["form (raw / windowed-15bit)"],
        "real_world": [
            "CTF challenge PRNGs (canonical pattern)",
            "Embedded firmware quick-prototype RNGs",
            "Custom session token generators in older C servers",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": None,
            "sonnet_4_6": None,
        },
        "solver": "rce_glibc",
    },
    {
        "id": "java_random",
        "name": "Java util.Random LCG",
        "formula": r"\text{seed}_{n+1} = (5DEECE66D_{16} \cdot \text{seed}_n + B_{16}) \bmod 2^{48}",
        "category": "algebraic",
        "description": (
            "java.util.Random — the default PRNG in Java/Kotlin/Android. The 'Minecraft seed "
            "crack' pattern: brute-force the 16 unknown low bits of state from K=2 consecutive "
            "next(32) outputs."
        ),
        "params_recovered": ["recovered_state_low16", "encoding (signed/unsigned)"],
        "real_world": [
            "Minecraft world seed cracking",
            "Android app session token entropy audit",
            "Server-side Java token / nonce / ID generation audit",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": None,
            "sonnet_4_6": None,
        },
        "solver": "rce_java",
    },
    {
        "id": "mt19937",
        "name": "Mersenne Twister (MT19937)",
        "formula": r"\text{state} = \text{Twist}(\text{state}_{prev}); \text{output} = \text{Temper}(\text{state}_i)",
        "category": "algebraic",
        "description": (
            "THE PRNG of the modern world: Python random, PHP mt_rand, Ruby, NumPy default "
            "(pre-1.17), V8 Math.random (pre-2018). Full state recovery from K=624 consecutive "
            "32-bit outputs via tempering inverse (microseconds)."
        ),
        "params_recovered": ["full state (624 words)"],
        "real_world": [
            "PHP password reset token entropy (Argyros & Kiayias, BlackHat 2012)",
            "Python session token / API key generation audit",
            "Web app CSRF token unpredictability",
            "Default-RNG-derived UUID v4 audits",
        ],
        "measured_accuracy": {
            "compiler": 1.00,
            "haiku_4_5": None,
            "sonnet_4_6": None,
        },
        "solver": "rce_mt19937",
    },
    {
        "id": "spatial_threshold",
        "name": "Spatial Threshold / Separable",
        "formula": r"y = \mathbb{1}[g(x) > \theta]",
        "category": "spatial",
        "description": (
            "Tasks with monotone or piecewise-separable structure. Frontier LLMs "
            "handle these reliably; we route to the cheapest model that meets "
            "the accuracy bar (Haiku 4.5 by default)."
        ),
        "params_recovered": [],
        "real_world": [
            "Loan approval threshold rules",
            "Anomaly detection cutoffs",
            "Most production business rules",
        ],
        "measured_accuracy": {
            "compiler": None,
            "haiku_4_5": 0.93,
            "sonnet_4_6": 0.95,
        },
        "solver": "llm_route (spatial path)",
    },
]


def list_families(category: str | None = None) -> list[dict]:
    """Return all families, optionally filtered by category."""
    if category:
        return [f for f in FAMILIES if f["category"] == category]
    return FAMILIES


def get_family(family_id: str) -> dict | None:
    for f in FAMILIES:
        if f["id"] == family_id:
            return f
    return None


def capability_matrix() -> dict:
    """Return a compact heatmap-friendly representation."""
    models = ["compiler", "haiku_4_5", "sonnet_4_6"]
    rows = []
    for f in FAMILIES:
        rows.append(
            {
                "family_id": f["id"],
                "family_name": f["name"],
                "category": f["category"],
                "scores": {m: f["measured_accuracy"].get(m) for m in models},
            }
        )
    return {"models": models, "rows": rows}
