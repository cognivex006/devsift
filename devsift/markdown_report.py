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


_GUIDANCE = {
    'LOG002': ('ตัวตรวจรายงานเส้นทางจัดการ exception ที่อาจกลืนข้อผิดพลาด', 'ตรวจเจตนาของ catch และ caller ก่อนเลือกส่งต่อข้อผิดพลาด คืนผลล้มเหลว หรือบันทึกอย่างเหมาะสม; ต้องคงพฤติกรรมที่ผู้เรียกพึ่งพา'),
    'LOG001': ('ตัวตรวจรายงานคำสั่งพิมพ์ debug ในเส้นทาง runtime', 'ตรวจว่าข้อความจำเป็นใน production หรือไม่ แล้วเลือก logger และระดับ log ที่เหมาะสมโดยไม่บันทึกข้อมูลลับ'),
    'HC001': ('ตัวตรวจรายงาน URL/IP/hostname ที่เขียนเป็นค่าคงที่ในโค้ด runtime', 'ตรวจว่าค่านี้เปลี่ยนตาม environment หรือเป็นค่าคงที่ที่อนุมัติแล้ว; ถ้าต้องเปลี่ยน ให้ใช้ configuration ที่ตรวจสอบค่าและส่งผ่าน dependency ที่เหมาะสม'),
    'HC002': ('ตัวตรวจรายงานค่าที่มีลักษณะ credential/API key/token', 'อย่าคัดลอกค่าลับลงรายงาน; ตรวจผู้ใช้ค่าและประวัติการเปิดเผย หากยืนยันว่าเป็นค่าจริงให้ผู้มีอำนาจดำเนินการเปลี่ยนหรือเพิกถอน แล้วใช้ secret provider'),
    'HC003': ('ตัวตรวจรายงานการแยกพฤติกรรมตาม environment ใน domain logic', 'ตรวจเงื่อนไขและผู้เรียก แล้วพิจารณาย้ายการเลือก environment ไปยัง configuration หรือ composition boundary'),
    'HC004': ('ตัวตรวจรายงานค่าตัวเลขที่อาจเป็น business threshold โดยไม่มีชื่อ', 'ยืนยันความหมายและหน่วยของค่ากับผู้เกี่ยวข้องก่อนตั้งชื่อหรือย้ายเป็น configuration; อย่าเปลี่ยนค่าตัวเลขโดยเดา'),
    'HC005': ('ตัวตรวจรายงาน filesystem path ที่ผูกกับเครื่อง', 'ตรวจว่าเป็น runtime path จริงหรือ fixture แล้วเลือก configuration หรือ path ที่อิง application data directory ตามสัญญาการใช้งาน'),
    'CFG001': ('ตัวตรวจรายงาน configuration ที่อาจขาด validation/schema', 'ตรวจขอบเขตการโหลดค่าและผลเมื่อค่าหายหรือผิดรูปแบบ ก่อนเพิ่ม validation และข้อความล้มเหลวที่ไม่เปิดเผยค่าลับ'),
    'CFG002': ('ตัวตรวจรายงาน configuration key ซ้ำหรือไม่มีผู้ใช้ที่ยืนยันได้', 'ตรวจผู้ใช้ทุกทางและลำดับ override ก่อนรวม ลบ หรือเปลี่ยนชื่อ key'),
    'CFG003': ('ตัวตรวจรายงาน secret ใน configuration หรือ fallback ที่อาจไม่ปลอดภัย', 'ตรวจว่าเป็นข้อมูลจริงหรือ fixture และตรวจแหล่ง secret ที่อนุมัติ; ห้ามแสดงค่าลับหรือเพิ่ม fallback ที่ปกปิดการตั้งค่าผิด'),
    'SEC001': ('ตัวตรวจรายงานข้อมูลลับหรือข้อมูลส่วนบุคคลใน log', 'ตรวจเส้นทางข้อมูลจริงและระบบรับ log; เลือกตัดข้อมูลหรือ masking ตามสัญญา โดยคงหลักฐานที่จำเป็นต่อการวิเคราะห์เหตุขัดข้อง'),
    'SEC002': ('ตัวตรวจรายงานการปิดหรือข้าม TLS certificate validation', 'ตรวจ client และ endpoint จริง แล้วใช้ trust configuration ที่ถูกต้อง; อย่าแก้ด้วยการปิด validation เพิ่ม'),
    'SEC003': ('ตัวตรวจรายงาน dynamic SQL ที่อาจรับข้อมูลที่ยังไม่พิสูจน์ความปลอดภัย', 'แยกข้อมูลกับคำสั่งด้วย parameter ตามชนิดข้อมูล; identifier ต้องผ่าน allowlist/การ quote ที่พิสูจน์ได้ ตรวจ caller และข้อจำกัด engine ก่อนเสนอ patch'),
    'ARC001': ('ตัวตรวจรายงาน import ที่อาจข้ามขอบเขต layer', 'ตรวจสัญญา dependency และผู้ใช้ก่อนย้าย boundary หรือเพิ่ม interface'),
    'ARC002': ('ตัวตรวจรายงาน business logic ที่อาจซ้ำกัน', 'เปรียบเทียบ semantics และผู้ใช้ก่อนรวมโค้ด; ชื่อหรือรูปแบบคล้ายกันไม่พิสูจน์ว่าพฤติกรรมเท่ากัน'),
    'ARC003': ('ตัวตรวจรายงาน dependency ที่ยังไม่มีหลักฐานอนุมัติ', 'ตรวจ owner นโยบายและเหตุผลการใช้งานก่อนเปลี่ยน dependency หรือขออนุมัติ'),
    'API001': ('ตัวตรวจรายงานการเปลี่ยน API/schema ที่อาจกระทบผู้ใช้', 'ตรวจผู้ใช้และสัญญารุ่นเดิมก่อนออกแบบ migration หรือ compatibility; ไม่สมมติว่าผู้ใช้ทั้งหมดอัปเกรดพร้อมกัน'),
    'API002': ('ตัวตรวจรายงานค่า retry/timeout ฝังใน application flow', 'ตรวจ deadline, idempotency และภาระต่อระบบก่อนตั้งชื่อหรือย้าย configuration; ไม่เดาค่า timeout ที่เหมาะสม'),
    'COM001': ('ตัวตรวจรายงานส่วน comment ที่มีลักษณะ executable code', 'ตรวจว่าเป็นตัวอย่างเอกสารหรือโค้ด runtime ที่เลิกใช้ ก่อนลบหรือย้ายไปเอกสารที่เหมาะสม'),
    'COM002': ('ตัวตรวจรายงาน TODO/FIXME/HACK ที่ยังไม่มีหลักฐานติดตาม', 'ตรวจ owner เหตุผลและงานติดตามก่อนกำหนดกำหนดเสร็จหรือลบ marker'),
    'COM003': ('ตัวตรวจรายงาน comment ที่อาจซ้ำกับความหมายของโค้ด', 'ตรวจว่ามีเหตุผลทางธุรกิจหรือข้อควรระวังที่ต้องรักษา แล้วปรับ comment ให้อธิบายเหตุผล'),
    'TST001': ('ตัวตรวจรายงานพฤติกรรมที่เปลี่ยนโดยยังไม่มีหลักฐาน test ที่เหมาะสม', 'ตรวจ trigger, expected behavior และผู้ใช้จริงก่อนเลือก regression test ที่พิสูจน์ผลกระทบ'),
    'TST002': ('ตัวตรวจรายงาน test ที่ถูกข้ามโดยยังไม่มีเหตุผลหรืองานติดตามที่ยืนยันได้', 'ตรวจสาเหตุการ skip, owner และเงื่อนไขเปิดกลับ; อย่าสมมติว่า test ผ่าน'),
}


