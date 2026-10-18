# ตรวจโปรเจกต์จนจบและอ่านรายงานครบทุก case

ความสามารถในหน้านี้อยู่ใน Unreleased หลัง 0.1.14 ขนาดโปรเจกต์ จำนวนไฟล์ และจำนวน
findings ไม่ใช่เหตุให้ตัดรายงานหรือหยุดตรวจที่เพดานรวม ใช้ CLI ที่มี flags เหล่านี้
ตาม `devsift scan --help`; การติดตั้ง 0.1.14 เดิมยังไม่มี workflow นี้

```text
devsift scan --all --legacy-mode recommend --summary
```

เพิ่ม `--native-manifest ABSOLUTE_MANIFEST --native-manifest-digest TRUSTED_SHA256`
เมื่อต้องใช้ native analyzers ที่ตั้งค่าและเชื่อถือแล้ว ดู [native setup](NATIVE-SETUP.md)
ห้ามเลือก manifest จากโปรเจกต์แล้วคำนวณ digest เพื่ออนุมัติให้ตัวเองโดยอัตโนมัติ

CLI ประมวลผลทีละไฟล์ เก็บผลที่ปิดบังข้อมูลแล้วลง session ภายนอก source และสร้างรายงาน
หลายส่วนพร้อมดัชนี ไฟล์ source, Git configuration และ dependency ของโปรเจกต์ไม่ถูกแก้ไข
ไม่ build หรือรันโค้ดของโปรเจกต์ การแบ่งเป็นหลายส่วนไม่ใช่การเลือกแสดงเฉพาะ findings แรก

## อ่านผลให้ครบ

`--summary` คืน JSON ขนาดเล็กแทน inventory ยาว ๆ ให้ตรวจข้อมูลเหล่านี้:

- `data.target_count`, `data.counts`: ขอบเขตและผลต่อไฟล์
- `data.finding_count`: จำนวน findings ทั้งหมด อย่าใช้ `findings: []` ใน summary แทนจำนวนนี้
- `data.execution`: แยกงานใหม่ในรอบนี้ออกจากผลเดิมที่ตรวจซ้ำแล้วใช้ต่อ
- `data.report_bundle.markdown_index`: ดัชนีสำหรับคนอ่าน เชื่อมทุกส่วนของรายงาน
- `data.report_bundle.index`: JSON index ระบุทุกส่วน ทุก case จำนวน bytes และ SHA-256
- `reports_complete`: รายงานทุก case และทุก format ที่เลือกมีครบ และผ่านการตรวจ integrity
- `analysis_complete`, `complete`, `errors`: ผลวิเคราะห์และข้อจำกัดจริง

เปิดทุกส่วนจาก index เพื่ออ่านหรือส่งรายงานฉบับเต็ม ไม่แทนรายงานด้วย top findings หรือ
ตัวอย่างบาง cases แต่ละส่วนมี Markdown, JSON และ SARIF ตาม formats ที่เลือก รวมถึง
`scan.json` ขนาดย่อยสำหรับส่งให้คำสั่ง `prompt --scan-input` ของ case นั้น
หากไม่ใช้ `--summary` CLI จะ stream findings และ targets ครบจาก session ไปยัง stdout
ผลขนาดเล็กยังมี `data.reports` แบบ inline; ผลขนาดใหญ่ใช้ `data.report_bundle` เป็นหลัก

รายงานครบไม่แปลว่าโค้ดผ่าน: parse error, analyzer ที่ขาด, source ที่ยืนยันไม่ได้ และ
UNKNOWN ต้องปรากฏตามจริง งานที่วิเคราะห์ไม่ครบยังออก exit 2 และห้ามประกาศว่า clean
หากรายงานส่วนใดสร้างไม่ได้หรือสูญหาย `reports_complete` ต้องเป็น false ไม่อ้างว่ารายงานครบ

## เก็บ session และทำต่อ

ค่าเริ่มต้นอยู่ใต้ `~/.local/share/devsift/scans/` นอกโปรเจกต์ หรือระบุ directory ใหม่
ด้วย absolute path ซึ่งต้องอยู่นอก source:

```text
devsift scan --all --summary --report-dir ABSOLUTE_NEW_REPORT_DIRECTORY
devsift scan --all --summary --resume ABSOLUTE_EXISTING_SESSION_DIRECTORY
```

ใช้ scope, native manifest/digest, security, base, policy และ formats เดิมเมื่อ resume
ระบบตรวจ root/configuration และเนื้อหา source ใหม่ ไฟล์เดิมที่ตรวจครบและยังตรงกันจึงใช้
ผลต่อได้ ไฟล์ที่เปลี่ยนหรือยังตรวจไม่ครบจะถูกตรวจใหม่ ไฟล์ที่ถูกลบไม่คงอยู่ใน coverage รอบใหม่
ทุกครั้งต้องตรวจ readiness ของ analyzer แม้ source ทุกไฟล์จะอยู่ใน cache แล้ว

หยุดด้วย Ctrl+C ได้ กระบวนการลูกและหน้าจอ progress จะถูกเก็บกวาด ผลที่ commit ลง session
แล้วยังอยู่ พร้อม `SCAN_INTERRUPTED` และ path สำหรับ resume ไม่ overwrite directory ของ
ผู้ใช้หรือเปิด session ที่เป็น symlink/junction ห้ามเปิด writer สองตัวใน session เดียวกัน

## การทำงานนานและไฟล์ขนาดใหญ่

TTY แสดงสองบรรทัดเดิม: จำนวนไฟล์/ผลใหม่/เวลาที่ใช้ และ spinner พร้อม stage หรือไฟล์จริง
stdout ยังเป็น JSON; redirected output ไม่มี ANSI หรือ animation logs
ไม่มีเวลารวมที่ใช้ตัดสินว่าโปรเจกต์ใหญ่เกินไป ใน complete run native file transport
รอจน analyzer จบหรือผู้ใช้ยกเลิก โดยยังตรวจ exit code, protocol, hash pins และ cleanup

helper รุ่นใหม่ส่ง source ผ่าน snapshot ส่วนตัวนอกโปรเจกต์และรับ diagnostics ทีละรายการ
จึงไม่ติดเพดาน JSON inline หรือจำนวน diagnostics เดิม หาก helper เดิมรองรับเฉพาะ inline
ให้ปรับปรุงผ่าน trusted setup ไม่แบ่งโค้ดตามจำนวน bytes แล้วอ้างว่าเทียบเท่า AST ทั้งไฟล์
parser ยังต้องใช้หน่วยความจำสำหรับไฟล์ที่กำลังตรวจ และ parser error หรือ process failure
ต้องเป็นข้อผิดพลาดจริงในรายงาน ไม่ทำให้ findings ของไฟล์อื่นหาย

source excerpt ขนาดใหญ่อาจแสดง `[REDACTED]` ทั้งช่วง เพื่อคงการปิดบังข้อมูลใน full context
พิกัดและ Git SHA ต้องผ่านการยืนยันเช่นเดิม จำนวน cases และตำแหน่งไม่ถูกตัดเพราะขนาด excerpt

CI ใช้ workflow เดียวกัน:

```text
devsift ci --all --base TRUSTED_BASE_REF --summary --native-manifest ABSOLUTE_MANIFEST --native-manifest-digest TRUSTED_SHA256
```

ยังคงกฎ source attribution, legacy recommendations, security review และการอนุมัติแก้ไข
เป็นราย case การสแกนหรือมีรายงานไม่ได้ให้สิทธิ์แก้ source อัตโนมัติ
