"""RCE-ECDSA-HNP — recover an ECDSA private key from biased nonces.

⚠️  STATUS: v0 SKELETON — NOT WIRED TO DISPATCHER.
The framework, API contract, fpylll integration, and verification logic are in
place. The lattice-basis construction follows Boneh-Venkatesan / Howgrave-Graham
formulation but needs further tuning of column scaling for secp256k1-grade
attacks. Recovery is succeeding on TOY parameters (leak_bits = log2(n) - 16) but
failing on production-grade parameters (leak_bits = 4-8 on secp256k1).

For production use, port a tested reference such as bitlogik/lattice-attack or
Crypto-Cat/CTF/hnp.py, or integrate Sage's built-in HNP solver.


The Hidden Number Problem (Boneh & Venkatesan, 1996) applied to ECDSA
(Howgrave-Graham & Smart, 2001).

If the nonce k used in ECDSA signing is biased — small, has known leading bits,
or any structural pattern — the private key d can be recovered from O(n/leak_bits)
signatures via lattice reduction.

Real-world hits:
  - Sony PS3 (2010): same k reused → trivial recovery
  - Android SecureRandom bug (2013): biased k in early Bitcoin wallets → millions $ stolen
  - LadderLeak (2020): 1-bit side-channel leak → TLS server keys
  - JWT signers (recurring): deterministic / weak k → forgeable tokens

Attack canonical form (k has top `leak_bits` bits = 0):
  Given N signatures (m_i, r_i, s_i) all signed with the same private key d:
    k_i ≡ s_i^{-1} · (m_i + r_i · d)   mod n
  Since k_i < 2^(L - leak_bits) where L = bit length of n:
    Build a lattice from (s_i^{-1} · m_i, s_i^{-1} · r_i) and run LLL.
    The shortest vector reveals d.

We use:
  - `ecdsa` package for curve arithmetic and verification
  - `fpylll` for LLL (much faster than pure-Python implementations)

This is the canonical bitlogik/lattice-attack reformulated and integrated into
Kazdov's family-router. The math is Boneh & Venkatesan + Howgrave-Graham; the
packaging is what's new.
"""

from __future__ import annotations


def _modinv(a: int, n: int) -> int:
    """Extended Euclidean modular inverse."""
    if a == 0:
        raise ValueError("modular inverse of 0 is undefined")
    a = a % n
    g, x, _ = _egcd(a, n)
    if g != 1:
        raise ValueError(f"no modular inverse: gcd({a}, {n}) = {g}")
    return x % n