def rule_guidance(rule_id, language='en'):
    """Catalog-level review directions, never a claim about unproved source."""
    from .registry import RULES
    if language == 'th':
        return _GUIDANCE.get(rule_id, ('ตัวตรวจรายงานกรณีที่ต้องทบทวน', 'ยืนยัน source และผู้ใช้ก่อนเสนอการเปลี่ยนแปลงเฉพาะกรณี'))
    return ('The detector reported: ' + RULES[rule_id].title,
            'Inspect the verified region, rule exceptions and actual callers before proposing one bounded change; tests and effects remain unverified.')


_THAI_HEADINGS = {
    '# DevSift report': '# รายงาน DevSift',
    '## Summary': '## สรุปกรณีที่ตรวจพบ',
    '## Execution errors': '## ข้อผิดพลาดและขอบเขตการตรวจ',
    '### Identity and gate': '### ข้อมูลกรณีและผลต่อ quality gate',
    '### Source evidence': '### หลักฐาน source',
    '### BEFORE': '### BEFORE — โค้ดที่ยืนยันแล้ว',
    '### AFTER (PROPOSAL)': '### AFTER (PROPOSAL) — ข้อเสนอที่ยังไม่อนุมัติ',
    '### Detector explanation': '### เหตุผลที่ตัวตรวจรายงาน',
    '### Alternatives': '### ทางเลือกที่ต้องพิจารณา',
    '### Impact if unchanged': '### ผลกระทบหากยังไม่แก้',
    '### Risk if changed': '### ความเสี่ยงหากปรับแก้',
    '### Affected scope and evidence': '### ขอบเขตที่ได้รับผลและหลักฐาน',
    '### Verification and rollback': '### การตรวจยืนยันและการย้อนกลับ',
    '### Review prompt': '### คำสั่งสำหรับทบทวน',
    '### Implement prompt': '### คำสั่งสำหรับเสนอการแก้เฉพาะกรณี',
    '## Contextual recommendations': '## ข้อเสนอจากบริบทเพิ่มเติม',
    '| Case | Rule | Severity | Lifecycle | Enforcement | Source |': '| กรณี | กฎ | ความรุนแรง | Lifecycle | Enforcement | Source |',
    'No cases supplied. The run status above determines whether analysis completed.': 'ไม่มีกรณีในรายงานนี้ ต้องอ่านสถานะและ coverage ก่อนสรุปว่าการตรวจเสร็จหรือโค้ดผ่าน',
    'SOURCE_UNRESOLVED: no verified BEFORE snippet.': 'SOURCE_UNRESOLVED: ยังไม่มี BEFORE ที่ยืนยันได้ ห้ามเดาพิกัดหรือโค้ด',
    'No verified proposal is available. Inspect source and consumers before proposing a bounded change.': 'ยังไม่มี patch ที่ยืนยันแล้ว ต้องตรวจ source และผู้ใช้ก่อนเสนอการเปลี่ยนแปลงเฉพาะกรณี',
    'No proven source path, region or navigation is available.': 'ยังไม่มี path/พิกัด/link ของ source ที่พิสูจน์ได้',
    'Unknown impact, source or coverage is not evidence of safety. Security-review flags require independent follow-up.': 'UNKNOWN ของผลกระทบ source หรือ coverage ไม่ใช่หลักฐานว่าปลอดภัย ต้องทบทวน security flags แยกต่างหาก',
    'None supplied.': 'ไม่มีข้อมูลที่ให้มา',
    'None supplied by this report model.': 'ไม่มีข้อมูลเพิ่มเติมใน report model นี้',
    'Evidence: none supplied.': 'หลักฐาน: ไม่มีข้อมูลที่ให้มา',
    'Related locations:': 'ตำแหน่งที่เกี่ยวข้อง:',
    'Runtime evidence:': 'หลักฐาน runtime:',
    'Consumers:': 'ผู้ใช้ที่ได้รับผล:',
    'Tests:': 'หลักฐาน test:',
    'No consumer evidence supplied; consumers remain unknown.': 'ยังไม่มีหลักฐานผู้ใช้ที่ได้รับผล จึงคง UNKNOWN',
    'No test evidence supplied.': 'ยังไม่มีหลักฐาน test ห้ามอ้างว่าทดสอบผ่าน',
    'Navigation: unavailable; no trusted repository link supplied.': 'ยังไม่มีลิงก์ repository ที่เชื่อถือได้ ใช้ path และ Git SHA ที่ยืนยันประกอบ',
    'Verified selected/highlighted region, not full file lines. Numbers identify physical LF lines; all displayed content belongs to the highlighted finding region.': 'BEFORE แสดงเฉพาะช่วงที่ตรวจยืนยัน เลขบรรทัดอิง LF จริง ไม่อ้างว่าเป็นเนื้อหาเต็มทุกบรรทัดของไฟล์',
    'The entire selected region is redacted; no per-line content is inferred.': 'ปิดบังช่วงที่เลือกทั้งช่วง ไม่เดาเนื้อหาของแต่ละบรรทัด',
    'Verified zero-width region; no source characters are selected.': 'ยืนยันพิกัดแบบ zero-width จึงไม่มีตัวอักษร source ที่เลือก',
    'Unverified proposal; not an asserted correct or applied patch.': 'ข้อเสนอยังไม่ผ่านการยืนยัน ไม่อ้างว่า patch ถูกต้องหรือถูกนำไปใช้แล้ว',

}


