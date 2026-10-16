"""Read-only release-candidate evidence check; never authorizes a release."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_package import PackageBuildError, verify_bundle
from tools.check_artifact_security import inspect_archive


_BLOCKERS = ["OWNER_LICENSE_APPROVAL_PENDING", "SIGNING_EVIDENCE_NOT_CHECKED",
             "HOSTED_CI_EVIDENCE_NOT_CHECKED", "RELEASE_REVIEW_REQUIRED"]


def check_release_readiness(bundle, *, source_sha, integrity_sha256):
    """Verify explicit bundle pins and inspect every declared ZIP without writes."""
    result = {"schema_version": "1", "source_sha": source_sha if isinstance(source_sha, str) else None,
              "checks": [], "missing_inputs": list(_BLOCKERS), "blockers": list(_BLOCKERS), "checks_complete": False,
              "release_ready": False, "publication_authorized": False,
              "checksums_authenticate": False}
    try:
        artifacts = verify_bundle(bundle, expected_source_sha=source_sha,
                                  expected_integrity_sha256=integrity_sha256)
        result["checks"].append({"name": "bundle_integrity_and_source_pin", "passed": True})
        integrity = json.loads((Path(bundle) / "integrity.json").read_bytes())
        archives = [a for a in artifacts if a.name.endswith(".zip")]
        security = []
        for artifact in archives:
            inspection = inspect_archive(str(Path(bundle) / artifact.name), expected_sha256=artifact.sha256)
            security.append({"name": artifact.name, "complete": inspection["complete"],
                             "issues": inspection["issues"]})
            if not inspection["complete"]:
                result["blockers"].append("ARCHIVE_SECURITY_INSPECTION_INCOMPLETE")
            if inspection["release_review_required"]:
                result["blockers"].append("ARCHIVE_REVIEW_REQUIRED")
        result["checks"].append({"name": "bounded_archive_security_inspection", "passed": bool(security) and all(x["complete"] for x in security),
                                 "archives": security})
        result["checks"].append({"name": "declared_component_count", "passed": len(security) == len(integrity["components"])})
        if len(security) != len(integrity["components"]):
            result["blockers"].append("DECLARED_COMPONENT_CHECK_FAILED")
        result["checks_complete"] = all(c["passed"] for c in result["checks"])
    except (PackageBuildError, OSError, ValueError, TypeError):
        result["checks"].append({"name": "bundle_integrity_and_source_pin", "passed": False,
                                 "issue": "BUNDLE_UNAVAILABLE_OR_PIN_MISMATCH"})
        result["blockers"].append("BUNDLE_VERIFICATION_FAILED")
    result["blockers"] = sorted(set(result["blockers"]))
    result["status"] = "checks_passed_release_blocked" if result["checks_complete"] else "incomplete"
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError()


def main(argv=None):
    try:
        parser = _Parser(description=__doc__, allow_abbrev=False)
        parser.add_argument("--bundle", required=True)
        parser.add_argument("--source-sha", required=True)
        parser.add_argument("--integrity-sha256", required=True)
        args = parser.parse_args(argv)
        result = check_release_readiness(args.bundle, source_sha=args.source_sha,
                                         integrity_sha256=args.integrity_sha256)
    except (ValueError, TypeError):
        result = {"schema_version": "1", "checks": [], "missing_inputs": list(_BLOCKERS), "blockers": ["INVALID_ARGUMENTS"],
                  "checks_complete": False, "release_ready": False, "publication_authorized": False,
                  "checksums_authenticate": False, "status": "incomplete"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["checks_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
