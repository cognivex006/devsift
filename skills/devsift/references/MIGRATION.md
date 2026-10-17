# Gradual adoption

Start with the [installation and usage guide](USAGE.md). Use a trusted installed interpreter and `-I -B` from the consumer Git root. Setup and optional native helper builds happen separately. Scans, case prompts and policy inspection do not rewrite consumer source or install missing tools.

## Establish an honest starting point

Run an explicit all-source inventory in recommend mode:

```sh
devsift scan --all --legacy-mode recommend
```

This selects current source and requests the supported legacy mode. It does not prove that findings are legacy. Verify tool coverage, source evidence and lifecycle attribution before using the result. Unconfigured providers, unknown origin and unresolved source remain incomplete. Keep UNKNOWN in the report; do not convert unknown findings into a clean baseline to make a gate green.

Review one bounded case at a time. Source verification establishes bytes and location, while candidate consumers, test relationships, regression behavior and business effects may remain unknown. The [report walkthrough](cases/REPORT-WALKTHROUGH.md) demonstrates this distinction with actual CLI output. Findings do not authorize edits, and a recommendation is not a requirement to add missing fields throughout old logging code.

## Move from review to supported enforcement

| Phase | Evidence to review | Policy effect |
| --- | --- | --- |
| Inventory | Actual provider availability and source location | Incomplete remains explicit; no consumer edits |
| Review existing findings | Verified origin, case context and accepted provenance | Unchanged legacy findings remain recommendations |
| Review current changes | Verified new origin and supported rule severity | Enforce only according to the supported policy and CI gate |
| Reassess after an approved change | Fresh diagnostics, relevant regression evidence and bounded rollback plan | Declared passing records alone cannot prove preserved behavior |

Critical security review remains independent in every phase, including unchanged legacy. Lower quality thresholds, declared risk, a baseline, waiver, missing tool or a matching case selector cannot establish that security review happened. A gate can be incomplete and still contain a verified Critical observation that needs attention.

Configure [the CI gate](reference/CI-GATE.md) only with explicitly trusted native manifests and independently obtained digests. Its fresh analysis requires committed source and Git provenance. Working-tree `scan --changed` path selection and source location by themselves are insufficient finding-origin proof. Do not broaden legacy enforcement or manufacture accepted history simply to remove warnings.

## Treat imports and proposals as evidence

Reassemble imported scan evidence against the selected repository; imported rendered reports or serialized lifecycle labels are not trusted proof. `prompt --scan-input` works on an explicit scan envelope. Review prompt generation is not an analysis pass. Implementation proposal generation can precede the operator record and still requires review; even a matching case-bound record grants no source-write or execution authority. See [the case workflow](reference/CASE-PROMPTS.md).

[Change budgets](https://github.com/orchex006/devsift/blob/main/docs/development/CHANGE-BUDGET.md) and [verification records](https://github.com/orchex006/devsift/blob/main/docs/development/VERIFICATION-EVIDENCE.md) are planning aids. Their declarations, measured counts and proposed rollback target do not execute tests, restore a repository, preserve business behavior or grant a batch refactor. Unknown or broad effects require separate review; plan a small explicitly authorized change before touching consumer source.

## Change configuration deliberately

Use [validated policy](reference/PROJECT-POLICY.md) instead of copying ad hoc rules between repositories. The standalone discovery library reads a bounded repo-local or explicitly selected file, without remote/global policy discovery. Invalid present configuration does not silently fall back. CLI Doctor validates its explicit policy path; the discovery library is not an automatic scan configuration loader. Preserve the Critical security floor and accepted schema when overriding supported fields.

Keep report files, approval records, caches and generated artifacts outside consumer source as appropriate. A shell redirect is an operator write, not an effect of the read-only command. Review confidentiality and independently trusted provenance before sharing an artifact. No package publication, tag, release, credential rotation or mass rewrite follows from adopting the tooling.