_THAI_MODEL_PROSE = {
    'The configured detector reported this rule at the supplied region; inspect its documented limits.': 'ตัวตรวจที่ตั้งค่ารายงานกฎนี้ในพิกัดที่ให้มา ต้องตรวจข้อจำกัดและเงื่อนไขของตัวตรวจประกอบ',
    'Unknown until the exact detector context and counterexamples are checked.': 'UNKNOWN จนกว่าจะตรวจบริบทจริงและกรณียกเว้นที่ทำให้ข้อสรุปของตัวตรวจใช้ไม่ได้',
    'Leave behavior unchanged while collecting evidence.': 'คงพฤติกรรมเดิมระหว่างเก็บหลักฐาน',
    'Propose one bounded change after review.': 'เสนอการเปลี่ยนแปลงเฉพาะกรณีหลังทบทวน',
    'Production frequency, exploitability and consumers are unmeasured.': 'ยังไม่มีหลักฐานความถี่ที่เกิดจริง ช่องทางนำไปใช้โจมตี หรือผู้ใช้ที่ได้รับผล จึงคง UNKNOWN',
    'Functional, contract, logging, security, performance and deployment effects are unverified.': 'ยังไม่ยืนยันผลต่อพฤติกรรม สัญญา log ความปลอดภัย ประสิทธิภาพ หรือ deployment จึงคง UNKNOWN',
    'Inspect the immutable source and actual consumers; select relevant regression checks before editing.': 'ตรวจ source ที่ผูกกับ Git SHA และผู้ใช้จริง แล้วเลือก regression checks ที่เกี่ยวข้องก่อนแก้',
    'No source change has been applied. Define a scoped rollback before implementation.': 'ยังไม่มีการแก้ source ต้องกำหนดวิธีย้อนกลับเฉพาะส่วนก่อนลงมือแก้',
    'pending source and consumer inspection': 'รอตรวจ source และผู้ใช้จริง',
}