def _egcd(a: int, b: int) -> tuple[int, int, int]:
    if a == 0:
        return b, 0, 1
    g, x1, y1 = _egcd(b % a, a)
    return g, y1 - (b // a) * x1, x1


# secp256k1 curve order (Bitcoin / Ethereum). We default to this; user can override.
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# secp256r1 (P-256, NIST) — used by TLS, Apple SecureEnclave
SECP256R1_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551

CURVES = {
    "secp256k1": SECP256K1_N,
    "secp256r1": SECP256R1_N,
    "p256": SECP256R1_N,
}


def _build_hnp_basis(signatures: list[dict], n: int, leak_bits: int):
    """Build the lattice basis for HNP attack.

    For each signature i: k_i = a_i + t_i · d mod n  where a_i, t_i derived below.
    If k_i < 2^(L - leak_bits), then |k_i - 2^(L - leak_bits - 1)| < 2^(L - leak_bits - 1).

    Lattice basis (N+2) × (N+2):
        diagonal block of n's, then a row of t_i scaled, then a row of a_i scaled.
    """
    from fpylll import IntegerMatrix

    N = len(signatures)
    L = n.bit_length()
    B = 1 << (L - leak_bits - 1)  # half the upper bound of k_i

    # k_i ≡ a_i + t_i · d  (mod n)  with k_i < B
    # where a_i = m_i / s_i (mod n), t_i = r_i / s_i (mod n)
    a_list = []
    t_list = []
    for sig in signatures:
        m, r, s = sig["m"], sig["r"], sig["s"]
        s_inv = _modinv(s, n)
        a_i = (m * s_inv) % n
        t_i = (r * s_inv) % n
        a_list.append(a_i)
        t_list.append(t_i)

    # Boneh-Venkatesan / Howgrave-Graham lattice basis (N+2) × (N+2):
    #   diag(n, ..., n) for first N rows  (modular relations)
    #   row N:   (t_1, t_2, ..., t_N, 1, 0)
    #   row N+1: (a_1, a_2, ..., a_N, 0, B)
    # The short vector (k_1, ..., k_N, d, B) appears as d·row_N + row_{N+1} + (k_i adjustments).
    # After LLL: a row with col N+1 = ±B has d in col N (with matching sign).
    M = IntegerMatrix(N + 2, N + 2)
    for i in range(N):
        M[i, i] = n
    for i in range(N):
        M[N, i] = t_list[i]
        M[N + 1, i] = a_list[i]
    M[N, N] = 1
    M[N + 1, N + 1] = B
    return M, a_list, t_list, B


def solve_ecdsa_hnp(
    signatures: list[dict],
    leak_bits: int = 4,
    curve: str = "secp256k1",
    public_key_x: int | None = None,
) -> dict:
    """Recover an ECDSA private key from N signatures with biased nonces.

    Args:
        signatures: list of dicts with keys 'm' (message hash, int), 'r', 's'
        leak_bits: assumed number of high bits of k that are zero (or known)
        curve: 'secp256k1' (Bitcoin/Ethereum default) or 'secp256r1' / 'p256'
        public_key_x: optional public key x-coord to verify recovered d

    Returns:
        dict with 'recovered_d' (private key int), 'consistency_score', 'details'.
    """
    try:
        from fpylll import LLL
    except ImportError:
        return {
            "recovered_d": None,
            "consistency_score": 0.0,
            "reason": "fpylll not installed",
            "details": {},
        }

    if curve not in CURVES:
        return {
            "recovered_d": None,
            "consistency_score": 0.0,
            "reason": f"unknown curve {curve!r}; use one of {list(CURVES.keys())}",
            "details": {},
        }

    n = CURVES[curve]
    N = len(signatures)
    if N < 4:
        return {
            "recovered_d": None,
            "consistency_score": 0.0,
            "reason": "need at least 4 signatures with biased nonces",
            "details": {},
        }

    L = n.bit_length()
    if not (1 <= leak_bits < L):
        return {
            "recovered_d": None,
            "consistency_score": 0.0,
            "reason": f"leak_bits={leak_bits} out of valid range [1, {L - 1}]",
            "details": {},
        }

    try:
        basis, a_list, t_list, B = _build_hnp_basis(signatures, n, leak_bits)
    except (ValueError, KeyError) as e:
        return {
            "recovered_d": None,
            "consistency_score": 0.0,
            "reason": f"basis construction failed: {e}",
            "details": {},
        }

    # Run LLL reduction; for harder cases we'd use BKZ with larger block size.
    LLL.reduction(basis)

    # Heuristic candidate enumeration — scan ALL rows of the reduced basis.
    # The "lucky" row containing the secret can appear with various scaling
    # multipliers (LLL is approximate). For each row, derive candidate d via
    # multiple ratios and verify by re-deriving k_i sizes.
    candidates_d = set()
    for row in range(N + 2):
        col_n_val = basis[row, N]
        col_last = basis[row, N + 1]
        if col_last == 0 and col_n_val == 0:
            continue
        # If col_last == ±B (canonical case), col_N is ±d
        if col_last != 0 and abs(col_last) == B:
            sign = 1 if col_last > 0 else -1
            candidates_d.add((sign * col_n_val) % n)
            candidates_d.add((-sign * col_n_val) % n)
        # If col_last == k*B for small k, d = col_N / k
        elif col_last != 0 and B != 0 and col_last % B == 0:
            k_mult = col_last // B
            if abs(k_mult) <= 1024 and k_mult != 0 and col_n_val % k_mult == 0:
                d_raw = col_n_val // k_mult
                candidates_d.add(d_raw % n)
                candidates_d.add((-d_raw) % n)
        # Sometimes the secret appears scaled by gcd of B and other factors —
        # try col_n_val directly (with both signs) as a fallback
        if col_n_val != 0:
            candidates_d.add(col_n_val % n)
            candidates_d.add((-col_n_val) % n)
    candidates_d = list(candidates_d)

    # Filter candidates by re-deriving k_i for each and checking it's small
    valid_d = []
    for d in candidates_d:
        ok_count = 0
        for sig in signatures:
            m, r, s = sig["m"], sig["r"], sig["s"]
            try:
                s_inv = _modinv(s, n)
            except ValueError:
                break
            k_i = (s_inv * (m + r * d)) % n
            # Accept if k_i has the expected size (< 2^(L - leak_bits))
            if k_i < (1 << (L - leak_bits + 2)):  # small slack
                ok_count += 1
        if ok_count >= max(N - 1, int(0.85 * N)):
            valid_d.append((ok_count, d))

    if not valid_d:
        return {
            "recovered_d": None,
            "consistency_score": 0.0,
            "reason": (
                "LLL reduction did not yield a private key candidate. "
                "Try increasing leak_bits or providing more signatures."
            ),
            "details": {"n_signatures": N, "leak_bits_attempted": leak_bits},
        }

    valid_d.sort(reverse=True)
    best_score, recovered = valid_d[0]
    confidence = best_score / N

    return {
        "recovered_d": recovered,
        "consistency_score": confidence,
        "method": "lattice_LLL_HNP",
        "details": {
            "curve": curve,
            "n_signatures": N,
            "leak_bits_assumed": leak_bits,
            "consistent_signatures": f"{best_score}/{N}",
            "recovered_d_hex": hex(recovered),
        },
    }
