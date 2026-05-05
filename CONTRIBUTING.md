# Contributing to kbound

Thanks for considering a contribution. The project is small and pre-1.0; the
fastest way to land a change is to open an issue first describing what you
want to do, then a focused pull request.

## Setup

```bash
git clone https://github.com/OriginalKazdov/kbound
cd kbound
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Optional extras:
- `pip install -e ".[server]"` — fastapi + uvicorn for the `kbound.api.main:app` service
- `pip install -e ".[llm]"` — `anthropic` for the spatial → LLM fallback path

## Verify before pushing

Quick checks (≈30 seconds total):

```bash
ruff check kbound tests          # lint
ruff format --check kbound tests # formatting (CI fails if not formatted)
pytest                           # 94 tests, ~25 seconds
```

Full local equivalent of the GitHub Actions CI matrix:

```bash
bash scripts/ci.sh
```

`scripts/ci.sh` runs ruff + pytest + `python -m build` + a fresh-venv install
smoke that imports `kbound` (without `[server]` extras), runs `recover_rule`,
and exercises the `kbound` console script against a bundled demo trace —
the same checks `.github/workflows/ci.yml` runs remotely. Useful when
GitHub Actions is unavailable for any reason.

The remote CI on push runs the same checks across Python 3.10 / 3.11 / 3.12 / 3.13.

## Adding a new operator family

The library is built around 16 typed operator families. Adding a new one is a
first-class contribution. The pattern:

1. **Solver** in `kbound/solvers/rce_<family>.py`. Function signature:
   `solve_<family>(examples, query, **opts) -> dict`. Returns a dict with at
   least `predicted_y`, `consistency_score`, and the recovered parameters.
2. **Operator metadata** in `kbound/operators.py` — add an `OperatorMeta`
   entry under `OPERATORS` with `internal_id`, `business_name`,
   `family_label`, `description`, and `typical_k_lower_bound`.
3. **Family detection** in `kbound/classifier/family_id.py` — add a branch
   that returns your `internal_id` when the support pattern matches.
4. **Dispatch** in `kbound/solvers/dispatcher.py` — add a branch that calls
   your solver and wraps the result in the standard envelope.
5. **Predict path** in `kbound/recover.py` `_apply()` — add the closed-form
   evaluation for held-out inputs.
6. **Test fixture** in `tests/conftest.py` — add a `FamilyFixture` and
   register its name in `ALL_FAMILY_FIXTURE_NAMES`. The parametrized tests in
   `tests/test_families.py` will pick it up automatically.

## Filing a bug

Useful issue content:
- Minimum reproducer with `recover_rule(...)` + the exact observations
- The expected vs. actual `RecoveryResult` (or stack trace if it crashes)
- Output of `python -c "import kbound; print(kbound.__version__)"`
- Python version and OS

## License

By contributing you agree your changes are released under the MIT license
that ships with the project.