def _thai_label(value):
    if value in _THAI_HEADINGS:
        return _THAI_HEADINGS[value]
    for prefix, translated in (
            ('## Case ', '## กรณี '), ('Report schema: ', 'Schema รายงาน: '),
            ('Status: ', 'สถานะ: '), ('Source status: ', 'สถานะ source: '),
            ('Repository: ', 'Repository: '), ('Immutable SHA: ', 'Git SHA ที่ยืนยัน: '),
            ('Path: ', 'ไฟล์: '), ('Region: ', 'พิกัด: '), ('Symbol: ', 'Symbol: '),
            ('Reason: ', 'เหตุผล: '), ('Lookup plan: ', 'แนวทางค้นหาหลักฐาน: '),
            ('Security escalation: ', 'ต้องทบทวน security: '),
            ('Approval: ', 'สถานะอนุมัติ: '), ('Confidence: ', 'ความมั่นใจ: '),
            ('Proposal confidence: ', 'ความมั่นใจของข้อเสนอ: '), ('Rollback: ', 'การย้อนกลับ: '),
            ('Level: ', 'ระดับ: '), ('Scope: ', 'ขอบเขต: '), ('Why detector fired: ', 'เหตุที่ตัวตรวจรายงาน: '),
            ('Invalidating exception: ', 'กรณียกเว้นที่ต้องตรวจ: ')):
        if value.startswith(prefix):
            return translated + value[len(prefix):]
    return value


