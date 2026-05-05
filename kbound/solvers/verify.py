"""Consistency verification — re-evaluate predicted formula on support set.

After any RCE solver returns parameters, this re-runs the formula on the support
to confirm 100% consistency. If consistency drops, lower the confidence reported
to the user.

This is the cell-audit-style sanity check (399/399 mappings perfect on Prism).
"""

from __future__ import annotations


def verify_lcg(examples, a, c, m) -> float:
    """Verify y = (a*x + c) mod m holds on support."""
    if a is None or c is None or m is None:
        return 0.0
    correct = 0
    for x, y in examples:
        x_v = int(x) if not isinstance(x, (list, tuple)) else int(x[0])
        if (a * x_v + c) % m == int(y):
            correct += 1
    return correct / len(examples)


def verify_polycoef(examples, a, b, c, p) -> float:
    if any(v is None for v in (a, b, c, p)):
        return 0.0
    correct = 0
    for x, y in examples:
        x_v = int(x) if not isinstance(x, (list, tuple)) else int(x[0])
        if (a * x_v * x_v + b * x_v + c) % p == int(y):
            correct += 1
    return correct / len(examples)


def verify_modmul(examples, a, p) -> float:
    if a is None or p is None:
        return 0.0
    correct = 0
    for x, y in examples:
        x_v = int(x) if not isinstance(x, (list, tuple)) else int(x[0])
        if (a * x_v) % p == int(y):
            correct += 1
    return correct / len(examples)


def verify_modexp(examples, a, p) -> float:
    if a is None or p is None:
        return 0.0
    correct = 0
    for x, y in examples:
        x_v = int(x) if not isinstance(x, (list, tuple)) else int(x[0])
        if pow(a, x_v, p) == int(y):
            correct += 1
    return correct / len(examples)


def verify_modinv(examples, p) -> float:
    if p is None:
        return 0.0
    correct = 0
    for x, y in examples:
        x_v = int(x) if not isinstance(x, (list, tuple)) else int(x[0])
        if (x_v * int(y)) % p == 1:
            correct += 1
    return correct / len(examples)


def verify_modadd(examples, p) -> float:
    if p is None:
        return 0.0
    correct = 0
    for x, y in examples:
        if (int(x[0]) + int(x[1])) % p == int(y):
            correct += 1
    return correct / len(examples)
