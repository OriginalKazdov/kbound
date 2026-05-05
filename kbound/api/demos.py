"""Demo cases — pre-built examples for each family.

Each demo has: name, family hint, examples, query, expected_answer, real_world_context.
"""

from __future__ import annotations

import random


def _gen_lcg_demo():
    rng = random.Random(42)
    m, a, c = 7, 3, 2
    xs = rng.sample(range(100), 16)
    ys = [(a * x + c) % m for x in xs]
    return {
        "id": "lcg_basic",
        "title": "Predictable RNG (LCG mod 7)",
        "family_hint": "lcg",
        "examples": list(zip(xs, ys, strict=False)),
        "query": 50,
        "expected_answer": (a * 50 + c) % m,
        "real_world": "Smart contract bug pattern: predictable random number generator. Fomo3D-style vulnerability.",
        "true_params": {"a": a, "c": c, "m": m},
    }


def _gen_polycoef_demo():
    p, a, b, c = 13, 2, 3, 5
    rng = random.Random(99)
    xs = rng.sample(range(40), 16)
    ys = [(a * x * x + b * x + c) % p for x in xs]
    return {
        "id": "polycoef_basic",
        "title": "Polynomial coefficient recovery (mod 13)",
        "family_hint": "polycoef",
        "examples": list(zip(xs, ys, strict=False)),
        "query": 10,
        "expected_answer": (a * 100 + b * 10 + c) % p,
        "real_world": "Cryptographic secret-sharing leak: Shamir's scheme reveals polynomial when coefficients are predictable.",
        "true_params": {"a": a, "b": b, "c": c, "p": p},
    }


def _gen_modexp_demo():
    p, a = 11, 3
    xs = list(range(2, 18))
    ys = [pow(a, x, p) for x in xs]
    return {
        "id": "modexp_rsa",
        "title": "RSA primitive (a^x mod p)",
        "family_hint": "modexp",
        "examples": list(zip(xs, ys, strict=False)),
        "query": 20,
        "expected_answer": pow(a, 20, p),
        "real_world": "Detecting weak RSA implementations: if exponentiation pattern is predictable, the key is broken.",
        "true_params": {"a": a, "p": p},
    }


def _gen_hash_routing_demo():
    rng = random.Random(2024)
    m, a, c = 13, 5, 7
    user_ids = rng.sample(range(10000), 16)
    shards = [(a * uid + c) % m for uid in user_ids]
    return {
        "id": "hash_shard_routing",
        "title": "Database shard routing",
        "family_hint": "lcg",
        "examples": list(zip(user_ids, shards, strict=False)),
        "query": 50000,
        "expected_answer": (a * 50000 + c) % m,
        "real_world": "Common production pattern: route user_id to shard via modular hash. LLMs cannot infer; we recover (a, c, m) from 16 examples.",
        "true_params": {"a": a, "c": c, "m": m},
    }


def _gen_xor_demo():
    return {
        "id": "boolean_xor",
        "title": "Boolean XOR",
        "family_hint": "boolean_2input",
        "examples": [
            ((0, 0), 0),
            ((0, 1), 1),
            ((1, 0), 1),
            ((1, 1), 0),
            ((0, 0), 0),
            ((0, 1), 1),
            ((1, 0), 1),
            ((1, 1), 0),
            ((0, 0), 0),
            ((0, 1), 1),
            ((1, 0), 1),
            ((1, 1), 0),
            ((0, 0), 0),
            ((0, 1), 1),
            ((1, 0), 1),
            ((1, 1), 0),
        ],
        "query": (1, 1),
        "expected_answer": 0,
        "real_world": "Parity bits, checksums, simple boolean logic. Some LLMs succeed here; ours guarantees 100%.",
        "true_params": {"truth_table": [0, 1, 1, 0]},
    }


def _gen_fibonacci_demo():
    def fib_mod(n, m):
        a, b = 0, 1
        for _ in range(n):
            a, b = b, (a + b) % m
        return a

    m = 7
    examples = [(n, fib_mod(n, m)) for n in range(16)]
    return {
        "id": "fibonacci_mod",
        "title": "Fibonacci sequence mod 7",
        "family_hint": "recurrence_fib",
        "examples": examples,
        "query": 18,
        "expected_answer": fib_mod(18, m),
        "real_world": "Sequence-prediction tasks where the rule is a linear recurrence. Common in cellular automata, time-series.",
        "true_params": {"a": 1, "b": 1, "m": m},
    }


def _gen_threshold_demo():
    return {
        "id": "loan_approval",
        "title": "Loan approval (1D threshold)",
        "family_hint": "spatial",
        "examples": [
            (174, 1),
            (192, 1),
            (36, 0),
            (90, 0),
            (151, 1),
            (62, 0),
            (200, 1),
            (28, 0),
            (115, 1),
            (47, 0),
            (180, 1),
            (75, 0),
            (160, 1),
            (44, 0),
            (188, 1),
            (66, 0),
        ],
        "query": 155,
        "expected_answer": 1,
        "real_world": "Business rule: approve if score > 100. LLMs handle this reliably (spatial regime).",
        "true_params": {"threshold": 100},
        "requires_api_key": True,
    }


DEMOS = [
    _gen_lcg_demo(),
    _gen_polycoef_demo(),
    _gen_modexp_demo(),
    _gen_hash_routing_demo(),
    _gen_xor_demo(),
    _gen_fibonacci_demo(),
    _gen_threshold_demo(),
]


def get_demo(demo_id: str) -> dict | None:
    for d in DEMOS:
        if d["id"] == demo_id:
            return d
    return None


def list_demos() -> list[dict]:
    return [
        {
            "id": d["id"],
            "title": d["title"],
            "family_hint": d["family_hint"],
            "real_world": d["real_world"],
            "n_examples": len(d["examples"]),
        }
        for d in DEMOS
    ]
