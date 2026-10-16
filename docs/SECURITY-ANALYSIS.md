# Bounded credential detector adapter (T031)

`SecurityAdapter` performs actual local, deterministic credential-shape checks;
it does not invoke or claim unavailable Gitleaks/Semgrep tooling, contact services,
validate credentials against an account, or establish live secret validity. The
rule IDs and severities come from the accepted catalog, not a generic entropy
score or arbitrary regular-expression severity assignment. No source is changed.

```python
adapter = SecurityAdapter(
    delegate=native_adapter,  # Optional existing provider; replace its registration.
    repo_root=git_root, source_sha=full_commit_sha, repository="local",
    config_paths=("src/environment.ts",), redactor=shared_redactor,
)
```

Without a delegate the adapter advertises the six existing source languages and
the fixed `devsift-security` capability. This means this narrow detector is
available, not that all six languages or all secret/security rules are covered.
With a delegate it advertises only that provider's languages through one composed,
bounded hashed `security-...` capability ID. Register the wrapper **instead of**
the delegate; registering two competing language providers would let coordinator
selection bypass one of them. T031 does not change CLI/provider registration.

## Supported candidates and context

Candidates must occupy an entire supported static string literal (PEM blocks may
have outer whitespace). Implemented shapes are:

- `ghp_`, `gho_`, `ghu_`, `ghs_`, or `ghr_` followed by 36–255 ASCII alphanumeric
  characters, or `github_pat_` followed by 50–255 ASCII alphanumeric/underscore
  characters. These are deliberately bounded PAT-like candidate shapes, not a
  claim to validate every current/future provider token format.
- Forty ASCII alphanumeric, slash, plus or equals characters assigned directly
  to a static `aws_secret_access_key`, `awsSecretAccessKey`, `secret_access_key`
  or equivalent case/underscore spelling. Example/YOUR-like values are excluded.
  An AWS access-key ID alone does not establish a secret and is not reported.
- Matching PRIVATE KEY / RSA PRIVATE KEY / EC PRIVATE KEY / OPENSSH PRIVATE KEY
  PEM delimiters enclosing a bounded 32–65,536-character base64-like body, with at
  least 32 actual non-whitespace base64 characters. Deterministic header/footer
  extraction and a single body pass reject mismatches and whitespace-only bodies
  without overlapping-whitespace regex backtracking. This is
  structural candidate detection, not ASN.1/cryptographic validity checking.

Python uses real `ast.parse` string nodes in direct assignment, named argument,
dictionary-value or return contexts; comments, docstrings, fake executable text
and arbitrary string expressions are excluded. Python AST UTF-8 byte offsets are
converted to physical LF/Unicode code-point regions.

The other five languages use a conservative local literal lexer, not a pretend
compiler/AST. It excludes comments, SQL quoted identifiers, Go/C# rune/character
literals, and only accepts assignment/property-like string contexts. It supports
ordinary quoted strings with bounded common escapes, Go raw strings, C# verbatim/
raw quoted text, and SQL single-quoted strings. Ambiguous interpolation, unsupported
escapes and unterminated literals/comments retain incomplete status. It does not
interpret JS/TS regex bodies as assignment/string code: proved expression-start
regex contexts are skipped with escape/character-class handling, while ambiguous
slash/division syntax stays incomplete. It does not
resolve variables, concatenate strings, perform arbitrary language/type parsing,
or establish runtime use/reachability. Ordinary password strings, embedded token
mentions in documentation text, placeholder strings and comments do not become
Critical merely because they contain suggestive words. Static signatures can
still be synthetic, revoked or unreachable and require independent review.

`HC002` is the default candidate rule. `CFG003` requires membership in an exact,
caller-declared canonical `config_paths` tuple. A directory name alone never
proves configuration intent and no test/config path can blanket-waive security.
The declaration is trusted caller context, not an independently discovered
configuration loader. No suppression or remediation is authorized by detection.

## Evidence, masking and composition

Every finding defaults to UNKNOWN. When immutable Git root/SHA are configured,
the adapter verifies the exact physical region against that commit and checks
the **entire snapshot blob** before publishing source proof. Missing, malformed,
stale or dirty snapshots retain SOURCE_UNRESOLVED rather than fabricated location
proof. Physical coordinates are LF/CRLF lines, one-based Unicode code points,
exclusive end. Full credential regions use accepted `sensitive=True` masking, so
BEFORE is entirely `[REDACTED]`, including escapes, private-key newlines and
cropped source evidence. Masking never changes the immutable region or establishes
secret validity. No raw value is stored in a public finding, message or error.

Case identity hashes the original private literal span, rule, path and region;
masked values do not collide merely because their display is identical. Literal
values remain local/private and private literal representations omit them. Known
messages are replaced with catalog titles. Source lookup failures, malformed
input and delegate exceptions use fixed incomplete outcomes without exception or
source text. No source, baseline or database writes or network calls are performed.

The wrapper suppresses delegate stdout/stderr during analysis, preserves its
failure/incomplete state, and retains unresolved findings with normalized hashed
case IDs and canonical messages. It re-verifies delegated physical regions
against the configured source instead of trusting supplied BEFORE text. Credential
rules and delegated regions overlapping detected credentials receive whole-region
masking. Exact rule/region duplicates collapse deterministically; conflicting
delegate case IDs keep the run incomplete. A delegate HC002 in a declared config
path is normalized to CFG003 so the same candidate is not counted twice.
Unresolved findings cannot acquire a caller's asserted NEW lifecycle through this
composition. A provider that executes arbitrary host operations is still trusted
code; this wrapper is not an OS sandbox or a defense against hostile Python
introspection/global logging outside its explicit analysis boundary.

Input is limited to ready UTF-8 snapshots of at most 2 MB, no NULs, existing
supported language/path contracts, and at most 1,000 candidate findings. Invalid
encoding, unsupported/malformed literal boundaries or excess input remain
incomplete. Detector completion only means these bounded checks completed; it is
never a comprehensive secret inventory, language analysis or clean quality gate.
Shared coordinator source/policy checks still own the final gate and independent
critical-security escalation. T032 adds separately reviewed native security
contexts, and later verification hardens coverage; they are not implied here.

Producer checks: `python -m unittest discover -s tests -p test_security_adapter.py`.
Tests create real Git histories, verify fully masked proof and source round trips,
scan/no-write behavior, six-language literal contexts, config scopes, stale and
cropped evidence, strict limits/negative cases, and safe failing/duplicate delegate
composition. A timed isolated child checks malformed 2 KB/20 KB/65 KB PEM bodies;
the composed-provider regression checks that coordinator re-verification retains
whole-region masking for a non-security LOG001 finding overlapping an AWS secret.
Rollback is the scoped adapter/tests/docs commit revert.