def _render_terms_wire(wire, *, language='en'):
    """Internal display of engine-redacted terms from a sealed report."""
    _require(language in ('en', 'th'))
    parts = []
    def add(value=''):
        parts.append(value + '\n')
    def label(en, th):
        return th if language == 'th' else en
    def block(value):
        add(_code(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)))
    add('## ' + label('Third-party terms governance', 'การกำกับดูแลข้อกำหนดของบุคคลที่สาม'))
    add()
    add(label('Scope: bounded offline terms review; source analysis coverage is separate.',
              'ขอบเขต: ทบทวนข้อกำหนดจากหลักฐานภายในแบบจำกัด แยกจากการวิเคราะห์ source'))
    add('Status: ' + _text(wire['status']) + '; complete: ' + str(wire['complete']).lower()
        + '; enforced: ' + str(wire['enforced_count']) + '; decision required: '
        + str(wire['decision_required']).lower())
    add(label('A remembered decline never clears a serious block. Unknown evidence is not permission.',
              'การปฏิเสธแก้ไขที่บันทึกไว้ไม่ปลด block ร้ายแรง หลักฐานที่ยังไม่ทราบไม่ใช่การอนุญาต'))
    add(label('### Review binding and coverage', '### หลักฐานผูกมัดและความครอบคลุม'))
    block({key: wire[key] for key in ('schema_version', 'policy_version', 'repository_id',
           'input_digest', 'history_revision', 'scope', 'errors', 'limitations')})
    add(label('### Component inventory', '### รายการส่วนประกอบ'))
    block(wire['inventory'])
    for case in wire['cases']:
        add('### ' + label('Terms case ', 'กรณีข้อกำหนด ') + _text(case['case_id']))
        add()
        # Every available field, including compact decisions under output limits,
        # remains safely fenced data rather than document instructions.
        block(case)
        add(label('#### Why and proposed action', '#### เหตุผลและแนวทางเสนอ'))
        add(_text(case['rationale']))
        add(_text(case['recommendation']))
        add(label('#### Impact if unchanged', '#### ผลกระทบหากไม่แก้ไข'))
        add(label('Continuing the evidenced use retains the reported conflict or review gap. '
                  'Business frequency, contractual consequences and affected consumers remain unmeasured.',
                  'การใช้ตามหลักฐานต่อไปยังคงข้อขัดแย้งหรือช่องว่างการทบทวน '
                  'ความถี่ ผลกระทบตามสัญญา และผู้ใช้ที่ได้รับผลยังไม่ได้ตรวจวัด'))
        add(label('#### Risk if changed', '#### ความเสี่ยงหากแก้ไข'))
        add(label('Replacement or removal may affect behavior, availability, contracts and deployment. '
                  'Inspect actual consumers before selecting a bounded change.',
                  'การเปลี่ยนหรือถอดออกอาจกระทบพฤติกรรม ความพร้อมใช้ สัญญา และ deployment '
                  'ตรวจผู้ใช้จริงก่อนเลือกการแก้ไขที่มีขอบเขต'))
        add(label('#### Verification and rollback', '#### การตรวจยืนยันและย้อนกลับ'))
        add(label('Recheck current official applicability, pinned clause/usage bytes, dependency version, '
                  'freshness and owner history; verify the proposed compliant behavior with relevant tests. '
                  'Refresh the assessment after authorized repairs. Define rollback before editing; no change has been applied.',
                  'ตรวจข้อกำหนดทางการ hash ของข้อกำหนดและการใช้ รุ่น dependency ความสดใหม่ และประวัติ Owner '
                  'ทดสอบพฤติกรรมที่เสนอและประเมินใหม่หลังแก้ไขที่ได้รับอนุญาต '
                  'กำหนดวิธีย้อนกลับก่อนแก้ไข รายงานนี้ยังไม่ได้เปลี่ยน source'))
        add(label('#### Review and implementation guidance', '#### แนวทางทบทวนและดำเนินการ'))
        block({key: case[key] for key in ('case_id', 'fingerprint', 'evidence_digest', 'decision_required')})
        add(label('Review read-only first. For a new serious conflict obtain an explicit owner '
                  'remediate/decline answer bound to the fingerprint and evidence digest. Reuse a matching '
                  'fresh decision without prompting again. A proposal, remembered decision or resolved label '
                  'does not authorize edits or prove remediation; no automatic fix or code patch is supplied.',
                  'ทบทวนแบบอ่านอย่างเดียวก่อน ข้อขัดแย้งร้ายแรงใหม่ต้องได้คำตอบ Owner ว่าจะแก้ไขหรือปฏิเสธ '
                  'โดยผูกกับ fingerprint และ evidence digest ใช้คำตัดสินเดิมที่ตรงหลักฐานโดยไม่ถามซ้ำ '
                  'ข้อเสนอ คำตัดสิน หรือ resolved ไม่ใช่สิทธิ์แก้ source หรือหลักฐานว่าแก้สำเร็จ ไม่มี patch อัตโนมัติ'))
    rendered = ''.join(parts)
    _require(len(rendered.encode('utf-8')) <= MAX_OUTPUT_BYTES)
    return rendered


