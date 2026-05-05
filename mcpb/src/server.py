#!/usr/bin/env python3
"""Entry point for the kbound Claude Desktop Extension (MCPB / DXT).

Claude Desktop launches this via ``uv run --directory <bundle> src/server.py``
(see manifest.json `server.mcp_config`). uv resolves the dependencies declared
in `../pyproject.toml` — namely `kbound[mcp]` from PyPI — into a managed
isolated environment, then runs this file. We delegate immediately to
``kbound.mcp.main``, which starts the FastMCP stdio server with all five
tools registered.

The actual tool implementations live in ``kbound/mcp.py``. This file is a
thin shim so the same server code drives both:

  * ``pip install kbound[mcp]`` + ``kbound-mcp`` console script (dev / Cursor / Cline)
  * Claude Desktop bundle (this file)
"""

from kbound.mcp import main

if __name__ == "__main__":
    main()
