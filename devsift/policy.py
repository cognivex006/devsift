"""Strict, deterministic policy resolution and evidence-aware enforcement.

Source classification and verification are upstream responsibilities. This module
never reads Git or modifies sources, baselines, or policy files.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path

from .registry import RULES, Severity


class PolicyError(ValueError):
    """Invalid policy or decision input; callers must treat this as failure."""


_DEFAULTS = {
    "schema_version": "1",
    "quality_gate": {"block_on": ["Critical", "Error"]},
    "legacy_mode": "recommend",
    "rules": {},
}
_LIFECYCLES = frozenset({"NEW", "MODIFIED_INTRODUCED", "MODIFIED_PREEXISTING",
                         "LEGACY_UNCHANGED", "UNKNOWN"})


def _object(value, allowed, location):
    if not isinstance(value, dict):
        raise PolicyError(f"{location} must be an object")
    if any(key not in allowed for key in value):
        raise PolicyError(f"{location} contains unknown keys")


def _validate(layer):
    _object(layer, _DEFAULTS, "policy")
    if "schema_version" in layer and layer["schema_version"] != "1":
        raise PolicyError("schema_version must be '1'")
    if "legacy_mode" in layer and layer["legacy_mode"] != "recommend":
        raise PolicyError("legacy_mode must be 'recommend'")
    if "quality_gate" in layer:
        gate = layer["quality_gate"]
        _object(gate, {"block_on"}, "quality_gate")
        if "block_on" in gate:
            values = gate["block_on"]
            if (not isinstance(values, list)
                    or any(value not in ("Critical", "Error") for value in values)
                    or len(values) != len(set(values))):
                raise PolicyError("block_on must list unique Critical/Error values")
    if "rules" in layer:
        _object(layer["rules"], RULES, "rules")
        for rule_id, override in layer["rules"].items():
            _object(override, {"severity"}, f"rules.{rule_id}")
            if "severity" in override and override["severity"] not in tuple(Severity):
                raise PolicyError(f"rules.{rule_id}.severity is unsupported")


def _merge(target, layer):
    for key, value in layer.items():
        if isinstance(value, dict):
            _merge(target.setdefault(key, {}), value)
        else:
            target[key] = deepcopy(value)


def resolve_policy(repo=None, overlay=None):
    """Validate each partial layer before merging defaults → repo → overlay.

    Objects merge recursively; arrays replace. None means an absent layer.
    Every call returns a fresh independent full policy object.
    """
    result = deepcopy(_DEFAULTS)
    for layer in (repo, overlay):
        if layer is not None:
            _validate(layer)
            _merge(result, layer)
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError("policy JSON contains duplicate keys")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise PolicyError("policy JSON contains a non-finite constant")


def load_policy(path, overlay=None):
    """Load one explicit UTF-8 JSON file; no discovery or filesystem writes."""
    try:
        layer = json.loads(Path(path).read_text(encoding="utf-8"),
                           object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PolicyError("cannot read valid UTF-8 policy JSON") from exc
    _validate(layer)  # JSON null is invalid, even though None can mean absent.
    return resolve_policy(layer, overlay)


@dataclass(frozen=True)
class Decision:
    rule_id: str
    severity: Severity
    lifecycle_class: str
    enforcement: str
    security_escalation: bool


def decide(rule_id, lifecycle_class, *, source_verified, policy=None):
    """Evaluate supplied evidence; never infer a source lifecycle or approval.

    Critical security escalation uses catalog criticality as a floor, so a local
    severity override cannot suppress the independent security review workflow.
    """
    if not isinstance(rule_id, str) or rule_id not in RULES:
        raise PolicyError("unknown rule ID")
    if not isinstance(lifecycle_class, str) or lifecycle_class not in _LIFECYCLES:
        raise PolicyError("unknown lifecycle class")
    if type(source_verified) is not bool:
        raise PolicyError("source_verified must be boolean")
    resolved = resolve_policy(policy)
    rule = RULES[rule_id]
    severity = Severity(resolved["rules"].get(rule_id, {}).get("severity", rule.severity))
    escalation = (source_verified and rule.security
                  and (rule.severity == Severity.CRITICAL or severity == Severity.CRITICAL))
    if lifecycle_class == "UNKNOWN" or not source_verified:
        enforcement = "incomplete"
    elif lifecycle_class in {"NEW", "MODIFIED_INTRODUCED"}:
        enforcement = "block" if severity in resolved["quality_gate"]["block_on"] else "advisory"
    else:
        enforcement = "security_review" if escalation else "advisory"
    return Decision(rule_id, severity, lifecycle_class, enforcement, escalation)


def gate_result(decisions):
    """Summarize findings only, not analyzer execution completeness or exit code.

    A caller must separately account for failed/unavailable analyzers. Security
    escalation flags remain available on every individual decision.
    """
    statuses = set()
    for decision in decisions:
        if not isinstance(decision, Decision) or decision.enforcement not in {
            "block", "incomplete", "security_review", "advisory"
        }:
            raise PolicyError("invalid enforcement decision")
        statuses.add(decision.enforcement)
    for status in ("block", "incomplete", "security_review"):
        if status in statuses:
            return status
    return "pass"
