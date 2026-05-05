"""LLM route — real Anthropic API call for spatial tasks.

Builds a prompt from K-shot examples + query, parses LLM response.
Falls back gracefully if no API key.
"""

from __future__ import annotations

import os
import re


def _format_example(x, y) -> str:
    if isinstance(x, (list, tuple)):
        return f"input: {list(x)}  →  output: {y}"
    return f"input: {x}  →  output: {y}"


def _build_prompt(examples: list[tuple], query) -> str:
    examples_str = "\n".join(_format_example(x, y) for x, y in examples)
    if isinstance(query, (list, tuple)):
        q_str = f"input: {list(query)}  →  output: ?"
    else:
        q_str = f"input: {query}  →  output: ?"
    return f"""You are evaluating a deterministic rule from input/output examples.

Examples:
{examples_str}

Predict the output for:
{q_str}

Respond with ONLY the integer output, no explanation.
Output:"""


def call_llm_for_query(examples: list[tuple], query, model: str = "claude-haiku-4-5") -> dict:
    """Call Anthropic API with K-shot prompt. Returns parsed answer + metadata."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "answer": None,
            "model_used": model,
            "raw_output": "",
            "inferred_confidence": None,
            "error": "No ANTHROPIC_API_KEY set; LLM call skipped",
            "stub": True,
        }

    try:
        from anthropic import Anthropic
    except ImportError:
        return {
            "answer": None,
            "model_used": model,
            "raw_output": "",
            "inferred_confidence": None,
            "error": "anthropic SDK not installed",
        }

    # Map our short names → API model strings
    model_map = {
        "claude-haiku-4-5": "claude-haiku-4-5",
        "claude-sonnet-4-6": "claude-sonnet-4-6",
        "claude-opus-4-7": "claude-opus-4-7",
    }
    api_model = model_map.get(model, model)

    client = Anthropic(api_key=api_key)
    prompt = _build_prompt(examples, query)
    try:
        msg = client.messages.create(
            model=api_model,
            max_tokens=64,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_output = msg.content[0].text.strip()
    except Exception as e:
        return {
            "answer": None,
            "model_used": model,
            "raw_output": "",
            "inferred_confidence": None,
            "error": f"API call failed: {e}",
        }

    # Parse — pick the first integer in the output
    matches = re.findall(r"-?\d+", raw_output)
    answer = int(matches[0]) if matches else None

    # Inferred confidence — if multiple integers, lower confidence
    inferred_conf = 0.85 if len(matches) == 1 else (0.65 if matches else 0.0)

    return {
        "answer": answer,
        "model_used": model,
        "raw_output": raw_output,
        "inferred_confidence": inferred_conf,
        "tokens_used": (msg.usage.input_tokens + msg.usage.output_tokens)
        if hasattr(msg, "usage")
        else None,
    }
