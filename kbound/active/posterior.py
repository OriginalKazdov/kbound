"""Posterior over candidate rules — enumerate which rules are consistent with K observations.

Wraps the existing 13 solvers as candidate generators. After K observations:
  - For each family, enumerate all consistent (param) tuples
  - Build a flat list of candidates (mixed across families)
  - Each candidate implements .predict(x) → y for use by info_gain.best_query

Memo: enumeration explodes for large parameter spaces. We use:
  - Pool-based: enumerate over a finite parameter pool (small primes for LCG, etc.)
  - Lazy filtering: drop candidates as observations come in
"""

from __future__ import annotations

from kbound.solvers.rce_lcg import DEFAULT_PRIME_POOL

# ============================================================
# Generic candidate base
# ============================================================


class Candidate:
    """Abstract base. Subclasses implement predict(x), repr, eq, hash."""

    family: str = "unknown"

    def predict(self, x):
        raise NotImplementedError

    def consistent_with(self, observations: list[tuple]) -> bool:
        for x, y in observations:
            try:
                if self.predict(x) != y:
                    return False
            except Exception:
                return False
        return True


class LCGCandidate(Candidate):
    family = "lcg"

    def __init__(self, a: int, c: int, m: int):
        self.a, self.c, self.m = a, c, m

    def predict(self, x):
        return (self.a * x + self.c) % self.m

    def __repr__(self):
        return f"LCG({self.a}·x+{self.c} mod {self.m})"

    def __eq__(self, other):
        return isinstance(other, LCGCandidate) and (self.a, self.c, self.m) == (
            other.a,
            other.c,
            other.m,
        )

    def __hash__(self):
        return hash(("lcg", self.a, self.c, self.m))


class PolycoefCandidate(Candidate):
    family = "polycoef"

    def __init__(self, a: int, b: int, c: int, p: int):
        self.a, self.b, self.c, self.p = a, b, c, p

    def predict(self, x):
        return (self.a * x * x + self.b * x + self.c) % self.p

    def __repr__(self):
        return f"Poly({self.a}·x²+{self.b}·x+{self.c} mod {self.p})"

    def __eq__(self, other):
        return isinstance(other, PolycoefCandidate) and (self.a, self.b, self.c, self.p) == (
            other.a,
            other.b,
            other.c,
            other.p,
        )

    def __hash__(self):
        return hash(("poly", self.a, self.b, self.c, self.p))


class ModMulCandidate(Candidate):
    family = "modmul"

    def __init__(self, a: int, p: int):
        self.a, self.p = a, p

    def predict(self, x):
        return (self.a * x) % self.p

    def __repr__(self):
        return f"ModMul({self.a}·x mod {self.p})"

    def __eq__(self, other):
        return isinstance(other, ModMulCandidate) and (self.a, self.p) == (other.a, other.p)

    def __hash__(self):
        return hash(("modmul", self.a, self.p))


class ModExpCandidate(Candidate):
    family = "modexp"

    def __init__(self, a: int, p: int):
        self.a, self.p = a, p

    def predict(self, x):
        return pow(self.a, x, self.p)

    def __repr__(self):
        return f"ModExp({self.a}^x mod {self.p})"

    def __eq__(self, other):
        return isinstance(other, ModExpCandidate) and (self.a, self.p) == (other.a, other.p)

    def __hash__(self):
        return hash(("modexp", self.a, self.p))


# ============================================================
# Enumeration over parameter pools
# ============================================================


def enumerate_lcg(m_pool: list[int] | None = None, ys_max: int | None = None) -> list[Candidate]:
    """Enumerate LCG candidates over a small-prime modulus pool."""
    if m_pool is None:
        m_pool = [m for m in DEFAULT_PRIME_POOL if m <= 50]  # keep enumeration manageable
    if ys_max is not None:
        m_pool = [m for m in m_pool if m > ys_max]
    candidates = []
    for m in m_pool:
        for a in range(1, m):
            for c in range(0, m):
                candidates.append(LCGCandidate(a, c, m))
    return candidates


def enumerate_polycoef(
    p_pool: list[int] | None = None, ys_max: int | None = None
) -> list[Candidate]:
    """Enumerate quadratic polycoef over a small-prime pool. Cubic search-space too large."""
    if p_pool is None:
        p_pool = [p for p in DEFAULT_PRIME_POOL if 5 <= p <= 23]
    if ys_max is not None:
        p_pool = [p for p in p_pool if p > ys_max]
    candidates = []
    for p in p_pool:
        for a in range(0, p):
            for b in range(0, p):
                for c in range(0, p):
                    candidates.append(PolycoefCandidate(a, b, c, p))
    return candidates


def enumerate_modmul(p_pool: list[int] | None = None, ys_max: int | None = None) -> list[Candidate]:
    if p_pool is None:
        p_pool = [p for p in DEFAULT_PRIME_POOL if p <= 50]
    if ys_max is not None:
        p_pool = [p for p in p_pool if p > ys_max]
    return [ModMulCandidate(a, p) for p in p_pool for a in range(1, p)]


def enumerate_modexp(p_pool: list[int] | None = None, ys_max: int | None = None) -> list[Candidate]:
    if p_pool is None:
        p_pool = [p for p in DEFAULT_PRIME_POOL if p <= 50]
    if ys_max is not None:
        p_pool = [p for p in p_pool if p > ys_max]
    return [ModExpCandidate(a, p) for p in p_pool for a in range(2, min(p, 30))]


# ============================================================
# Top-level: build initial candidate pool, filter, refine
# ============================================================


def build_initial_pool(
    observations: list[tuple],
    families: list[str] | None = None,
) -> list[Candidate]:
    """Build the initial candidate pool consistent with K observations.

    Default: enumerate across {lcg, polycoef, modmul, modexp}. Other families
    can be added — they need a Candidate subclass.
    """
    if families is None:
        families = ["lcg", "polycoef", "modmul", "modexp"]

    if not observations:
        ys_max = None
    else:
        ys_max = max(int(y) for _, y in observations)

    candidates: list[Candidate] = []
    if "lcg" in families:
        candidates.extend(enumerate_lcg(ys_max=ys_max))
    if "polycoef" in families:
        candidates.extend(enumerate_polycoef(ys_max=ys_max))
    if "modmul" in families:
        candidates.extend(enumerate_modmul(ys_max=ys_max))
    if "modexp" in families:
        candidates.extend(enumerate_modexp(ys_max=ys_max))

    # Filter by observations
    return [c for c in candidates if c.consistent_with(observations)]


def reduce_to_unique_or_lower(candidates: list[Candidate]) -> list[Candidate]:
    """Group candidates by their prediction signature on a wide probe set.

    Two candidates that produce identical outputs across ALL probes are functionally
    equivalent (for the auditor's purpose, indistinguishable). We keep one representative
    per equivalence class — preferring the simplest (smallest modulus) one.
    """
    if not candidates:
        return []
    # Wide probe set: 0..200 covers most realistic query ranges + a few large
    probes = list(range(0, 201)) + [500, 999, 4096, 50000]
    seen: dict = {}
    for c in candidates:
        try:
            sig = tuple(c.predict(x) for x in probes)
        except Exception:
            continue
        # Prefer simpler representative (smaller modulus where applicable)
        if sig not in seen:
            seen[sig] = c
        else:
            existing = seen[sig]
            # Heuristic: keep the one with smaller "complexity"
            cur_complexity = getattr(c, "m", None) or getattr(c, "p", 1e9)
            ex_complexity = getattr(existing, "m", None) or getattr(existing, "p", 1e9)
            if cur_complexity < ex_complexity:
                seen[sig] = c
    return list(seen.values())
