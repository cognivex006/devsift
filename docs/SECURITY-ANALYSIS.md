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
critical-security escalation.

## Bounded AST security contexts (T032)

`python_contexts(text)` in `security_context.py` returns a frozen `ContextReport`
containing only completion and rule/physical-region facts. SecurityAdapter 1.1.0
composes these Python contexts with the credential detector; frontend helper and
factory internal version 1.2.0 add actual ESLint/TypeScript AST contexts. These are
internal adapter/rulepack changes, not a project release or publication. Parser,
ESLint, TypeScript, .NET SDK and ScriptDom dependency pins are unchanged.

| Platform | SEC001 sensitive logging | SEC002 TLS | SEC003 dynamic SQL |
| --- | --- | --- | --- |
| Python | Imported stdlib logging aliases/getLogger; unshadowed print | Imported requests methods/Session verify=False; ssl unverified-context factory | No new coverage |
| TypeScript/JavaScript | Unshadowed global console methods | Imported Node https Agent/get/request and tls.connect literal options | No new coverage |
| T-SQL | No new coverage | No new coverage | Existing real ScriptDom rule and matched parameterized controls |
| C#/Go | **No new SEC001 coverage** | **No new SEC002 coverage** | No new coverage |

The existing six-language credential-shape detector still applies independently
on C#/Go. No regex is substituted for unimplemented native security contexts.
The C#/Go helpers and factories are not changed by T032.

SEC001 requires an actual supported AST logging call with a direct credential-
signature literal, or a same-scope static literal binding with that signature.
The signatures are the bounded PAT/AWS/PEM shapes above, never just a variable
name or free text mentioning passwords. Python supports selected logging imports,
module aliases, getLogger instances, direct scalar aliases, local literal bindings
and builtin print. Logger format arguments and msg= are examined, not unrelated
control kwargs. Imported names are a **static AST binding contract**, not proof of
the installed/live requests or logging module identity: target modules are never
imported or executed. Function parameters, rebinding, overridden members and
lookalike modules invalidate nominal identities. Function literal bindings are
not inferred from an outer scope; class/method namespace flow is unsupported.

Python SEC002 requires exact boolean False in a recognized requests method's
verify keyword or a tracked requests Session.verify assignment. String 'false',
integer values, arbitrary similarly named functions, and normal verified requests
do not trigger this rule. The explicitly imported ssl._create_unverified_context
factory is recognized; general SSL-context property/dataflow analysis is absent.
For this factory, the checked default or explicitly resolved CERT_NONE/CERT_REQUIRED
and boolean check_hostname states determine the finding. Restoring both
CERT_REQUIRED and check_hostname=True produces no SEC002; unproved/unsupported
arguments or conflicting states remain incomplete. The test constructs the
actual stdlib SSL context with restored checks without opening any connection.
No requests, ssl or target imports execute during these checks.

Unrelated Python application branches, loops or classes are outside bounded rule
matching and do not automatically make every module incomplete. Unsupported
syntax/scope/flow is incomplete when it contains a signature candidate, proven
sensitive binding, relevant TLS call or potentially mutated security identity.
Ambiguous flow cannot silently inherit a convenient safe binding. Syntax errors,
invalid input and excessive diagnostic counts remain incomplete. This is not a
claim to analyze all Python control flow or all runtime security effects.

The frontend uses real ESTree scope/import definitions. Console arguments must
be direct signature literals or a uniquely bound same-variable-scope literal
without later writes; arbitrary transformations are not assumed equivalent.
Node TLS requires an actual import from https/node:https or tls/node:tls and exact
boolean false in a direct options object. Static named-import aliases, namespace/
default imports and lexical shadows are checked. Duplicate property overrides
use the effective last static property; spreads, unknown computed properties,
string values, reassignments and overridden module members are not treated as
proof of an insecure option. CommonJS require, deep option aliases, arbitrary
logger libraries and runtime module mutation outside the source are not covered.
Options positions follow the supported API signatures: Agent reads argument 0;
https.get/request read argument 0 or argument 1 after an explicit HTTPS URL;
tls.connect reads argument 0 or the supported numeric-port/optional-host options
position. An ignored second Agent argument never becomes evidence of TLS bypass.
An actual built-in Agent construction test confirms its options without network
activity. Direct module-object aliases (including transparent TS casts) are
linked for member-mutation invalidation; replacing a member through an alias
invalidates the original import identity and keeps analysis incomplete rather
than reporting against a conveniently assumed original implementation. This is
bounded static alias handling, not arbitrary object/interprocedural taint.
Direct mutation targets include assignment/update/delete, destructuring with
rest/default patterns, and for-in/for-of writes. Transparent TypeScript/chain
wrappers and nested member receivers invalidate the underlying identifier root.
Function-based reflection such as Object.assign/defineProperty and arbitrary
interprocedural mutation are outside this direct-write contract.

