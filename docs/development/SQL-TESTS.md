# SQL acceptance fixtures

`tests/test_sql_acceptance.py` exercises the actual pinned ScriptDom helper and
accepted Python host integration. It does not substitute a Python SQL parser or
fabricate native analyzer results. Set `DEVSIFT_TEST_NATIVE=1` after explicit setup;
`DEVSIFT_DOTNET` and `DEVSIFT_SQL_ARTIFACTS` identify the configured runtime/helper
location. Missing/unpinned requested native tools fail setup instead of skipping.
Without explicit native opt-in these acceptance tests are intentionally skipped.

```text
python -m unittest discover -s tests -p test_sql_acceptance.py
```

The fixtures and expected outcomes cover:

- Both real `TSql150Parser` and `TSql160Parser`, with explicit dialect metadata.
- Parameterized `sys.sp_executesql` with bound values and zero SEC003 findings.
- AST counts for four supported DDL statements and one unqualified table
  reference, including real T-SQL `GO` batch boundaries for CREATE VIEW.
- Missing/PostgreSQL/MySQL/unsupported/case-mismatched dialects rejected by the
  raw protocol, so no Python-side dialect guard can substitute for native checks.
- Invalid grammar, opaque dynamic execution, unknown procedure calls, finite
  QUOTENAME storage and EXECUTE AS contexts remain incomplete in both dialects.
- DDL and xp_cmdshell source text is only parsed. An isolated filesystem marker
  must not appear, source bytes remain identical, and unrelated invalid customer
  `.sqlproj`/`Directory.Build.targets` files are not loaded or built.
- Real temporary Git repositories bind SEC003 to an immutable source SHA and
  exact execution-region BEFORE. Native findings retain UNKNOWN lifecycle even
  with source proof; independently computed unchanged source origin routes a
  verified critical legacy finding to security review rather than a new-quality
  block. A modified snapshot cannot inherit the committed source proof.

The source fixture metadata and SQL values are test data, not production source
locations or claims about an actual database. The test never opens a connection,
requests a database service, deploys schema or executes SQL. The accepted helper
contains ScriptDom parser calls, not a database driver or execution API. Marker
and unchanged-byte checks establish observed no-execution/no-source-write behavior
for these fixtures; they are not an OS network/filesystem sandbox or proof about
arbitrary replacement binaries. The native protocol/host integrity pins and
trusted-runtime boundary remain applicable.

These acceptance checks do not claim full T-SQL security coverage, semantic
binding, runtime reachability, exploitability or safe automatic remediation.
Unsupported provenance/flow stays incomplete. SQL rulepack capacity/context and
Unicode coordinate producer regressions remain in `test_sql_rules.py`.

Rollback is the test-only commit revert. No product source or databases are
modified by this task; shared task status/evidence is owned by the controller.
