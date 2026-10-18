# JSON and SARIF report exports

`devsift.report_export.render_json(report)` and `render_sarif(report)` accept only
the sealed `Report` model and return deterministic JSON strings. They use the
standard library and perform no source reads, network calls, installation, writes
or remediation. Invalid/unsupported input and output over 16,000,000 UTF-8 bytes
raise static ExportError, never a truncated document. Runtime package dependencies
remain empty.

These are individual document limits. The CLI starting in 0.1.15 creates adaptive
source-reproved pages plus a complete index/checksums instead of imposing these
limits on the entire repository or finding collection. Each page also includes
bounded `scan.json` for an explicit case prompt. See [complete scans](../COMPLETE-SCANS.md).

JSON preserves the complete model, including every case, evidence, unknown risk,
pending proposal, full prompts and execution errors. No re-masking of model
constants or reconstruction from untrusted findings occurs. Existing whole-region
security masks remain intact. Nonempty contextual recommendation data currently
fails closed until the separately approved contextual integration is available;
it is not silently dropped from an export.

SARIF uses version 2.1.0 and `columnKind: unicodeCodePoints`. Verified locations
preserve physical one-based start/end coordinates with exclusive end and the
already-redacted selected-region snippet. Artifact URIs are encoded **relative
proven source paths**, with immutable source SHA/repository properties. No working
directory base URI or current-checkout/commit equivalence is invented. Consumers
must view the indicated immutable revision to interpret those locations. The
only navigation URL retained is the accepted model's explicitly proven mapping.
Unresolved source has no physical location, guessed path/line/URL or fingerprint;
its source status, lookup plan and runtime evidence remain in result properties.
Related locations are emitted only for actually VERIFIED related evidence.

Critical/Error map to SARIF error, Warning to warning, Suggestion to note. The
original severity, enforcement, lifecycle and security-escalation flag remain
explicit in the complete case properties. Enforced blocks use result kind fail;
other results use review, never a fabricated pass. UNKNOWN is not converted to a
baselineState assertion. Only an existing known raw-region fingerprint is emitted
in partialFingerprints. No automatic fixes are generated from uncertain proposals.

Invocation executionSuccessful reflects analysis completeness, independently of
whether a completed quality gate found enforced violations. An incomplete run is
false even if other findings block. Report exit/status/count and static execution
notifications remain explicit. No invocation command line, timestamps or native
tool versions are guessed.

## Explicit offline validation setup

Development/CI validation uses fully pinned wheel hashes from official PyPI release
metadata in `requirements-dev.txt`, including transitive dependencies and all
published platform wheel hashes for those exact releases. Installation is explicit:

```text
python -m pip install --require-hashes --only-binary=:all: -r requirements-dev.txt
python tools/setup_validation.py
```

The setup script alone may access the network. It downloads the official OASIS
SARIF 2.1.0 Draft 4 schema from a fixed repository commit, verifies exact byte
length and SHA256 before saving an ignored local cache. An existing matching
cache avoids downloading. Export, scanning and validation never invoke setup or
fetch schemas. No third-party schema is vendored into Git.

- [Official pinned OASIS schema](https://raw.githubusercontent.com/oasis-tcs/sarif-spec/1742a253eb654bf8a4ed7c60eaef7412b2c23553/sarif-2.1/schema/sarif-schema-2.1.0.json)
- Bytes: 112768
- SHA256: `c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e`
- Cache: `.devsift/local/schemas/sarif-2.1.0.json`

Normal exporter tests require only the runtime standard library. Set
`DEVSIFT_TEST_SCHEMA=1` to require actual jsonschema validation and the verified
official cache. Missing dependencies/cache fail under opt-in, rather than skip.
Own report JSON uses Draft 2020-12 with an offline registry for
`urn:devsift:evidence:1`. SARIF uses the actual official Draft 4 validator, including
URI/URI-reference checks via the pinned rfc3986-validator development dependency.
Both workflows install the hashed binary-only dev lock, run explicit schema setup
and enable schema tests on Windows/Linux Python 3.12.

Tests use real temporary Git proof for Unicode columns, full JSON fidelity,
verified/unresolved source, all four severity mappings, whole HC002 and overlapping
nonsecurity masks, incomplete execution, deterministic output and unchanged
source/.git bytes. Actual official-schema corruption negatives reject invalid
versions, levels, columns, zero lines, URI formats and nonboolean execution status.
Validation runs with network functions blocked; mismatched schema downloads cannot
become a trusted cache. Structural schema validity does not establish source proof
or attribution authority; the accepted model remains the prerequisite.
