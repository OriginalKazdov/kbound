# Papers — the research kbound is built on

Four working papers (Dovzak) on the geometric structure of K-shot rule
induction and a master inequality for sample complexity. They are the
theoretical and empirical foundation of [`kbound`](../README.md): the
operator catalog, the geometry-routed dispatcher, the K-bound
certificate every recovery emits, and the Relational Consistency
Executor pattern all come from this line of work.

You do **not** need to read these to use `kbound` — `recover_rule()`
and the MCP tools work standalone. They are here for researchers who
want the answer to *"is this principled?"* rather than *"how do I use
it?"*

The PDFs in this directory are the canonical versions. Working drafts
and superseded variants live outside the public repo.

---

## 1. The Compositional Depth Decay is a Dispatch Tax

**Subtitle:** Separating Parsing from Evaluation Collapses the
Exponential Decay Rate α to Zero.

**File:** [`01_compositional_depth_law.pdf`](01_compositional_depth_law.pdf)

We study compositional depth extrapolation on balanced reverse-Polish
modular arithmetic and identify a two-parameter empirical law for
out-of-distribution accuracy: `acc(d) = floor_arch + (acc(d_min) −
floor_arch) · exp(−α_arch · (d − d_min))`. Across 42 runs spanning
three architectures and multiple curricula, leave-one-out prediction
of unseen depths has mean absolute error 1.7–3.2 percentage points. We
propose that α measures a *dispatch tax* — the per-depth cost of
learning *when* to combine intermediate states. Architectures that must
infer execution structure pay this tax; architectures whose
computational graph encodes it directly do not. We design **TreeMoTE**,
a recursive shared-cell architecture whose forward pass traverses the
expression parse tree, and verify the extreme-case prediction α → 0.
TreeMoTE achieves 100 % accuracy at p = 7 depths up to d = 8 (OOD),
extends to d = 12 at 93–100 %, and outperforms Transformer by 80 pp
at d = 8.

**Categories** (if posted to arXiv): `cs.LG`, `cs.CL`. **Status:**
working draft.

---

## 2. The Geometric Boundary of Few-Shot Rule Induction in Frontier LLMs

**Subtitle:** Spatial Separability, not Output Cardinality, Predicts
In-Context Recovery.

**File:** [`02_llm_geometric_boundary.pdf`](02_llm_geometric_boundary.pdf)

We test whether the geometric structure of a parameterized rule
predicts whether commercial frontier-family large language models will
recover it from K=16 in-context input–output examples. We design a
cardinality-controlled falsification experiment with three independent
task-suite seeds: at output cardinality 4, spatially separable rules
(`y = ⌊x/50⌋`) are recovered at a mean accuracy of 0.88 across three
commercial frontier-family models (Anthropic Haiku 4.5, Sonnet 4.6,
OpenAI GPT-4o-mini), while algebraically coupled rules with the same
cardinality (`y = ((ax+c) mod m) mod 4`) fall to 0.25 (Δ = 0.63 ± 0.02
across seeds). At cardinality 50, the same comparison gives 0.88
versus 0.02 (Δ = 0.86 ± 0.01). By-task permutation tests yield p < 10⁻⁴
on all six per-model contrasts. Best-of-3 ensemble accuracy reaches
1.00 on spatial families at both cardinalities and only 0.56 ± 0.03
and 0.05 ± 0.03 on algebraic families: pooling LLMs does not cross the
boundary. The cardinality hypothesis ("larger output space is harder")
predicts the opposite of what we observe and is falsified.

**Categories** (if posted to arXiv): `cs.CL`, `cs.LG`. **Status:**
working draft.

---

## 3. Geometry of Few-Shot Rule Induction

**Subtitle:** Spatial Separability, Algebraic Coupling, and Relational
Consistency.

**File:** [`03_geometry_of_induction.pdf`](03_geometry_of_induction.pdf)