def render_terms_markdown(assessment, *, language='en'):
    """Render every available terms field without I/O or imported authority."""
    from .terms import TermsAssessment
    try:
        _require(type(assessment) is TermsAssessment)
        return _render_terms_wire(assessment.to_dict(), language=language)
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, OverflowError, RecursionError):
        raise MarkdownError('Invalid, unsupported or excessive Markdown report') from None


def render_markdown(report: Report, *, language='en') -> str:
    """Render every field/case; never truncate, re-mask, execute or discover URLs."""
    _require(type(report) is Report and language in ('en', 'th'))
    try:
        wire = report.to_dict()
        _require(wire['contextual_recommendations'] == [])  # T041 integration is separate.
        chunks, size = [], 0

        def text(value):
            return _text(_THAI_MODEL_PROSE.get(value, value) if language == 'th' else value)

        def add(value=''):
            nonlocal size
            if language == 'th':
                value = _thai_label(value)
            size += len(value.encode('utf-8')) + 1
            _require(size <= MAX_OUTPUT_BYTES)
            chunks.append(value + '\n')

        def bullets(values, empty='None supplied.'):
            if not values:
                add(empty)
            for value in values:
                if type(value) is str:
                    add('- ' + text(value))
                else:
                    add(_code(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)))

        def evidence(values):
            if not values:
                add('Evidence: none supplied.')
            else:
                add(_code(json.dumps(values, ensure_ascii=False, sort_keys=True, indent=2)))

        add('# DevSift report')
        if 'terms_compliance' not in wire:
            add('Scope: source analysis only; this page does not assess third-party terms.')
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
                add(f'| [{text(case["case_id"])}](#case-{ordinal:04}) | {case["rule_id"]} | {case["severity"]} | {case["lifecycle_class"]} | {case["enforcement"]} | {case["source"]["status"]} |')
        add()
        add('## Execution errors')
        add()
        if not wire['errors']:
            add('None supplied.')
        for error in wire['errors']:
            add('- ' + text(error['code']) + ': ' + text(error['message']))
        add()
        for ordinal, stored in enumerate(report.cases, 1):
            case = report.find_case(stored.case_id).to_dict()
            anchor = f'case-{ordinal:04}'
            add(f'<a id="{anchor}"></a>')
            add(f'## Case {text(case["case_id"])}: {text(case["title"])}')
            add()
            add(f'[Review prompt](#{anchor}-review) · [Implement prompt](#{anchor}-implement)')
            add()
            if language == 'th':
                explanation, action = rule_guidance(case['rule_id'], language)
                add(text(explanation))
                add('แนวทางตรวจแก้: ' + text(action))
                add('นี่เป็นแนวทางทบทวน ไม่ใช่ patch ที่ตรวจยืนยันแล้วหรือสิทธิ์ให้แก้ source อัตโนมัติ')
                add()
            add('### Identity and gate')
            add()
            add(f'Rule: {case["rule_id"]}; severity: {case["severity"]}; lifecycle: {case["lifecycle_class"]}; enforcement: {case["enforcement"]}.')
            add(f'Confidence: {case["confidence"]}')
            add(f'Security escalation: {str(case["security_escalation"]).lower()}')
            add(f'Approval: {case["approval_status"]}; automatic fix: {str(case["automatic_fix"]).lower()}')
            add('Fingerprint: ' + (text(case['fingerprint']) if case['fingerprint'] else 'unavailable'))
            add()
            add('### Source evidence')
            add()
            source = case['source']
            add('Source status: ' + source['status'])
            location = source['location']
            if source['status'] == 'VERIFIED':
                region = location['region']
                add('Repository: ' + text(location['repository']))
                add('Immutable SHA: ' + text(location['source_sha']))
                add('Path: ' + text(location['path']))
                add(f'Region: {region["start_line"]}:{region["start_column"]}–{region["end_line"]}:{region["end_column"]} (one-based code points; end exclusive).')
                add('Symbol: ' + (text(location['symbol']) if location['symbol'] else 'unknown (not proven).'))
                if case['navigation'] is not None:
                    # The sealed model supplies this source-proven, encoded URL.
                    add('[Immutable source](' + case['navigation'] + ')')
                else:
                    add('Navigation: unavailable; no trusted repository link supplied.')
            else:
                add('Reason: ' + text(source['reason']))
                add('Lookup plan: ' + text(source['lookup_plan']))
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
            add('Status: ' + text(proposal['status']))
            add('Proposal confidence: ' + proposal['confidence'])
            if proposal['code'] is None:
                add('No verified proposal is available. Inspect source and consumers before proposing a bounded change.')
            else:
                add('Unverified proposal; not an asserted correct or applied patch.')
                add(_code(proposal['code']))
            add()
            add('### Detector explanation')
            add()
            add(text(case['human_explanation']))
            add('Why detector fired: ' + text(case['why_detector_fired']))
            add('Invalidating exception: ' + text(case['invalidating_exception']))
            add()
            add('### Alternatives')
            add()
            bullets(case['alternatives'])
            for title, key in (('Impact if unchanged', 'impact_if_unchanged'), ('Risk if changed', 'risk_if_changed')):
                add()
                add('### ' + title)
                add()
                add('Level: ' + case[key]['level'])
                add('Reason: ' + text(case[key]['reason']))
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
            add('Rollback: ' + text(case['rollback']))
            add()
            for title, key, suffix in (('Review prompt', 'review_prompt', 'review'),
                                        ('Implement prompt', 'implement_prompt', 'implement')):
                add(f'<a id="{anchor}-{suffix}"></a>')
                add('### ' + title)
                add()
                add(_code(case[key]))
        if 'terms_compliance' in wire:
            add(_render_terms_wire(wire['terms_compliance'], language=language))
        add('## Contextual recommendations')
        add()
        add('None supplied by this report model.')
        return ''.join(chunks)
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        raise MarkdownError('Invalid, unsupported or excessive Markdown report') from None
