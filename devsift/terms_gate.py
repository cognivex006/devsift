"""In-process terms floor; serialized summaries never authorize a waiver."""
from datetime import datetime, timezone
from functools import lru_cache

from .output import result
from .terms import TermsAssessment, _catalog, assess_terms
from .terms_memory import read_history, repository_identity


@lru_cache(maxsize=8)
def _facts(assessment):
    if type(assessment) is not TermsAssessment:
        raise ValueError('Verified terms assessment required')
    wire = assessment.to_dict()
    return (wire['complete'], wire['enforced_count'], wire['status'],
            wire['decision_required'], len(wire['cases']), tuple(wire['errors']))


def assessment_for(root, assessment=None, *, catalog_path=None, catalog_digest=None):
    if assessment is None:
        return assess_terms(root, catalog_path=catalog_path, catalog_digest=catalog_digest)
    if type(assessment) is not TermsAssessment or assessment.repository_id != repository_identity(root):
        raise ValueError('Verified terms assessment required for this repository')
    return assessment


def source_record(record, assessment):
    """Recover source outcome only from a trusted in-process gated result.

    Report callers must supply the sealed assessment explicitly; imported JSON
    alone never supplies the terms authority or a source completeness override.
    """
    facts = _facts(assessment)
    data = dict(record['data'])
    summary = data.get('terms_gate')
    if summary is None:
        return {**record, 'data': data}
    if (type(summary) is not dict or summary.get('binding_digest') != assessment.binding_digest
            or type(data.get('source_analysis_complete')) is not bool
            or type(data.get('source_enforced_count')) is not int
            or data['source_enforced_count'] < 0):
        raise ValueError('Verified source outcome unavailable')
    complete = data['source_analysis_complete']
    enforced = data['source_enforced_count']
    for key in ('source_analysis_complete', 'source_enforced_count', 'terms_gate',
                'terms_compliance', 'terms_case_count', 'terms_blocked_count', 'total_case_count'):
        data.pop(key, None)
    codes = set(facts[5]) | {'TERMS_REVIEW_INCOMPLETE'}
    errors = [error for error in record['errors'] if error['code'] not in codes]
    return result(record['command'], complete=complete, enforced_count=enforced,
                  findings=record['findings'], errors=errors, data=data)


def apply_terms_gate(record, assessment, *, include_assessment=False):
    """Add the non-additive, unwaivable terms floor to a source result."""
    facts = _facts(assessment)
    source = source_record(record, assessment)
    data = dict(source['data'])
    errors = list(source['errors'])
    complete, blocks, status, decision_required, case_count, codes = facts
    if not complete:
        for code in codes or ('TERMS_REVIEW_INCOMPLETE',):
            if not any(item['code'] == code for item in errors):
                errors.append({'code': code, 'message':
                    'Third-party evidence or decision history is incomplete; inspect the terms report.'})
    data.update(source_analysis_complete=source['complete'],
                source_enforced_count=source['enforced_count'],
                terms_gate={'binding_digest': assessment.binding_digest, 'complete': complete,
                            'enforced_count': blocks, 'status': status,
                            'decision_required': decision_required},
                terms_case_count=case_count, terms_blocked_count=blocks,
                total_case_count=data.get('finding_count', len(source['findings'])) + case_count)
    if include_assessment:
        data['terms_compliance'] = assessment.to_dict()
    return result(source['command'], complete=bool(source['complete'] and complete),
                  enforced_count=source['enforced_count'] + blocks,
                  findings=source['findings'], errors=errors, data=data)


def changed_record(root, assessment, *, catalog_path=None, catalog_digest=None):
    """A concurrent terms/use/history change requires a fresh session."""
    current = assess_terms(root, catalog_path=catalog_path, catalog_digest=catalog_digest)
    if current.binding_digest == assessment.binding_digest:
        return None
    return result('scan', complete=False, errors=[{
        'code': 'TERMS_INPUT_CHANGED',
        'message': 'Terms evidence, inventory or owner history changed during execution; start a fresh assessment.'}],
        data={'targets': [], 'terms_input_changed': True})


def gated_records(root, records, assessment, *, catalog_path=None, catalog_digest=None):
    iterator = iter(records)
    command = 'scan'
    try:
        for record in iterator:
            command = record['command']
            yield apply_terms_gate(record, assessment)
        changed = changed_record(root, assessment, catalog_path=catalog_path, catalog_digest=catalog_digest)
        if changed is not None:
            changed['command'] = command
            yield apply_terms_gate(changed, assessment)
    finally:
        if hasattr(iterator, 'close'):
            iterator.close()


def readiness(root, *, catalog_path=None, catalog_digest=None):
    """Validate configuration/history only; no inventory or use assessment."""
    errors = []
    data = {'analysis_performed': False, 'assessment_performed': False,
            'catalog_supplied': catalog_path is not None or catalog_digest is not None,
            'catalog_configuration_valid': None, 'decision_history_readable': False,
            'limitations': ['Configuration readiness is not a terms compliance assessment.',
                            'No policy fetching, dependency installation or project writes performed.']}
    try:
        history = read_history(root)
        data.update(decision_history_readable=True, history_revision=history.revision,
                    recorded_decisions=len(history.events))
    except (OSError, ValueError):
        errors.append('TERMS_HISTORY_UNAVAILABLE')
    if data['catalog_supplied']:
        try:
            _, _, fresh = _catalog(catalog_path, catalog_digest, datetime.now(timezone.utc))
            data['catalog_configuration_valid'] = bool(fresh)
            if not fresh:
                errors.append('TERMS_CATALOG_STALE')
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            data['catalog_configuration_valid'] = False
            errors.append('TERMS_CATALOG_INVALID')
    return data, errors


def attach_readiness(record, root, *, catalog_path=None, catalog_digest=None):
    data, codes = readiness(root, catalog_path=catalog_path, catalog_digest=catalog_digest)
    return result(record['command'], complete=bool(record['complete'] and not codes),
                  enforced_count=record['enforced_count'], findings=record['findings'],
                  errors=[*record['errors'], *({'code': code, 'message':
                    'Terms configuration or owner history is unavailable; no compliance assessment was performed.'}
                    for code in codes)], data={**record['data'], 'terms_governance': data})
