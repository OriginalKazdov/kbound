"""Atomic transforms — the building blocks of composition search.

Each Atom defines:
  forward(x, params) → y
  param_search(input_output_pairs) → list of (params, score) sorted by score
  invert(y, params) → list of plausible x values (multi-valued for lossy atoms)

Compositions are built bottom-up: search the inner atom over (x_input, z_intermediate),
search the outer atom over (z_intermediate, y_output). Where z is unknown, we use the
outer atom's invert() to enumerate candidates.

Novelty claim: this is the framework. The atoms themselves are textbook.
"""

from __future__ import annotations

SMALL_PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]


# ============================================================
# Atom interface
# ============================================================


class Atom:
    name: str = "abstract"
    invertible_given_params: bool = False

    def forward(self, x: int, params: dict) -> int:
        raise NotImplementedError

    def param_search(self, pairs: list[tuple[int, int]]) -> list[tuple[dict, float]]:
        """Return ranked list of (params, score) — score in [0, 1] = fraction consistent."""
        raise NotImplementedError

    def invert(self, y: int, params: dict, hint_max: int = 1024) -> list[int]:
        """Return plausible x values such that forward(x, params) == y. Multi-valued for lossy atoms."""
        raise NotImplementedError


# ============================================================
# 1. AffineMod — y = (a·x + c) mod m
# ============================================================


