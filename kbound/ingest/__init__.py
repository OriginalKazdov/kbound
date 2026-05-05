"""Trace-format ingesters — parse vendor logs into kbound observation pairs.

Public surface:

    parse_jsonl_trace     — OpenAI Chat Completions JSONL → list of (input, output)
    detect_query          — find a "?" line in a trace (for spec recovery query)
"""

from kbound.ingest.openai_logs import detect_query, parse_jsonl_trace

__all__ = ["parse_jsonl_trace", "detect_query"]
