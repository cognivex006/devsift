# Getting started

DevSift analyzes source read-only and reports evidence for human review. Python 3.12+ is required. No public package release or owner-selected license is currently declared; these instructions install from an explicitly trusted checkout.

## Install the trusted tooling first

From the DevSift checkout, create a virtual environment and install the CLI:

```sh
python -m venv .venv
```

On Windows PowerShell:

```powershell
.venv\Scripts\python.exe -m pip install .
```

On Linux/macOS:

```sh
.venv/bin/python -m pip install .
```

Installation may fetch the pinned build backend and writes packaging/environment files. It is a separate setup step; it does not analyze or build a consumer application. The runtime has no third-party Python dependencies. Native helpers have their own explicit [trusted setup](NATIVE-SETUP.md); they are not installed during a scan.

Install both `SKILL.md` and `CONSUMER-SCOPE.md` from `skills/devsift/` in your host's skill directory. Pip installs the CLI, not those skill files. Host registration differs; DevSift does not supply or prove an automatic host API. Keep the trusted Python environment accessible when using the skill.

## Run from the consumer Git root

Use the interpreter containing that installation (activate its environment, or use its absolute path). In the following commands, `python` means that trusted interpreter:

```sh
python -I -B -m devsift --help
python -I -B -m devsift doctor
python -I -B -m devsift scan --changed
```

`-I` prevents consumer module shadowing; `-B` prevents bytecode writes. Doctor inventories availability and validates explicitly supplied configuration. It installs nothing and is not a source scan. Without configured native providers, ordinary scans remain incomplete. An empty finding list is insufficient evidence of a clean analysis.

For explicit native analysis, obtain an absolute trusted manifest and its SHA256 independently, then replace both placeholders:

```sh
python -I -B -m devsift scan --changed --native-manifest /absolute/trusted-tools.json --native-manifest-digest <trusted-sha256>
```

Native configuration authorizes only the specified hash-pinned tool processes. It is not permission to execute the consumer application, fetch dependencies, or apply findings. See [CLI behavior](CLI.md) and [security coverage](SECURITY-ANALYSIS.md). `--security` adds bounded credential and supported context detectors; missing language coverage still cannot become a pass.

## New work and an existing codebase

| Situation | Starting command | What it establishes |
| --- | --- | --- |
| Current development changes | `python -I -B -m devsift scan --changed` | Staged, unstaged and untracked path selection; current working bytes |
| Existing repository inventory | `python -I -B -m devsift scan --all --legacy-mode recommend` | All selected source; recommendations for unchanged legacy |
| Committed CI change | Follow [CI gate setup](CI-GATE.md) | Fresh analysis with explicit tool trust and immutable Git provenance |

Changed paths do not establish a finding's origin. A verified location proves matching immutable source, while lifecycle, regression behavior, consumer impact and business effects may remain UNKNOWN. New blocking findings need supported provenance and policy. Unchanged legacy is not permission for a broad refactor; Critical security escalation remains independent of ordinary quality thresholds. Gradually review recommendations and approved case scopes rather than enforcing unproved history.

## Interpret the result before acting

| Exit | Meaning |
| --- | --- |
| 0 | Completed command according to that command's scope; help and prompt generation are not scan passes |
| 1 | Complete analysis with verified enforced violations |
| 2 | Incomplete analysis, missing capability or outstanding review |
| 3 | Invalid command or approval arguments |

Incomplete takes precedence over enforced findings. Process security-review flags even when a complete legacy analysis returns 0. The JSON envelope distinguishes command, completeness, findings and errors; `data.reports` contains selected JSON, Markdown and SARIF documents. Scan commands do not save those documents automatically. Shell redirection is an operator-controlled write: choose an output outside the consumer source and handle sensitive artifacts appropriately.

Use [the executable report walkthrough](cases/REPORT-WALKTHROUGH.md) to distinguish VERIFIED source from unresolved navigation and untrusted imported lifecycle claims. Source snippets are redacted; never interpret a masked match as proof that a credential is live or that a business effect is known.

## Review one case

Save an explicit scan envelope outside source, then select a real case ID from it:

```sh
python -I -B -m devsift prompt CASE-1 --mode review --scan-input /absolute/scan.json
```

Review generation succeeds only with reproved source; it performs no new scan. `report --latest` and `explain` storage discovery are unavailable. Implementation proposals require an explicit matching selector and a separately supplied case-bound operator record; a selector alone grants no authorization. Even a matching record with unknown effects permits manual planning only. No CLI command applies source edits. See [case prompts and approval](CASE-PROMPTS.md) for the actual record format and denial conditions.

Project-policy discovery and the separate security escalation library are documented in [project policy](PROJECT-POLICY.md) and [security gate](SECURITY-GATE.md). These library entry points are not automatic CLI configuration discovery. Start from [development](../DEVELOPMENT.md) for changing the tooling itself.
