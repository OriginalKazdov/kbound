def decision(x: int) -> int:
    """Recovered polynomial threshold — equivalent to the audited LLM."""
    return (7 * x * x + 11 * x + 1) % 23
