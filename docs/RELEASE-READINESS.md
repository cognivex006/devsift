# Release-candidate readiness check

`tools/check_release_readiness.py` is a bounded, read-only composition of the
source-bundle verifier and artifact security inspector. It requires an explicit
bundle directory, full source commit SHA and independently trusted SHA256 of
`integrity.json`:

```text
python -B tools/check_release_readiness.py --bundle <absolute-bundle-directory> --source-sha <trusted-commit-sha> --integrity-sha256 <trusted-integrity-sha256>
```

The verifier checks the expected source identity, integrity digest, all bundle
checksums, archive bytes and declared members without extracting them. Each
archive then receives the existing bounded ZIP text/known-shape inspection.
The output distinguishes completed checks from release blockers. Even when all
checks complete, the result says `checks_passed_release_blocked`, keeps
`release_ready` and `publication_authorized` false, and lists owner license
approval, signing evidence, hosted CI evidence and release review as pending.
License approval is currently unresolved; this tool does not select a license
or infer owner approval.

The source SHA identifies Git objects and the expected integrity digest binds
bundle bytes only when both values are independently trusted by the caller.
Checksums do not authenticate an origin, reviewer or publisher. A clean scoped
archive inspection covers supported ZIP text and recognized sensitive shapes;
it does not inspect nested archives, compiled files, license suitability,
signatures, native availability or every release policy. No finding does not
grant approval. This command does not build, install, execute, download, sign,
publish, tag or change a version, and its result grants no publication
authority.
