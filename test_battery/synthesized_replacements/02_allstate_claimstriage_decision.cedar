// Cedar policy — recovered family: polynomial_threshold_rule.
// Parameters: {"a": 5, "b": 7, "c": 3, "p": 19}
// (Generic annotation; AGT integration adapter handles family-specific semantics.)
@kazdov_recovered_rule(
  family: "polynomial_threshold_rule",
  parameters: {"a": 5, "b": 7, "c": 3, "p": 19},
  emitted_by: "kazdov_spec.synth.synthesize_replacement"
)
permit (principal, action == Action::"emit_decision", resource);
