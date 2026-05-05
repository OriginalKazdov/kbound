"""Shared modular-arithmetic helpers for the RCE solvers.

Replaces the per-file `_egcd` / `_ext_gcd` / `_modinv` / `_divisors`
copies that accumulated when the solvers were independent modules.

The `egcd` here is iterative — the recursive form used to live in five
solver files and would have hit Python's recursion limit on very large
moduli (≈40 levels for 2³², ≈85 for 2⁵⁶). Iterative is uniformly faster
and never blows the stack.
"""

from __future__ import annotations

from math import gcd as _gcd


def egcd(a: int, b: int) -> tuple[int, int, int]:
    """Iterative extended Euclidean.

    Returns ``(g, x, y)`` such that ``g == gcd(a, b)`` and ``a*x + b*y == g``.
    """
    x0, x1, y0, y1 = 1, 0, 0, 1
    while b != 0:
        q, r = divmod(a, b)
        a, b = b, r
        x0, x1 = x1, x0 - q * x1
        y0, y1 = y1, y0 - q * y1
    return a, x0, y0


def modinv(a: int, m: int) -> int | None:
    """Multiplicative inverse of `a` modulo `m`, or ``None`` if not invertible.

    Uses Python 3.8+ ``pow(a, -1, m)`` for the common path. Returns ``None``
    when ``gcd(a, m) != 1`` so callers can branch on missing inverse.
    """
    a %= m
    if a == 0 or _gcd(a, m) != 1:
        return None
    return pow(a, -1, m)


def divisors(n: int, max_small_prime: int = 5000) -> set[int]:
    """All positive divisors of ``n``.

    Trial-divides by primes up to ``max_small_prime``, then includes any
    remaining large factor as a single piece. Sufficient for the moduli the
    Boyar / Vandermonde-determinant attacks recover (≤ 2⁴⁸).
    """
    if n <= 0:
        return set()
    factors: dict[int, int] = {}
    remainder = n
    d = 2
    while d * d <= remainder and d <= max_small_prime:
        while remainder % d == 0:
            factors[d] = factors.get(d, 0) + 1
            remainder //= d
        d += 1
    if remainder > 1:
        factors[remainder] = factors.get(remainder, 0) + 1
    divs: set[int] = {1}
    for prime, exp in factors.items():
        new_divs: set[int] = set()
        for div in divs:
            for k in range(exp + 1):
                new_divs.add(div * (prime**k))
        divs = new_divs
    return divs