We study K-shot induction of parameterized operators from input–output
examples and identify a structural boundary between rules whose
parameters are recoverable by permutation-invariant attention and
rules whose parameters are not. Across five operator families (single
threshold, conjunctive thresholds, depth-2 axis-aligned decision
trees, modular polynomial coefficients, and linear congruential
generators) trained from 16 examples per episode, performance
partitions cleanly along this boundary: spatially separable
parameters — those locally identifiable from a sub-region of the
support — are recovered at 93–96.5 % accuracy across multiple seeds,
while algebraically coupled parameters fall to chance, even under
iterative refinement with continuous residual feedback. We propose the
**Relational Consistency Executor (RCE)**, a hybrid pipeline in which
the neural component contributes a scale prior and a domain-aware
symbolic search closes the algebraic constraint by validating
consistency against the support. RCE recovers polynomial coefficients
perfectly via a 3 × 3 linear system in F_p, and recovers LCG
parameters at 96.4 % ± 1.2 % over three seeds with strict
prime-disjoint train/test splits — an improvement of approximately 31×
over the pure-attention baseline.

**Categories** (if posted to arXiv): `cs.LG`, `cs.AI`. **Status:**
working draft.

---

## 4. A Universal Sample-Complexity Framework for Black-Box Rule Recovery

**File:** [`04_kbound_framework.pdf`](04_kbound_framework.pdf)

We propose a unified framework for the sample complexity of recovering
deterministic rules from black-box observation. The literature on rule
recovery is fragmented: Boyar (1989) settled linear congruential
generators with K = O(1) observations; Stern (1987) and
Contini–Shparlinski (2005) addressed truncated LCGs via lattice
reduction; Bouillaguet et al. (2020) cracked the PCG family by
hand-crafted guess-and-determine; Martinez (2022) extended lattice
methods to combined multiple recursive generators with subtraction.
Each result covers a single rule class in isolation, with class-specific
complexity measures and ad-hoc proofs. We unify these under a single
complexity measure `C(C)` capturing degrees of freedom, structural
depth, and output bandwidth, and prove a two-sided master inequality:
an information-theoretic lower bound that is universal across
recovery procedures, and a constructive upper bound that is class-dependent.
We instantiate the framework on eight known rule classes (single LCG,
truncated LCG, polynomial mod p, linear recurrence, Boolean truth
tables, k-bit parity, glibc TGFSR additive feedback, and the Java
truncated 48-bit LCG) and recover all known bounds as corollaries. We
then state two new bounds with no published analogue: K_min for
bitwise non-linear 2-LCG compositions (XOR, MUL, AND, OR), and K_min
for heterogeneous PRNG XOR compositions (e.g. TGFSR ⊕ LCG), validated
empirically (98/100 random configurations recovered across N ∈ {32,
48, 64} for 2-LCG XOR; 20/20 held-out outputs predicted for TGFSR ⊕
LCG at K = 80).

**Categories** (if posted to arXiv): `cs.CR`, `cs.IT`, `cs.LG`.
**Status:** working draft.

---

## How to cite

While preprints / journal versions are pending, please cite as:

```bibtex
@unpublished{dovzak2026compositional,
  author = {Juan Cruz Dovzak},
  title  = {The Compositional Depth Decay is a Dispatch Tax},
  year   = {2026},
  note   = {Working draft. \url{https://github.com/OriginalKazdov/kbound/blob/main/papers/01_compositional_depth_law.pdf}},
}

@unpublished{dovzak2026geometricboundary,
  author = {Juan Cruz Dovzak},
  title  = {The Geometric Boundary of Few-Shot Rule Induction in Frontier LLMs},
  year   = {2026},
  note   = {Working draft. \url{https://github.com/OriginalKazdov/kbound/blob/main/papers/02_llm_geometric_boundary.pdf}},
}

@unpublished{dovzak2026geometry,
  author = {Juan Cruz Dovzak},
  title  = {Geometry of Few-Shot Rule Induction: Spatial Separability, Algebraic Coupling, and Relational Consistency},
  year   = {2026},
  note   = {Working draft. \url{https://github.com/OriginalKazdov/kbound/blob/main/papers/03_geometry_of_induction.pdf}},
}

@unpublished{dovzak2026kbound,
  author = {Juan Cruz Dovzak},
  title  = {A Universal Sample-Complexity Framework for Black-Box Rule Recovery},
  year   = {2026},
  note   = {Working draft. \url{https://github.com/OriginalKazdov/kbound/blob/main/papers/04_kbound_framework.pdf}},
}
```

## Future: Zenodo for DOIs (no endorsement required)

Each paper can be deposited on [Zenodo](https://zenodo.org/) for a
permanent DOI without arXiv's endorsement requirement — the GitHub ↔
Zenodo integration creates a DOI per release automatically. When ready
to lock the citations, deposit each PDF and update the BibTeX entries
above with the resulting `doi = {…}` field.
