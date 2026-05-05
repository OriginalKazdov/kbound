def decision(x: int) -> int:
    """Recovered polynomial threshold — equivalent to the audited LLM."""
    return (5 * x * x + 7 * x + 3) % 19
