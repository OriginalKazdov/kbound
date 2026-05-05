def decision(x: int) -> int:
    """Recovered behavioral spec — equivalent to the audited LLM agent.

    Family: linear_residual_policy
    Original LLM cost (est.): ~$0.001/call · this function: ~$0
    """
    return (13 * x + 7) % 17
