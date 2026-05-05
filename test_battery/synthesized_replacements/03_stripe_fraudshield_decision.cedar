// Cedar policy — recovered family: polynomial_threshold_rule.
// Parameters: {"a": 7, "b": 11, "c": 1, "p": 23}
// (Generic annotation; AGT integration adapter handles family-specific semantics.)
@kazdov_recovered_rule(
  family: "polynomial_threshold_rule",
  parameters: {"a": 7, "b": 11, "c": 1, "p": 23},
  emitted_by: "kazdov_spec.synth.synthesize_replacement"
)
permit (principal, action == Action::"emit_decision", resource);
