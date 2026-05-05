# kbound — engine container.
#
# Two run modes:
#   CLI:   docker run --rm -v $(pwd):/data kazdov/kbound recover --logs /data/trace.jsonl
#   Serve: docker run --rm -p 8765:8765 kazdov/kbound serve

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/kbound

# Layer 1: deps only (caches well — pyproject changes rarely)
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        "fastapi>=0.115.0" \
        "uvicorn>=0.30.0" \
        "pydantic>=2.0.0" \
        "python-multipart>=0.0.9" \
        "z3-solver>=4.13.0"

# Layer 2: source (changes more often, lighter rebuilds)
COPY kbound/ ./kbound/

# Install the package so the kbound console entrypoint registers
# via the pyproject [project.scripts] table.
RUN pip install --no-deps --no-cache-dir . && \
    python -c "from kbound import compliance, __version__; print(f'install OK · {__version__}')"

WORKDIR /workdir
EXPOSE 8765

# Dispatch entrypoint: first arg picks the mode.
COPY <<'EOF' /usr/local/bin/kbound-entry
#!/bin/sh
set -e
case "$1" in
  recover|"")
    exec kbound "$@"
    ;;
  serve)
    shift
    exec uvicorn kbound.api.main:app \
         --host 0.0.0.0 --port 8765 "$@"
    ;;
  python|sh|bash|/bin/sh|/bin/bash)
    exec "$@"
    ;;
  *)
    exec kbound "$@"
    ;;
esac
EOF
RUN chmod +x /usr/local/bin/kbound-entry

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -fs http://localhost:8765/health || exit 1

ENTRYPOINT ["/usr/local/bin/kbound-entry"]
CMD ["recover", "--help"]
