# kbound Claude Desktop Extension (MCPB)

This directory packages [kbound](../README.md) as a Claude Desktop Extension
([MCPB / DXT format](https://github.com/anthropics/dxt)), so Claude Desktop
users can install it with one click (or one drag) instead of editing
`claude_desktop_config.json` manually.

## Why this exists

Claude Desktop ≥ 1.5300 deprecated raw `mcpServers` in
`claude_desktop_config.json` in favour of the MCPB plugin format. This
directory is the source of the `.mcpb` archive shipped on the GitHub
Releases page; users drop the archive into Claude Desktop and the five
kbound tools become available.

## Build

Requires Node.js + `uv` locally for testing.

```bash
npx -y @anthropic-ai/mcpb pack mcpb/ kbound-0.2.0.mcpb
```

The output `kbound-0.2.0.mcpb` is a ZIP archive containing `manifest.json`,
`pyproject.toml`, and `src/server.py`. Claude Desktop's bundled `uv` resolves
`kbound[mcp]>=0.2.0` from PyPI at install time.

## Install

Drag `kbound-0.2.0.mcpb` onto Claude Desktop, or open
**Settings → Extensions → Install from file…** and pick the archive.
Restart Claude Desktop. The five tools (recover_rule_from_observations,
predict_under_recovered_rule, list_supported_rule_families,
verify_compliance_against_claimed_rule, classify_observation_geometry)
should appear in the tools palette.

## Layout

```
mcpb/
├── manifest.json       # MCPB metadata + tool list + uv command
├── pyproject.toml      # uv dependency: kbound[mcp]>=0.2.0
├── src/
│   └── server.py       # 1-line shim: kbound.mcp.main()
└── README.md           # this file
```
