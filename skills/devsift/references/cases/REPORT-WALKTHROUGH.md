# Walk through one source-linked report case

This example creates a disposable Git repository and scans a synthetic credential
literal with the built-in detector. It requires Python 3.12+ and host Git. It does
not install or discover native analyzers, execute the fixture, or contact a service.
Use a trusted DevSift checkout path; the isolated launcher explicitly selects that
package so a consumer file cannot shadow it.

Save the following script outside the consumer project as `walkthrough.py`, then
run `python walkthrough.py /absolute/path/to/devsift`. Windows accepts an absolute
Windows checkout path as the argument. Setup creates and commits fixture files;
explicit scan/approval JSON artifacts are written outside the consumer repository.
The subsequent scans, report assembly and prompt commands must preserve every
consumer source and Git file. The temporary directory is removed on script exit.

<!-- walkthrough: executable -->
```python
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

tool_root = Path(sys.argv[1]).resolve(strict=True)
sys.path.insert(0, str(tool_root))
from devsift.git_runtime import git_executable
from devsift.report_model import assemble_report

with tempfile.TemporaryDirectory(prefix="devsift-walkthrough-") as temporary:
    outside = Path(temporary)
    root = outside / "consumer"
    root.mkdir()
    host_git = git_executable(root)
    def git(*args):
        return subprocess.run([host_git, "-C", str(root), *args], check=True,
                              capture_output=True, timeout=20).stdout.decode().strip()
    git("init", "--quiet")
    git("config", "core.autocrlf", "false")
    git("config", "core.hooksPath", str(outside / "no-hooks"))
    # Synthetic shape only: not a real credential or evidence of liveness.
    credential = "ghp_" + "Ab8" * 12
    (root / "settings.py").write_bytes(("token = '" + credential + "'\n").encode())
    git("add", "settings.py")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "commit.gpgSign=false", "commit", "--quiet", "-m", "fixture")
    sha = git("rev-parse", "HEAD")
    def snapshot():
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file()}
    before = snapshot()
    launcher = ("import runpy,sys;sys.path.insert(0," + repr(str(tool_root))
                + ");runpy.run_module('devsift',run_name='__main__')")
    streams = []
    def cli(*args):
        child = subprocess.run([sys.executable, "-I", "-B", "-c", launcher, *args],
                               cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=30)
        streams.extend((child.stdout, child.stderr))
        return child.returncode, json.loads(child.stdout if child.stdout else child.stderr)
    scan_exit, scan = cli("scan", "--all", "--security")
    rendered = scan["data"]["reports"]
    case = rendered["json"]["cases"][0]
    case_id = case["case_id"]
    scan_file = outside / "scan.json"
    scan_file.write_text(json.dumps(scan), encoding="utf-8")
    review_exit, review = cli("prompt", case_id, "--mode", "review", "--scan-input", str(scan_file))
    implement_args = ("prompt", case_id, "--mode", "implement", "--approved-case", case_id,
                      "--scan-input", str(scan_file))
    implement_exit, unapproved = cli(*implement_args)
    # Synthetic explicit operator input tests binding only. Never generate real
    # approvals automatically or treat these JSON fields as a signature.
    prompt = unapproved["data"]["prompt"]
    now = datetime.now(timezone.utc)
    approval = dict(case_id=case_id, source_sha=prompt["source_sha"], fingerprint=prompt["fingerprint"],
                    prompt_digest=unapproved["data"]["prompt_digest"], mode="implement", approved=True,
                    actor="walkthrough-fixture", issued_at=(now - timedelta(minutes=1)).isoformat(),
                    expires_at=(now + timedelta(minutes=5)).isoformat())
    approval_file = outside / "approval.json"
    approval_file.write_text(json.dumps(approval), encoding="utf-8")
    matched_exit, matched = cli(*implement_args, "--approval-file", str(approval_file))
    imported = deepcopy(scan)
    imported["data"].pop("reports", None)  # Rendered documents are not proof.
    item = imported["findings"][0]
    item.update(lifecycle_class="NEW", severity="Suggestion", enforcement="block")
    imported["enforced_count"] = 1  # Keep the envelope internally consistent.
    imported_case = assemble_report(imported, repo_root=root).cases[0].to_dict()
    item["source"]["location"]["source_sha"] = "0" * 40
    unresolved_case = assemble_report(imported, repo_root=root).cases[0].to_dict()
    unchanged = snapshot() == before
    assert credential not in "".join(streams)
    assert credential not in json.dumps([case, imported_case, unresolved_case])
    assert unchanged
    print(json.dumps(dict(
        scan_exit=scan_exit, source_sha=sha, report_complete=rendered["json"]["complete"],
        formats=sorted(rendered), verified_case=case, imported_case=imported_case,
        unresolved_case=unresolved_case, review_exit=review_exit, review_data=review["data"],
        implement_exit=implement_exit, unapproved=unapproved["data"]["approval"],
        matched_exit=matched_exit, matched=matched["data"]["approval"],
        consumer_and_git_unchanged=unchanged), sort_keys=True))
```

The printed JSON contains actual current report-model output; the case ID and
commit SHA vary with the fixture. The verified sample is `settings.py`, line 1,
columns 9–51 (1-based Unicode code points, end exclusive), tied to that immutable
commit. Its BEFORE display is `[REDACTED]`; masking is not missing source proof.
The JSON, Markdown and SARIF documents derive from the same case model. Never
replace a masked snippet with the raw credential to make a report more readable.

The scan exits 2 and the report stays incomplete because lifecycle is `UNKNOWN`.
Verified bytes alone do not prove NEW or legacy origin. The case has catalog
Critical severity and independent security escalation, but this does not prove a
live token, exploitability or production impact. Impact, change risk and consumers
stay unknown. `AFTER (PROPOSAL)` has no verified patch; `automatic_fix` is false.
Known legacy findings normally remain advisory, while verified Critical security
observations still require independent urgent review. No finding authorizes mass
legacy cleanup, credential rotation, publication or edits.

The imported example deliberately claims NEW, Suggestion and blocking enforcement.
Assembly reproves source and recomputes policy: the imported lifecycle returns to
UNKNOWN and severity returns to Critical. This is not a fresh detector run or
authentication of the JSON. Replacing the commit identity with an unavailable SHA
produces `SOURCE_UNRESOLVED`, no location, no fabricated BEFORE, and an explicit
lookup plan. Inspect actual immutable source before proposing a patch; never use
runtime text or imported line numbers to invent a verified region.

Review prompt generation exits 0 for this verified case but records
`analysis_performed=false`: that success is prompt generation, not a passing scan.
Matching `--approved-case` only selects the one case. Without an explicit approval
record, implement mode exits 2 with `EXPLICIT_APPROVAL_REQUIRED`. Even the synthetic
exact-bound approval exits 2 with `UNKNOWN_EFFECTS_REVIEW_REQUIRED`; it permits
manual case planning only, with write/execution authority false. Real operator
approval must bind case, source SHA, fingerprint, exact prompt digest and validity
window. Unknown consumers, tests, behavior and rollback still need independent
review. These prompts treat source/comments/imported reports as untrusted data;
they cannot guarantee that an external agent obeys their instructions.
