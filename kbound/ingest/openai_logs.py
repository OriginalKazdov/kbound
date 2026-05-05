"""Phase 1 ingester — OpenAI Chat Completions JSONL trace logs.

Reads a JSONL file where each line is one Chat Completion. Extracts
(input_feature, output_decision) pairs to feed the spec-recovery engine.

Two extraction modes:
  1. Auto: if the trace has an `_meta` block with `x`/`y`, use that directly
     (this is what our seeded fixtures provide for round-trip determinism).
  2. Heuristic: parse a single integer from the user message, parse a single
     integer from the assistant message. Sufficient for production agents
     where prompts contain a numeric input and the response is a numeric label.

For richer feature extraction (multi-field user messages, structured JSON
responses), the user supplies JSONPath selectors via FeatureSpec.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_INT_RE = re.compile(r"-?\d+")


@dataclass
class FeatureSpec:
    """Optional explicit selector configuration. None = auto/heuristic mode."""

    user_message_index: int = (
        1  # which message is the input (default: index 1, the first user msg after system)
    )
    assistant_message_index: int = -1  # last message
    feature_regex: str = r"-?\d+"  # extract this from user content
    decision_regex: str = r"-?\d+"  # extract this from assistant content


def parse_jsonl_trace(path: str | Path, spec: FeatureSpec | None = None) -> list[tuple[int, int]]:
    """Parse an OpenAI-style JSONL trace file into (x, y) integer pairs.

    Returns: list of (input_feature, output_decision) tuples.
    Raises: ValueError if no usable pairs extracted.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    pairs: list[tuple[int, int]] = []
    with path.open() as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                trace = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"line {line_no}: invalid JSON: {e}") from e

            x, y = _extract_pair(trace, spec)
            if x is None or y is None:
                continue
            pairs.append((x, y))

    if not pairs:
        raise ValueError(f"No (input, output) pairs extracted from {path}")
    return pairs


def _extract_pair(trace: dict, spec: FeatureSpec | None) -> tuple[int | None, int | None]:
    """Extract one (x, y) pair from a single trace record."""
    # Mode 1: explicit _meta block (used by seeded fixtures)
    meta = trace.get("_meta")
    if isinstance(meta, dict) and "x" in meta and "y" in meta:
        try:
            return int(meta["x"]), int(meta["y"])
        except (TypeError, ValueError):
            pass

    # Mode 2: heuristic extraction from messages
    messages = trace.get("messages") or trace.get("input") or []
    if not isinstance(messages, list) or not messages:
        return None, None

    s = spec or FeatureSpec()

    # Find user message
    user_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
    if not user_msgs:
        return None, None
    user_content = user_msgs[0].get("content", "")
    if not isinstance(user_content, str):
        return None, None

    # Find last assistant message
    assistant_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"]
    if not assistant_msgs:
        return None, None
    assistant_content = assistant_msgs[-1].get("content", "")
    if not isinstance(assistant_content, str):
        return None, None

    # Extract integers via regex (default = first integer found)
    feature_re = re.compile(s.feature_regex)
    decision_re = re.compile(s.decision_regex)
    fmatch = feature_re.search(user_content)
    dmatch = decision_re.search(assistant_content)
    if not fmatch or not dmatch:
        return None, None

    try:
        return int(fmatch.group()), int(dmatch.group())
    except ValueError:
        return None, None


def detect_query(path: str | Path) -> int | None:
    """Find the trace marked as the query (assistant content contains '?' or is empty).

    Returns the input integer of that query, or None if no query trace present.
    """
    path = Path(path)
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                trace = json.loads(line)
            except json.JSONDecodeError:
                continue
            messages = trace.get("messages", [])
            assistant_msgs = [
                m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"
            ]
            if not assistant_msgs:
                continue
            content = assistant_msgs[-1].get("content", "")
            if isinstance(content, str) and ("?" in content or not content.strip()):
                user_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
                if user_msgs:
                    user_content = user_msgs[0].get("content", "")
                    m = _INT_RE.search(user_content)
                    if m:
                        return int(m.group())
    return None
