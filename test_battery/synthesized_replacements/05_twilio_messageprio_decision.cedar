// Cedar policy — recovered family: exponential_pattern_rule.
// Parameters: {"a": 3, "p": 19}
// (Generic annotation; AGT integration adapter handles family-specific semantics.)
@kazdov_recovered_rule(
  family: "exponential_pattern_rule",
  parameters: {"a": 3, "p": 19},
  emitted_by: "kazdov_spec.synth.synthesize_replacement"
)
permit (principal, action == Action::"emit_decision", resource);
