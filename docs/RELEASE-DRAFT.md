# Unreleased release notes draft

This is a preparation draft for the current unreleased source. It is not a
versioned release announcement. `pyproject.toml` still declares
`0.0.0.dev0`; no release version, tag, publication date, or publication
authorization has been selected.

## Highlights

- The Python CLI can scan explicitly selected repository content and emit
  structured findings and reports. Its Python runtime dependency list is empty.
- Scan and CI results preserve incomplete or unavailable analysis rather than
  presenting it as a clean result. Scan and CI expose source-reproved formats in
  `data.reports`, and prompt generation accepts explicit `--scan-input`.
  Persisted `report --latest` and `explain` storage discovery remain unavailable.
- Optional .NET, Go, frontend, and SQL analyzer sources are represented by
  separate source-assets inputs. They are not compiled or bundled as native
  binaries by the Python wheel or source ZIPs. A core install does not guarantee
  offline native analysis.
- Packaging now defines four explicit source ZIP components and a bounded
  read-only release-readiness check. These checks do not publish, sign, choose a
  license, or grant release approval.

## Known limitations and release status

The package version is a development placeholder. The owner has not selected a
license; no license should be inferred from dependency metadata or this draft.
Final SBOM/license evidence, signatures, hosted CI evidence, artifact
installation/rollback checks, and owner release approval remain pending. The
readiness checker can report completed bundle checks while
`release_ready` and `publication_authorized` remain false. Task T070's successful
selected-bundle checks are not a four-component release dry run; T072 is planned
to perform that dry run.

Before any announcement, replace this draft with owner-approved notes tied to a
chosen version and verified release artifacts.