class AffineMod(Atom):
    name = "affine_mod"
    invertible_given_params = True

    def forward(self, x, params):
        return (params["a"] * x + params["c"]) % params["m"]

    def param_search(self, pairs, m_pool=SMALL_PRIMES):
        if not pairs:
            return []
        ys = [y for _, y in pairs]
        ymax = max(ys)
        candidates = []
        for m in m_pool:
            if m <= ymax:
                continue
            for a in range(1, m):
                for c in range(0, m):
                    n_ok = sum(1 for x, y in pairs if (a * x + c) % m == y)
                    score = n_ok / len(pairs)
                    if score >= 0.5:
                        candidates.append(({"a": a, "c": c, "m": m}, score))
        candidates.sort(key=lambda kv: -kv[1])
        return candidates[:50]

    def invert(self, y, params, hint_max=1024):
        # y = (a·x + c) mod m  →  for each x_candidate in [0, hint_max), check
        a, c, m = params["a"], params["c"], params["m"]
        # We want x such that (a·x + c) ≡ y (mod m)
        # If gcd(a, m) = 1, x ≡ (y - c) · a^{-1} (mod m)
        # Otherwise multivalued
        from math import gcd

        g = gcd(a, m)
        if (y - c) % g != 0:
            return []
        if g == 1:
            a_inv = pow(a, -1, m)
            x_base = ((y - c) * a_inv) % m
            return [x_base + k * m for k in range(hint_max // m + 1)][:hint_max]
        else:
            # multi-valued; enumerate
            results = []
            for x in range(hint_max):
                if (a * x + c) % m == y:
                    results.append(x)
            return results


# ============================================================
# 2. ModReduce — y = x mod n  (the truncation atom)
# ============================================================


class ModReduce(Atom):
    name = "mod_reduce"
    invertible_given_params = True

    def forward(self, x, params):
        return x % params["n"]

    def param_search(self, pairs, n_pool=None):
        if n_pool is None:
            n_pool = list(range(2, 64)) + [128, 256, 512, 1024, 2048, 4096]
        ys = [y for _, y in pairs]
        ymax = max(ys)
        candidates = []
        for n in n_pool:
            if n <= ymax:
                continue
            n_ok = sum(1 for x, y in pairs if x % n == y)
            score = n_ok / len(pairs)
            if score >= 0.85:
                candidates.append(({"n": n}, score))
        candidates.sort(key=lambda kv: -kv[1])
        return candidates[:20]

    def invert(self, y, params, hint_max=4096):
        n = params["n"]
        if y >= n:
            return []
        # x mod n == y  →  x ∈ {y, y+n, y+2n, ...}
        return [y + k * n for k in range(hint_max // n + 1)]


# ============================================================
# 3. Power — y = x^k  (no mod, for composition with mod-reduce later)
# ============================================================


class Power(Atom):
    name = "power"
    invertible_given_params = False  # x^k loses sign info for even k

    def forward(self, x, params):
        return x ** params["k"]

    def param_search(self, pairs, k_pool=(2, 3, 4, 5)):
        candidates = []
        for k in k_pool:
            n_ok = sum(1 for x, y in pairs if x**k == y)
            score = n_ok / len(pairs)
            if score >= 0.5:
                candidates.append(({"k": k}, score))
        candidates.sort(key=lambda kv: -kv[1])
        return candidates

    def invert(self, y, params, hint_max=1024):
        if y < 0:
            return []
        k = params["k"]
        # integer k-th root
        x = round(y ** (1.0 / k))
        results = [x_c for x_c in (x - 1, x, x + 1) if x_c >= 0 and x_c**k == y]
        return results


# ============================================================
# 4. ConstAdd — y = x + c  (a "shift" of the input)
# ============================================================


class ConstAdd(Atom):
    name = "const_add"
    invertible_given_params = True

    def forward(self, x, params):
        return x + params["c"]

    def param_search(self, pairs, c_pool=None):
        if c_pool is None:
            c_pool = list(range(-50, 51))
        candidates = []
        for c in c_pool:
            n_ok = sum(1 for x, y in pairs if x + c == y)
            score = n_ok / len(pairs)
            if score >= 0.85:
                candidates.append(({"c": c}, score))
        candidates.sort(key=lambda kv: -kv[1])
        return candidates[:5]

    def invert(self, y, params, hint_max=1024):
        return [y - params["c"]]


# ============================================================
# 5. Identity — y = x
# ============================================================


class Identity(Atom):
    name = "identity"
    invertible_given_params = True

    def forward(self, x, params):
        return x

    def param_search(self, pairs):
        n_ok = sum(1 for x, y in pairs if x == y)
        score = n_ok / len(pairs)
        return [({}, score)] if score >= 0.85 else []

    def invert(self, y, params, hint_max=1024):
        return [y]


class XorConst(Atom):
    """y = x ^ c — bitwise XOR with a constant."""

    name = "xor_const"
    invertible_given_params = True

    def forward(self, x, params):
        return x ^ params["c"]

    def param_search(self, pairs, c_pool=None):
        if c_pool is None:
            c_pool = list(range(0, 256))
        candidates = []
        for c in c_pool:
            n_ok = sum(1 for x, y in pairs if (x ^ c) == y)
            score = n_ok / len(pairs)
            if score >= 0.85:
                candidates.append(({"c": c}, score))
        candidates.sort(key=lambda kv: -kv[1])
        return candidates[:5]

    def invert(self, y, params, hint_max=1024):
        return [y ^ params["c"]]


class BitShiftRight(Atom):
    """y = x >> k — right shift (lossy: low k bits lost)."""

    name = "bitshift_right"
    invertible_given_params = True

    def forward(self, x, params):
        return x >> params["k"]

    def param_search(self, pairs, k_pool=None):
        if k_pool is None:
            k_pool = list(range(1, 16))
        candidates = []
        for k in k_pool:
            n_ok = sum(1 for x, y in pairs if (x >> k) == y)
            score = n_ok / len(pairs)
            if score >= 0.85:
                candidates.append(({"k": k}, score))
        candidates.sort(key=lambda kv: -kv[1])
        return candidates[:5]

    def invert(self, y, params, hint_max=4096):
        # x >> k == y → x ∈ [y << k, (y+1) << k - 1]
        k = params["k"]
        base = y << k
        return [base + i for i in range(min(1 << k, hint_max))]


ATOMS = {
    "affine_mod": AffineMod(),
    "mod_reduce": ModReduce(),
    "power": Power(),
    "const_add": ConstAdd(),
    "identity": Identity(),
    "xor_const": XorConst(),
    "bitshift_right": BitShiftRight(),
}
