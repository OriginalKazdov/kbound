# RESEARCH-ONLY — DO NOT SHIP AS CUSTOMER OPERATORS

The scripts in this directory are paper-grade research. The 6-agent business
council on 2026-05-03 explicitly classified the following as **paper-only,
NOT customer-facing engine operators**:

| Script | Construction | Reason for cajón |
|---|---|---|
| `05_z3_attack.py`, `06_z3_verify_and_predict.py`, `07_scaling_limits.py`, `08_statistical_breadth.py` | 2-LCG XOR composition | Genuinely novel SMT attack but ZERO documented real-world deployment. Engineering theater if exposed as customer operator. |
| `11_mul_composition.py` | 2-LCG MUL composition | Same — multiplicative composition wraps in ways engineers don't ship. |
| `13_and_or_composition.py` | 2-LCG AND/OR composition | AND/OR collapse entropy; no production deployment. |
| `10_three_lcg_xor.py`, `10b_three_lcg_small.py` | 3-LCG XOR composition | Doesn't reach production-scale moduli (N>16 timeouts). |
| `17_tgfsr_xor_lcg.py`, `17b_tgfsr_lcg_verify.py` | TGFSR ⊕ LCG heterogeneous | Theoretical "paranoid embedded firmware". Regulated-gambling smell. Paper figure, not product. |

## Why cajón

Applied Security Strategist (10+ years auditing): "I have NEVER seen a deployed
XOR-of-two-LCGs in a real application — not in firmware audits, not in casino
RNG reviews, not in IoT teardowns. Bouillaguet 2020 attacked PCG's permutation
composition because PCG is **actually deployed in NumPy's BitGenerator and
Rust's rand_pcg**. Our 2-LCG composition has no equivalent target."

Shipping these as customer operators would: (a) bloat the catalog with
operators that never fire on real customer data, (b) telegraph spec-sheet
padding to sophisticated buyers, (c) compromise the audit-grade brand.

## What these scripts ARE for

- USENIX Security / IACR ToSC paper draft (sections: structural analysis,
  Z3-SMT methodology, statistical evaluation)
- Methodology proof for acquirers (shows generalization velocity beyond
  catalog completion)
- Internal research portfolio (reproducible, signed off the engine)
- Future operator candidates IF a real-world target emerges

## What CUSTOMER-FACING operators look like (from this directory's findings)

The 4 generic-modulus engine fixes (already in `solvers/` and routed in
`dispatcher.py`) are the actual customer-facing artifact from this research:

- `rce_lcg_generic.py` — Boyar 1989 generic LCG (any unknown a, c, m)
- `rce_polycoef_generic.py` — Vandermonde-determinant-gcd polynomial
- `rce_recurrence_generic.py` — Hankel-determinant-gcd linear recurrence
- `rce_glibc_tgfsr.py` — glibc TYPE_3 LSB recovery (gated experimental)

These DO ship as operators. The composition scripts in this directory DO NOT.

## Final verdict from council

> "The paper gets the novelty credit. The engine stays sharp. The brand stays buyable."
> — Applied Security Strategist