Masked literals, placeholders, ordinary text, unrelated imports, same-name
parameters and sanitized-value examples do not acquire SEC001 merely from their
names. Opaque transformations are outside this direct scalar proof, not assumed
safe sanitizers. Neither rule proves reachability, live credentials, exploitability,
installed package identity or a complete taint/security model. Every emitted case
retains default UNKNOWN lifecycle until independently classified.

SEC001 source regions are always wholly masked. A Python TLS finding overlapping
a detected credential also receives whole-region masking, preserving the T031
overlap contract through scanner/source re-verification. Actual native AST ranges
convert UTF-16 to physical LF/CRLF code-point coordinates; emoji and logical LS
inside a physical line do not shift immutable evidence. No source snippets,
identifier values, credentials or arbitrary native messages leave the helper.

Producer checks: `python -m unittest discover -s tests -p test_security_adapter.py`.
Tests create real Git histories, verify fully masked proof and source round trips,
scan/no-write behavior, six-language literal contexts, config scopes, stale and
cropped evidence, strict limits/negative cases, and safe failing/duplicate delegate
composition. A timed isolated child checks malformed 2 KB/20 KB/65 KB PEM bodies;
the composed-provider regression checks that coordinator re-verification retains
whole-region masking for a non-security LOG001 finding overlapping an AWS secret.
T032 checks use `test_security_context.py` and opt-in `test_native_security.py`.
Native tests require an explicitly installed pinned frontend package and real
ScriptDom artifacts (`DEVSIFT_FRONTEND_PACKAGE`, `DEVSIFT_SQL_ARTIFACTS`); missing
requested tools fail rather than substituting a parser. Tests include actual
native safe/unsafe SQL controls, Git-verified masked SEC001, same-line emoji/LS
ranges, TLS literal types, shadow/rebinding counterexamples and no-source-write
checks. No C#/Go security-context capability is inferred from these tests.
Rollback is the scoped adapter/tests/docs commit revert.

## End-to-end security verification (T033)

`tests/test_security_end_to_end.py` invokes the actual CLI entrypoint in temporary
Git repositories, with isolated trusted Python import roots and bytecode writes
disabled. It does not replace the scanner, reporter, source verifier or native
provider with fabricated success. Source and all Git file bytes are hashed before
and after every CLI operation; scans/rendering/prompts never authorize edits.

The default group verifies PAT/AWS/PEM findings and a sensitive logging overlap
through the JSON envelope and its complete Findings JSON, Markdown and SARIF
documents. JSON source BEFORE and every SARIF physical snippet stay fully masked;
raw credential values/body fragments must be absent from stdout and stderr.
Canonical report-case review/implement prompts retain read-only/per-case approval
boundaries, pending approval and no automatic fix. These are the existing report
model fields, not a dependency on later case-prompt/approval modules.

Adversarial manifest schema keys/values and mismatched prompt approval arguments
exercise real CLI error streams without echoing sensitive input. Actual Git
classification proves unchanged legacy and novel new source origin while plain
`scan --security` deliberately retains UNKNOWN lifecycle. A malformed 20 KB PEM
candidate must complete a real CLI invocation within a bounded 15-second timeout
without inventing a credential finding or creating report files.

With `DEVSIFT_TEST_NATIVE=1`, an additional test requires a real installed pinned
frontend helper selected by `DEVSIFT_FRONTEND_PACKAGE` (and optional
`DEVSIFT_NODE_EXECUTABLE`). Missing requested dependencies fail, never silently
skip or substitute a simulated provider. The test serializes an explicit trusted
manifest from that actual factory and invokes real `ci --security --base` runs.
An actual SEC001 console finding and executed-target counts prove native AST work
occurred; builtin signature checks alone cannot satisfy the assertion.

The native fixture verifies legacy critical cases request independent review
without quality blocking (exit 2), and genuinely novel introduced cases block
(exit 1). Credential literals equal to schema words such as Critical/source/status
must have masked source snippets while legitimate schema keys and severity enums
remain intact. Both runs retain all three report formats and unchanged source/Git
state. Explicit setup/manifest files are outside the target repository and are
test preparation, not implicit scan writes or authorization to execute target code.

Run `python -m unittest discover -s tests -p test_security_end_to_end.py` for the
default group; set native opt-in and its real package path for the additional
native assertions. These checks prove the described bounded cases, not complete
secret detection, live credentials, arbitrary taint or runtime exploitability.
No HTTP/database connections, target imports/builds or remediation execute.
