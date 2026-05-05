"""RCE-Glibc-TGFSR — recover the state of glibc rand() / random() TYPE_3.

Since glibc 2.0, the default rand() / random() implementation is no longer the
simple LCG (TYPE_0, handled by rce_glibc.py) but a 31-word additive feedback
shift register (TYPE_3):

    v_k = (v_{k-31} + v_{k-3}) mod 2^32     for k >= 31
    o_k = v_k >> 1                          (31-bit output, LSB discarded)

This is the same algorithm used by FreeBSD/macOS random(), Solaris random(),
and many embedded libcs. It is NOT a pure LCG and Boyar's attack does not
apply directly — but the LSB-recovery attack does.

Crack outline (Stern-style LSB recovery via GF(2) linear algebra):
    1. Each output o_k pins 31 bits of v_k; the LSB epsilon_k in {0,1} is unknown.
    2. The recurrence reduced mod 2 gives epsilon_k = epsilon_{k-31} XOR epsilon_{k-3}
       for k >= 31, so every epsilon is a GF(2)-linear function of the 31
       initial unknowns epsilon_0..epsilon_30.
    3. The integer relation 2*(o_k - o_{k-31} - o_{k-3}) mod 2^32 must equal
       (epsilon_{k-31} + epsilon_{k-3} - epsilon_k) signed.  Even values are
       {0, 2}; LHS=2 is a HARD positive constraint epsilon_{k-31}=1 AND
       epsilon_{k-3}=1.
    4. Each LHS=2 hit yields two linear equations over GF(2) on the 31
       initial bits.  Gaussian eliminate to recover them.
    5. Once all epsilon_k are known, v_k = 2*o_k + epsilon_k is the full
       state sequence; the recurrence then predicts any future output.

Reference: Stern, "Secret Linear Congruential Generators are Not Cryptographically
Secure" (1987) — the technique was extended to additive-feedback generators by
multiple authors in the 1990s; the specific GF(2) treatment below follows the
public glibc-cracking notes circulated in cryptanalysis lectures.
"""

from __future__ import annotations

DEG = 31  # state size for glibc TYPE_3 (also FreeBSD/macOS random())
SEP = 3  # separation: v_k = v_{k-DEG} + v_{k-SEP}
MOD32 = 1 << 32


def _build_symbolic_lsbs(K: int) -> list[int]:
    """Return sym[k] for k = 0..K-1.

    sym[k] is a DEG-bit integer; bit j set means epsilon_k = ... XOR epsilon_j ... in
    its expansion as a linear combination of the initial DEG unknowns.
    """
    sym = [0] * K
    for j in range(min(DEG, K)):
        sym[j] = 1 << j
    for k in range(DEG, K):
        sym[k] = sym[k - DEG] ^ sym[k - SEP]
    return sym


def _gf2_solve(equations: list[tuple[int, int]], n_unknowns: int) -> list[int] | None:
    """Solve Ax = b over GF(2). Returns list of n_unknowns bits, or None."""
    if not equations:
        return None
    # Pack each equation into a single (n_unknowns + 1)-bit integer:
    # bits [0..n-1] are coefficients, bit n is the rhs.
    rows = [vec | ((rhs & 1) << n_unknowns) for vec, rhs in equations]

    pivot = 0
    for col in range(n_unknowns):
        found = -1
        for i in range(pivot, len(rows)):
            if rows[i] & (1 << col):
                found = i
                break
        if found < 0:
            continue
        if found != pivot:
            rows[pivot], rows[found] = rows[found], rows[pivot]
        p = rows[pivot]
        for i in range(len(rows)):
            if i != pivot and (rows[i] & (1 << col)):
                rows[i] ^= p
        pivot += 1

    # Inconsistency check
    coef_mask = (1 << n_unknowns) - 1
    for r in rows:
        if (r & coef_mask) == 0 and (r >> n_unknowns) & 1:
            return None

    if pivot < n_unknowns:
        return None  # Underdetermined

    # Extract: each pivot row now has a single coef bit set
    sol = [0] * n_unknowns
    for r in rows[:n_unknowns]:
        coef = r & coef_mask
        if coef == 0 or (coef & (coef - 1)) != 0:
            return None  # Not isolated to a single unknown
        bit = coef.bit_length() - 1
        sol[bit] = (r >> n_unknowns) & 1
    return sol


def crack_tgfsr(outputs: list[int]) -> list[int] | None:
    """Recover the underlying 32-bit state sequence v_k from K observed outputs.

    Returns the full v sequence (length K), or None if the data does not fit
    the TGFSR model or the GF(2) system is under-determined.
    """
    K = len(outputs)
    if K < DEG + 32:  # need plenty of constraints
        return None
    if not all(0 <= y < (1 << 31) for y in outputs):
        return None  # outputs must be 31-bit

    sym = _build_symbolic_lsbs(K)

    equations: list[tuple[int, int]] = []
    for i in range(DEG, K):
        lhs = (2 * (outputs[i] - outputs[i - DEG] - outputs[i - SEP])) % MOD32
        if lhs == 2:
            equations.append((sym[i - DEG], 1))
            equations.append((sym[i - SEP], 1))
        elif lhs != 0:
            return None  # outputs do not satisfy the TGFSR recurrence

    if len(equations) < DEG:
        return None  # not enough hard constraints

    eps_init = _gf2_solve(equations, DEG)
    if eps_init is None:
        return None

    eps = list(eps_init)
    for k in range(DEG, K):
        eps.append(eps[k - DEG] ^ eps[k - SEP])

    v = [((2 * outputs[i] + eps[i]) & (MOD32 - 1)) for i in range(K)]

    # Verification: the recurrence must hold over Z/2^32 on the recovered state
    for k in range(DEG, K):
        if (v[k - DEG] + v[k - SEP]) % MOD32 != v[k]:
            return None

    return v


def solve_glibc_tgfsr(examples: list[tuple], query) -> dict:
    """Solver entrypoint. Examples must be (call_index, output) consecutive pairs."""
    if not examples:
        return {"predicted_y": None, "consistency_score": 0.0, "reason": "no examples"}

    sorted_ex = sorted(examples, key=lambda e: e[0])
    xs = [int(e[0]) if not isinstance(e[0], (list, tuple)) else int(e[0][0]) for e in sorted_ex]
    ys = [int(e[1]) for e in sorted_ex]

    if not all(xs[i + 1] - xs[i] == 1 for i in range(len(xs) - 1)):
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "non-consecutive observation indices",
        }

    if len(ys) < DEG + 32:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": f"need at least {DEG + 32} consecutive outputs (TGFSR LSB-recovery)",
        }

    v = crack_tgfsr(ys)
    if v is None:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "TGFSR LSB-recovery did not converge (data may not be glibc TYPE_3)",
        }

    qx = int(query) if not isinstance(query, (list, tuple)) else int(query[0])
    target_idx = qx - xs[0]
    if target_idx < 0:
        return {
            "predicted_y": None,
            "consistency_score": 0.0,
            "reason": "query index < first observed",
        }

    # Project forward
    state = list(v)
    while len(state) <= target_idx:
        nxt = (state[len(state) - DEG] + state[len(state) - SEP]) % MOD32
        state.append(nxt)

    return {
        "predicted_y": state[target_idx] >> 1,
        "consistency_score": 1.0,
        "form": "tgfsr_lsb_recovery",
        "deg": DEG,
        "sep": SEP,
    }
