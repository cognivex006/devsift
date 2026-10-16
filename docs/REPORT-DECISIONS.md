# Baseline-aware decisions

`report_decisions.assess_finding` combines immutable Git source-origin proof, policy and optional reviewed baseline/suppressions without filesystem writes. It does not infer rule origin from changed-file membership or business risk from static severity.

Supply actual SourceEvidence, base/head refs, rule ID/version and policy. Persisted baselines must first be loaded with `baseline.load_snapshot` and an independently trusted file digest. Baseline tool/catalog/repository/base SHA and rule versions must match; matched fingerprints are recomputed against immutable base source. Missing entries are not proof of a completed baseline analysis. Changed-region introduction requires a complete in-process BaselineObservation, as defined by Git provenance.

Legacy findings remain advisory, except verified critical security findings retain independent security review. UNKNOWN source origin remains incomplete. Explicit unexpired finding-scoped waivers can make eligible findings advisory but cannot suppress unknowns or critical security escalation. Invalid or expired evidence fails with a constant safe error.

Serialized assessments include provenance rationale and baseline status; they explicitly leave impact-if-unchanged and risk-if-changed unknown until case-specific evidence exists. Automatic repair is never authorized. No source, Git metadata, baseline or suppression file is refreshed by this function.
