"""Input parsers — accept multiple formats so users can paste whatever they have.

Supported:
  - JSON: {"examples": [[x, y], ...], "query": x_q}
  - CSV-like: lines of "x,y" or "x1,x2,y" (last column = output)
  - Arrow form: "x -> y" or "x => y" or "x → y"
  - Mixed: any of the above per line, ignore comments (#) and blanks
"""

from __future__ import annotations

import json
import re
from typing import Any


def parse_input(text: str) -> dict[str, Any]:
    """Parse free-form input into {examples: [...], query: ...}.

    Tries JSON first, then arrow/CSV form line-by-line. The LAST line that's a
    single value (not a pair) is interpreted as the query.

    Returns: {"examples": [(x, y), ...], "query": x_q, "format_detected": "json"|"arrow"|"csv"}
    """
    text = text.strip()

    # Try JSON first
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "examples" in obj:
            examples = []
            for e in obj["examples"]:
                if isinstance(e, (list, tuple)) and len(e) == 2:
                    examples.append((e[0], e[1]))
            return {
                "examples": examples,
                "query": obj.get("query"),
                "format_detected": "json",
            }
    except (json.JSONDecodeError, ValueError):
        pass

    # Line-by-line: arrow form or CSV form
    lines = [
        ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        return {"examples": [], "query": None, "format_detected": "empty"}

    examples = []
    query = None
    fmt = "unknown"

    for ln in lines:
        # Arrow form: "x -> y" or "x => y" or "x → y" (RHS may be "?")
        m = re.match(r"^(.+?)\s*(?:->|=>|→|\|)\s*(.+)\s*$", ln)
        if m:
            lhs, rhs = m.group(1).strip(), m.group(2).strip()
            x = _parse_value(lhs)
            if rhs in ("?", "") or rhs.startswith("?"):
                query = x
            else:
                y = _parse_value(rhs)
                if y is not None and isinstance(y, int):
                    examples.append((x, y))
                    fmt = "arrow"
                else:
                    query = x
            continue

        # CSV form: "1,2,3" — last value is output
        if "," in ln and re.match(r"^[-\d.,\s\[\]]+$", ln):
            parts = [p.strip() for p in ln.split(",") if p.strip()]
            try:
                vals = [float(p) if "." in p else int(p) for p in parts]
                vals = [int(v) if isinstance(v, float) and v.is_integer() else v for v in vals]
                if len(vals) >= 2:
                    x = vals[0] if len(vals) == 2 else tuple(vals[:-1])
                    y = vals[-1]
                    examples.append(
                        (x, int(y) if isinstance(y, (int, float)) and y == int(y) else y)
                    )
                    fmt = "csv"
                continue
            except (ValueError, TypeError):
                pass

        # Plain single value → query
        try:
            x = _parse_value(ln)
            if x is not None:
                query = x
        except Exception:
            pass

    return {"examples": examples, "query": query, "format_detected": fmt}


def _parse_value(s: str):
    """Parse a value: int, list of ints, or tuple."""
    s = s.strip()
    if not s:
        return None
    # List form: [1, 2, 3] or (1, 2, 3)
    if s.startswith(("[", "(")) and s.endswith(("]", ")")):
        inner = s[1:-1]
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        try:
            return tuple(int(p) for p in parts) if len(parts) > 1 else int(parts[0])
        except ValueError:
            return None
    # Comma-separated without brackets
    if "," in s:
        parts = [p.strip() for p in s.split(",") if p.strip()]
        try:
            return tuple(int(p) for p in parts) if len(parts) > 1 else int(parts[0])
        except ValueError:
            return None
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return None
