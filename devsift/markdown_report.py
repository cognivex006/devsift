"""Standalone Markdown from accepted sealed reports; no I/O or executable actions."""
import html
import json
import re
import unicodedata

from .report_model import Report

MAX_OUTPUT_BYTES = 16_000_000


class MarkdownError(ValueError):
    """Safe renderer failure that never includes source or report values."""


def _require(condition):
    if not condition:
        raise MarkdownError('Invalid, unsupported or excessive Markdown report') from None


def _controls(value, *, code=False):
    _require(type(value) is str)
    result = []
    for index, character in enumerate(value):
        allowed = code and (character in '\n\t' or
                            (character == '\r' and index + 1 < len(value) and value[index + 1] == '\n'))
        if not allowed and (unicodedata.category(character) in {'Cc', 'Cf', 'Cs'} or character in '\u2028\u2029'):
            result.append(f'\\u{ord(character):04x}')
        else:
            result.append(character)
    return ''.join(result)


def _text(value):
    # Escape Markdown before adding HTML entities, so entity '#' characters are
    # not subsequently interpreted as user Markdown punctuation.
    escaped = re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', _controls(value))
    return html.escape(escaped, quote=True).replace(':', '&#58;').replace('/', '&#47;').replace('@', '&#64;')


def _code(value):
    safe = _controls(value, code=True)
    _require(len(safe.encode('utf-8')) <= MAX_OUTPUT_BYTES)
    longest = max((len(match.group()) for match in re.finditer(r'`+', safe)), default=0)
    fence = '`' * max(3, longest + 1)
    return fence + 'text\n' + safe + ('' if safe.endswith('\n') else '\n') + fence + '\n'


def _numbered(before, region):
    if before == '':
        return ''
    if before == '[REDACTED]':
        start, end = region['start_line'], region['end_line']
        if end > start and region['end_column'] == 1:
            end -= 1
        label = str(start) if start == end else f'{start}-{end}'
        return f'{label} | [REDACTED]'
    lines = before.split('\n')
    trailing_newline = before.endswith('\n')
    if trailing_newline:
        lines.pop()
    numbered, size = [], 0
    for offset, line in enumerate(lines):
        entry = f'{region["start_line"] + offset} | {line}'
        size += len(entry.encode('utf-8')) + 1
        _require(size <= MAX_OUTPUT_BYTES)
        numbered.append(entry)
    return '\n'.join(numbered) + ('\n' if trailing_newline else '')


