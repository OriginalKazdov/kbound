#!/usr/bin/env bash
# Local CI — mirrors .github/workflows/ci.yml so contributors can run the
# same checks GitHub Actions runs on push / PR.
#
# Why this exists: GitHub Actions can be unavailable (account suspended,
# region outage, fork without enabled workflows). Run this before pushing
# to catch what CI would catch.
#
# Usage:
#   bash scripts/ci.sh            # from repo root, .venv activated or in cwd
#
# Steps (each fails fast):
#   1. ruff check
#   2. ruff format --check
#   3. pytest
#   4. python -m build (sdist + wheel)
#   5. fresh-venv install smoke (verifies pip install kbound works
#      without [server] extras and `kbound recover` runs against the
#      bundled demo trace)

set -euo pipefail

# Resolve repo root (script may be invoked from elsewhere)
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Activate .venv if present and not already in one
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

step "1/5 ruff check"
ruff check kbound tests

step "2/5 ruff format --check"
ruff format --check kbound tests

step "3/5 pytest"
pytest

step "4/5 python -m build"
rm -rf dist build
python -m build --sdist --wheel >/dev/null

step "5/5 fresh-venv install smoke"
SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

python3 -m venv "$SMOKE_DIR/venv"
"$SMOKE_DIR/venv/bin/pip" install --quiet dist/*.whl

# 5a. import smoke (no [server] extras → fastapi MUST NOT be loaded)
"$SMOKE_DIR/venv/bin/python" - <<'PY'
import sys
import kbound

assert kbound.__version__, "missing __version__"
assert "fastapi" not in sys.modules, "import kbound must not pull fastapi"

r = kbound.recover_rule([(i, (3 * i + 7) % 17) for i in range(8)])
assert r.rule == "decision(x) = (3·x + 7) mod 17", f"got: {r.rule}"
assert r.verified, "recovery not verified"
assert r.predict(42) == 14, f"predict(42) = {r.predict(42)}"
print(f"  library: kbound v{kbound.__version__} import + recover_rule OK")
PY

# 5b. console script smoke
"$SMOKE_DIR/venv/bin/kbound" --help >/dev/null
"$SMOKE_DIR/venv/bin/kbound" recover \
    --logs kbound/data/demos/loan_approval_trace.jsonl \
    --out "$SMOKE_DIR/spec.md"
[ -s "$SMOKE_DIR/spec.md" ] || { echo "spec.md is empty"; exit 1; }
echo "  console script: kbound recover OK"

printf '\n\033[1;32m==> all checks passed\033[0m\n'
