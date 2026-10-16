# Release preparation checklist

This checklist records release evidence to gather. Items below are unchecked
because this task prepares documentation only. Checking a box requires current,
reviewable evidence for the intended release candidate and owner authorization.

## Candidate and source identity

- [ ] Select a release version and source commit through the authorized owner
  process; keep `pyproject.toml`'s current `0.0.0.dev0` until that decision.
- [ ] Confirm the reviewed commit, clean selected package inputs, and exact
  component manifest using `packaging/manifest.json` and
  `tools/package_manifest.py`.
- [ ] Build and verify all four source ZIP components from the trusted source:
  `devsift-core-wheel-source.zip`, `devsift-core-sdist-source.zip`,
  `devsift-consumer-skill.zip`, and `devsift-source-assets.zip`. Record the
  source SHA and independently held integrity SHA256.
- [ ] Complete the planned T072 four-component dry run and retain its evidence.

## Dependencies, SBOM, and license evidence

- [ ] Prepare a release-specific SBOM from the actual candidate artifacts and
  their canonical input manifests. Do not describe this checklist as an SBOM
  or as completed component/license analysis.
- [ ] Reconcile component inputs against the canonical files: `pyproject.toml`
  and `packaging/manifest.json`; `native/dotnet/DevSift.Roslyn.csproj` and
  `native/dotnet/global.json`; `native/sql/DevSift.Sql.csproj`,
  `native/sql/global.json`, and `native/sql/packages.lock.json`;
  `native/go/go.mod`; and `native/frontend/package.json` plus
  `native/frontend/package-lock.json`. Derive versions and dependency scope from
  these files at release time; do not create a second version source here.
- [ ] Record Python package version `0.0.0.dev0` and empty runtime dependency
  list as current metadata, with setuptools `83.0.0` as the pinned build
  requirement. The build backend is not a Python runtime dependency.
- [ ] Resolve license identifiers and notices for the actual shipped
  components and dependencies. Current project license decision is pending;
  preserve unknown/not-determined values as `NOASSERTION` where the chosen SBOM
  format defines that value. This records uncertainty and is not legal approval.
- [ ] Obtain owner-selected project license and approval before adding license
  declarations or treating a license review as complete. `license-files = []`
  does not select a license or grant rights.

## Artifact and release verification

- [ ] Review artifact member lists and hashes against the trusted manifest and
  source commit; retain independent verification evidence.
- [ ] Run the documented bounded archive inspection and investigate every
  finding or incomplete result. It does not inspect nested archives, compiled
  binaries, license suitability, or all release policies.
- [ ] Complete and record relevant CI, test, install, and rollback checks for
  the actual candidate. A passing selected-bundle check alone is not release
  readiness.
- [ ] Obtain and verify required signing evidence and release-owner review.
- [ ] Confirm `release_ready` and publication authorization through the
  authorized release process; the readiness checker itself always leaves both
  false.
- [ ] Only after all decisions and evidence are approved, prepare final release
  notes from [RELEASE-DRAFT.md](RELEASE-DRAFT.md) and perform separately
  authorized versioning, tagging, and publication.

## Component boundaries to retain in release materials

The four manifest components are the core wheel source inputs, core sdist source
inputs, consumer skill, and native/helper source assets. Source ZIPs are not
installable wheels or precompiled native distributions. The core wheel has no
bundled native toolchain, Roslyn, ScriptDom, npm/node_modules, or third-party
binaries, and does not guarantee offline analyzer availability. Report claims
must match the specific command and available analyzer; unavailable analysis
remains incomplete.
