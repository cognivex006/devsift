"""Explicit terms study/report and owner-attributed decision operations."""
from pathlib import Path
import re

from .output import result
from .terms import assess_terms
from .terms_gate import apply_terms_gate
from .terms_memory import TermsMemoryError, read_history, record_decision


def add_catalog_options(parser):
    parser.add_argument('--terms-catalog', help='Explicit absolute operator-reviewed local terms catalog; no automatic trust.')
    parser.add_argument('--terms-catalog-digest', help='Independently trusted SHA256 of the selected catalog bytes.')


def add_terms_command(commands):
    terms = commands.add_parser('terms', help='Offline third-party terms checks and durable owner decisions.')
    actions = terms.add_subparsers(dest='terms_action', required=True)
    check = actions.add_parser('check', help='Assess local terms evidence and deliver complete reports without native analyzers.')
    add_catalog_options(check)
    storage = check.add_mutually_exclusive_group()
    storage.add_argument('--report-dir', help='New absolute owned report directory outside source.')
    storage.add_argument('--resume', help='Resume only when terms/evidence/history/configuration still match.')
    check.add_argument('--summary', action='store_true')
    check.add_argument('--report-format', action='append', choices=('json', 'markdown', 'sarif'))
    check.add_argument('--report-language', choices=('en', 'th'), default='en')
    check.set_defaults(all=True, security=False, native_manifest=None,
                       native_manifest_digest=None, legacy_mode='recommend')
    actions.add_parser('history', help='Read verified append-only history; never creates or changes it.')
    decide = actions.add_parser('decide', help='Record an explicit actual-owner answer; never waive a serious block.')
    add_catalog_options(decide)
    decide.add_argument('case_id')
    decide.add_argument('--choice', required=True, choices=('remediate', 'decline', 'reconsider', 'resolved'))
    decide.add_argument('--owner', required=True, help='Actual owner attribution; this text is not authentication.')
    decide.add_argument('--reason', required=True, help='Explicit owner rationale, not an agent-invented answer.')
    decide.add_argument('--fingerprint', required=True, help='Current exact case fingerprint from a reviewed report.')
    decide.add_argument('--evidence-digest', required=True, help='Current exact evidence digest from that report.')
    decide.add_argument('--supersedes', help='Exact prior event ID; required for reconsideration.')


def validate_catalog_options(args):
    path, digest = getattr(args, 'terms_catalog', None), getattr(args, 'terms_catalog_digest', None)
    return ((path is None and digest is None) or
            (type(path) is str and Path(path).is_absolute() and type(digest) is str
             and re.fullmatch(r'[0-9a-f]{64}', digest) is not None))


def _failure(code, message, *, assessment=None):
    record = result('terms', complete=False, errors=[{'code': code, 'message': message}],
                    data={'analysis_performed': False, 'source_analysis_performed': False,
                          'terms_assessment_performed': assessment is not None, 'decision_recorded': False})
    return apply_terms_gate(record, assessment, include_assessment=True) if assessment is not None else record


def run_owner_command(args):
    root = Path.cwd()
    if args.terms_action == 'history':
        try:
            history = read_history(root)
            return result('terms', complete=True, data={'operation': 'history', 'analysis_performed': False,
                'repository_id': history.repository_id, 'history_revision': history.revision,
                'decisions': list(history.events), 'authority': 'Owner attribution, not authentication or permission.'})
        except (OSError, ValueError):
            return _failure('TERMS_HISTORY_UNAVAILABLE', 'Owner history is unavailable; never treat missing or corrupt owned history as a new empty decision.')
    assessment = assess_terms(root, catalog_path=args.terms_catalog,
                              catalog_digest=args.terms_catalog_digest)
    wire = assessment.to_dict()
    if any(code.startswith('TERMS_HISTORY_') for code in wire['errors']):
        return _failure('TERMS_DECISION_UNAVAILABLE',
                        'Recover verified owner history before recording another decision.', assessment=assessment)
    matches = [case for case in wire['cases'] if case['case_id'] == args.case_id
               and case['fingerprint'] == args.fingerprint
               and case['evidence_digest'] == args.evidence_digest]
    if len(matches) != 1:
        return _failure('TERMS_DECISION_STALE',
                        'Case identity/evidence changed or is unavailable; inspect a fresh terms report before deciding.',
                        assessment=assessment)
    if any(code in wire['errors'] for code in ('TERMS_CATALOG_INVALID', 'TERMS_CATALOG_STALE',
                                               'TERMS_REPOSITORY_UNAVAILABLE')):
        return _failure('TERMS_DECISION_UNAVAILABLE',
                        'Current trusted terms evidence is unavailable; refresh the review first.', assessment=assessment)
    try:
        event = record_decision(root, case_id=args.case_id, fingerprint=args.fingerprint,
            evidence_digest=args.evidence_digest, choice=args.choice, owner=args.owner,
            rationale=args.reason, supersedes=args.supersedes)
    except (OSError, TermsMemoryError, TypeError):
        return _failure('TERMS_DECISION_UNAVAILABLE',
                        'Decision was not recorded; inspect owner attribution, supersession and external history storage.',
                        assessment=assessment)
    current = assess_terms(root, catalog_path=args.terms_catalog,
                           catalog_digest=args.terms_catalog_digest)
    # Success of the explicit write does not imply permission to proceed.
    return apply_terms_gate(result('terms', complete=True,
        data={'operation': 'decide', 'analysis_performed': False, 'decision_recorded': True,
              'source_analysis_performed': False, 'terms_assessment_performed': True,
              'decision': event, 'next_action': 'Run devsift terms check for the updated complete report.'}),
        current, include_assessment=True)
