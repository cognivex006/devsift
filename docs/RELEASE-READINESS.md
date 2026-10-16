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

The canonical candidate dependency/input sources are `pyproject.toml`,
`packaging/manifest.json`, and the component-specific native project and lock
files listed in [RELEASE-CHECKLIST.md](RELEASE-CHECKLIST.md). A release-specific
SBOM and license evidence still need to be prepared from the actual candidate;
this readiness check does not generate either. Preserve `NOASSERTION` for a
license value that has not been determined in an SBOM format that supports it.
That value reports uncertainty and does not constitute approval.

The Python project currently declares version `0.0.0.dev0`, no runtime
dependencies, and setuptools `83.0.0` as its build requirement. Those facts do
not represent the native source asset dependency graph. Use the checked-in
NuGet, Go, and npm project/lock inputs for those components rather than copying
dependency versions into this document. `0.0.0.dev0` is a PEP 440 development
placeholder, not the owner-selected software release version. Select a
software-facing version under [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html)
through the authorized owner process; Specification v6 is not a software release.

Use identifiers or expressions from the official
[SPDX License List specification](https://spdx.github.io/spdx-spec/v2.3.1/)
only after the owner decision and component evidence support them. The project
license remains unselected. Where an SBOM format permits `NOASSERTION`, it may
record an unknown value; it is not approval or a substitute for legal review.

The source SHA identifies Git objects and the expected integrity digest binds
bundle bytes only when both values are independently trusted by the caller.
Checksums do not authenticate an origin, reviewer or publisher. A clean scoped
archive inspection covers supported ZIP text and recognized sensitive shapes;
it does not inspect nested archives, compiled files, license suitability,
signatures, native availability or every release policy. No finding does not
grant approval. This command does not build, install, execute, download, sign,
publish, tag or change a version, and its result grants no publication
authority.

T072's local dry-run uses actual temporary Git commits and all four manifest
components. It verifies the four source ZIPs with independently held fixture
pins, repeats the build to compare bundle bytes, runs the readiness composition,
and checks source/bundle snapshots around read-only operations. Run it with:

```text
python -B -m unittest discover -s tests -p test_release_dry_run.py -v
```

This is fixture evidence for the accepted source-bundle format. The
`core-wheel-source.zip` is source input, not a built wheel; the dry run does not
run pip, build a wheel/sdist, or prove install/rollback. It does not establish
that the live integration candidate was reviewed or clean, and does not prepare
an SBOM, select or approve a license, prove signatures or hosted CI, or authorize
publication. Source assets remain subject to every conservative inspection
finding; no finding is suppressed to obtain a completed result.

The T072 fixture currently produces `RECOGNIZED_SENSITIVE_SHAPE` on the two core
source archives and source-assets archive. Their digest-bound inspections ran,
but these findings keep the aggregate readiness result incomplete and require
review. The test asserts this observed result rather than masking it. The
separate accepted T054 tests established actual installation and explicit
rollback for their tested implementation and fixtures; this T072 test adds no
pip, native build, install, or rollback evidence. For an owner-selected future
candidate or changed assets, obtain candidate-matched release evidence.

See [RELEASE-DRAFT.md](RELEASE-DRAFT.md) for non-final notes and
[RELEASE-CHECKLIST.md](RELEASE-CHECKLIST.md) for separate candidate and release
evidence requirements.