def render_markdown(report: Report) -> str:
    """Render every field/case; never truncate, re-mask, execute or discover URLs."""
    _require(type(report) is Report)
    try:
        wire = report.to_dict()
        _require(wire['contextual_recommendations'] == [])  # T041 integration is separate.
        chunks, size = [], 0

        def add(value=''):
            nonlocal size
            size += len(value.encode('utf-8')) + 1
            _require(size <= MAX_OUTPUT_BYTES)
            chunks.append(value + '\n')

        def bullets(values, empty='None supplied.'):
            if not values:
                add(empty)
            for value in values:
                if type(value) is str:
                    add('- ' + _text(value))
                else:
                    add(_code(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)))

        def evidence(values):
            if not values:
                add('Evidence: none supplied.')
            else:
                add(_code(json.dumps(values, ensure_ascii=False, sort_keys=True, indent=2)))

        add('# DevSift report')
        add()
        add(f'Report schema: {wire["schema_version"]}; tool: {wire["tool"]}.')
        add(f'Status: {wire["status"]}; complete: {str(wire["complete"]).lower()}; exit code: {wire["exit_code"]}; enforced violations: {wire["enforced_count"]}.')
        add('Unknown impact, source or coverage is not evidence of safety. Security-review flags require independent follow-up.')
        add()
        add('## Summary')
        add()
        if not report.cases:
            add('No cases supplied. The run status above determines whether analysis completed.')
        else:
            add('| Case | Rule | Severity | Lifecycle | Enforcement | Source |')
            add('| --- | --- | --- | --- | --- | --- |')
            for ordinal, stored in enumerate(report.cases, 1):
                case = report.find_case(stored.case_id).to_dict()
                add(f'| [{_text(case["case_id"])}](#case-{ordinal:04}) | {case["rule_id"]} | {case["severity"]} | {case["lifecycle_class"]} | {case["enforcement"]} | {case["source"]["status"]} |')
        add()
        add('## Execution errors')
        add()
        if not wire['errors']:
            add('None supplied.')
        for error in wire['errors']:
            add('- ' + _text(error['code']) + ': ' + _text(error['message']))
        add()
        for ordinal, stored in enumerate(report.cases, 1):
            case = report.find_case(stored.case_id).to_dict()
            anchor = f'case-{ordinal:04}'
            add(f'<a id="{anchor}"></a>')
            add(f'## Case {_text(case["case_id"])}: {_text(case["title"])}')
            add()
            add(f'[Review prompt](#{anchor}-review) · [Implement prompt](#{anchor}-implement)')
            add()
            add('### Identity and gate')
            add()
            add(f'Rule: {case["rule_id"]}; severity: {case["severity"]}; lifecycle: {case["lifecycle_class"]}; enforcement: {case["enforcement"]}.')
            add(f'Confidence: {case["confidence"]}')
            add(f'Security escalation: {str(case["security_escalation"]).lower()}')
            add(f'Approval: {case["approval_status"]}; automatic fix: {str(case["automatic_fix"]).lower()}')
            add('Fingerprint: ' + (_text(case['fingerprint']) if case['fingerprint'] else 'unavailable'))
            add()
            add('### Source evidence')
            add()
            source = case['source']
            add('Source status: ' + source['status'])
            location = source['location']
            if source['status'] == 'VERIFIED':
                region = location['region']
                add('Repository: ' + _text(location['repository']))
                add('Immutable SHA: ' + _text(location['source_sha']))
                add('Path: ' + _text(location['path']))
                add(f'Region: {region["start_line"]}:{region["start_column"]}–{region["end_line"]}:{region["end_column"]} (one-based code points; end exclusive).')
                add('Symbol: ' + (_text(location['symbol']) if location['symbol'] else 'unknown (not proven).'))
                if case['navigation'] is not None:
                    # The sealed model supplies this source-proven, encoded URL.
                    add('[Immutable source](' + case['navigation'] + ')')
                else:
                    add('Navigation: unavailable; no trusted repository link supplied.')
            else:
                add('Reason: ' + _text(source['reason']))
                add('Lookup plan: ' + _text(source['lookup_plan']))
                add('No proven source path, region or navigation is available.')
            add('Related locations:')
            evidence(case['related_locations'])
            add('Runtime evidence:')
            evidence(case['runtime_evidence'])
            add()
            add('### BEFORE')
            add()
            if source['status'] == 'VERIFIED':
                add('Verified selected/highlighted region, not full file lines. Numbers identify physical LF lines; all displayed content belongs to the highlighted finding region.')
                if source['before'] == '[REDACTED]':
                    add('The entire selected region is redacted; no per-line content is inferred.')
                elif source['before'] == '':
                    add('Verified zero-width region; no source characters are selected.')
                add(_code(_numbered(source['before'], location['region'])))
            else:
                add('SOURCE_UNRESOLVED: no verified BEFORE snippet.')
            add('### AFTER (PROPOSAL)')
            add()
            proposal = case['after_proposal']
            add('Status: ' + _text(proposal['status']))
            add('Proposal confidence: ' + proposal['confidence'])
            if proposal['code'] is None:
                add('No verified proposal is available. Inspect source and consumers before proposing a bounded change.')
            else:
                add('Unverified proposal; not an asserted correct or applied patch.')
                add(_code(proposal['code']))
            add()
            add('### Detector explanation')
            add()
            add(_text(case['human_explanation']))
            add('Why detector fired: ' + _text(case['why_detector_fired']))
            add('Invalidating exception: ' + _text(case['invalidating_exception']))
            add()
            add('### Alternatives')
            add()
            bullets(case['alternatives'])
            for title, key in (('Impact if unchanged', 'impact_if_unchanged'), ('Risk if changed', 'risk_if_changed')):
                add()
                add('### ' + title)
                add()
                add('Level: ' + case[key]['level'])
                add('Reason: ' + _text(case[key]['reason']))
                evidence(case[key]['evidence'])
            add()
            add('### Affected scope and evidence')
            add()
            add('Scope: ' + case['affected_scope']['status'])
            add('Consumers:')
            bullets(case['affected_scope']['consumers'], 'No consumer evidence supplied; consumers remain unknown.')
            add('Tests:')
            bullets(case['affected_scope']['test_evidence'], 'No test evidence supplied.')
            add()
            add('### Verification and rollback')
            add()
            bullets(case['verification'])
            add('Rollback: ' + _text(case['rollback']))
            add()
            for title, key, suffix in (('Review prompt', 'review_prompt', 'review'),
                                        ('Implement prompt', 'implement_prompt', 'implement')):
                add(f'<a id="{anchor}-{suffix}"></a>')
                add('### ' + title)
                add()
                add(_code(case[key]))
        add('## Contextual recommendations')
        add()
        add('None supplied by this report model.')
        return ''.join(chunks)
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        raise MarkdownError('Invalid, unsupported or excessive Markdown report') from None
