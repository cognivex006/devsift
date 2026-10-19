# คู่มือใช้งาน DevSift

คู่มือนี้เป็น cookbook สำหรับ CLI ที่ติดตั้งแล้ว ใช้ `devsift` จาก Git root ของโปรเจกต์เป้าหมาย
และให้ terminal หรือ agent host มองเห็น launcher บน PATH

การติดตั้ง CLI และ Skill เป็นขั้นตอนแยกกัน ดู [ติดตั้ง](INSTALL.md) หรือ
[เริ่มต้นใช้งาน](GETTING-STARTED.md) ก่อน หากต้องการแก้ปัญหาให้ดู
[การแก้ปัญหา](TROUBLESHOOTING.md)

ทะเบียน analyzer, `setup` และ combined `REPORT.md` ตามภาษาในหน้านี้ใช้ **0.1.16 ขึ้นไป**
ตรวจ installed help เมื่อใช้ CLI เก่า; 0.1.15 ยังไม่มี flags เหล่านี้

## พร้อมแล้ว lint ได้ตรง ๆ

หลัง installation/setup ที่ได้รับอนุญาต รันจาก target Git root:

```text
devsift setup --status
devsift doctor
devsift scan --all --legacy-mode recommend --summary --report-language th
```

Scan/Doctor/CI ใช้ user registration โดยไม่ต้องพิมพ์ native path/digest ซ้ำทุกครั้ง
ถ้ายังไม่มี setup ให้แก้ readiness ตาม [Native setup](NATIVE-SETUP.md) อย่าเรียก inventory
ที่ไม่มี analyzer ว่าการ lint สำเร็จ คำขอตรวจไม่ใช่สิทธิ์ดาวน์โหลด/build tools เงียบ ๆ

## เลือกคำสั่งตามงาน

| งาน | คำสั่ง | ขอบเขตและข้อควรอ่าน |
| --- | --- | --- |
| ตรวจโปรเจกต์ / review project ทั่วไป | `devsift scan --all --legacy-mode recommend --summary --report-language th` | ค่าเริ่มต้นในการตีความคำขอ; ภาษารายงานอังกฤษใช้ en |
| ขอตรวจการแก้ไขปัจจุบันอย่างชัดเจน | `devsift scan --changed --summary --report-language th` | staged, unstaged และ untracked; ไม่ใช้แทน whole-project lint |
| เพิ่มตัวตรวจความปลอดภัยแบบ bounded | เพิ่ม `--security` ให้คำสั่ง scan | ขอบเขต detector มีจำกัด; review ที่จำเป็นยังมีผล |
| ตรวจ change ที่ commit แล้วใน CI | `devsift ci --changed --base TRUSTED_BASE_REF --summary` | ใช้ user registration หรือ explicit trust override; ดู [CI gate](reference/CI-GATE.md) |
| ตรวจการลงทะเบียนครั้งแรก | `devsift setup --status` | readiness metadata; ไม่ใช่ scan |
| ตรวจเครื่องมือที่พร้อมใช้ | `devsift doctor` | เป็น diagnostics ไม่ได้สแกน source และไม่ติดตั้งเครื่องมือ |
| ทบทวน finding รายกรณี | `prompt <CASE-ID> --mode review --scan-input <file>` | ใช้ case ID จริงและ scan envelope ที่บันทึกไว้อย่างชัดเจน |

คำสั่งสแกนไม่ได้พิสูจน์ว่า finding ทุกข้อเกิดจากไฟล์ที่เปลี่ยน การระบุที่มาที่ยังพิสูจน์ไม่ได้
คงเป็น UNKNOWN/incomplete; โหมด recommend ไม่ใช่การอนุมัติแก้ไข legacy แบบกลุ่ม

## สแกนงานที่กำลังเปลี่ยน

```sh
devsift scan --changed --summary --report-language th
devsift scan --changed --summary --report-language th --security
```

`--changed` เลือกไฟล์ staged, unstaged และ untracked ที่ root ของ repository
แล้วอ่าน bytes ปัจจุบันจาก working tree การเลือกไฟล์ไม่ได้ยืนยัน lifecycle ของ finding
เพิ่ม `--security` เพื่อรัน built-in detector แบบ bounded สำหรับ credential และรูปแบบ
logging/TLS ที่รองรับ

## ทบทวน codebase เดิม

```sh
devsift scan --all --legacy-mode recommend --summary --report-language th
devsift scan --all --legacy-mode recommend --summary --report-language th --security
```

โหมดนี้ตรวจทั้ง repository ด้วย analyzer ที่ตั้งค่าไว้ และไม่เปลี่ยน finding เดิมให้เป็น
ข้อผิดพลาดใหม่เพียงเพราะพบในปัจจุบัน Critical security review ยังแยกจาก quality threshold
การไม่มี provider หรือ source proof ทำให้ผลไม่สมบูรณ์ได้ แม้รายการ findings ว่าง

## Native analyzer และขอบเขตที่เชื่อถือได้

Native analyzer ใช้ executable trust ที่ลงทะเบียนโดย installer/setup ครั้งเดียว
หากมี manifest ที่ทบทวนไว้แล้ว ให้ลงทะเบียน absolute path และ digest ที่เชื่อถือได้:

แทน `/absolute/trusted-tools.json` และ `<independently-trusted-sha256>` ด้วย path และ
digest จริงก่อนรัน ตัวอย่างเป็น template บรรทัดเดียว จึงนำไปปรับใช้ได้ทั้ง PowerShell
และ POSIX shell:

```text
devsift setup --native-manifest /absolute/trusted-tools.json --native-manifest-digest TRUSTED_SHA256
```

คำสั่ง scan/doctor/ci ใช้ registry นอก target เป็นค่าเริ่มต้น คู่ explicit flags ยังคงใช้
override trust สำหรับคำสั่งนั้นได้ อย่าใช้ manifest ที่ค้นพบใน target แล้วคำนวณ digest
เพื่ออนุมัติตัวเอง ตัวอย่าง CI หลังลงทะเบียน โดยแทน base ด้วย Git ref ที่เชื่อถือได้:

```text
devsift ci --changed --base TRUSTED_BASE_REF --security --summary --report-language th
```

`ci --base` ใช้ merge-base ถึง HEAD รวมกับการเปลี่ยนแปลงใน working tree ตามขอบเขตที่เลือก
หาก base หายไปหรือกำกวม การตรวจไม่ผ่านเป็น incomplete แทนการตีความว่าไม่มี change
manifest อนุญาตเฉพาะโปรแกรมที่ระบุและ pin ไว้ ไม่อนุญาตให้รันแอปพลิเคชันของเป้าหมาย
ดาวน์โหลด dependency หรือแก้ source การตั้งค่าเครื่องมือแยกจากการสแกน ดู
[native setup](NATIVE-SETUP.md) และ [CI gate](reference/CI-GATE.md)

## อ่านผลและ exit code

workflow ตรวจต่อจนจบตั้งแต่รุ่น 0.1.15 ใช้รายงานหลายส่วนพร้อมดัชนีครบทุก case
ดู [COMPLETE-SCANS](COMPLETE-SCANS.md) สำหรับ session, resume และ native file transport

```text
devsift scan --all --summary --report-language th
```

อ่าน `data.finding_count`, `data.target_count`, `data.counts` และ `data.execution`
จาก summary แล้วเปิด `data.report_bundle.report` ซึ่งชี้ human `REPORT.md` โดยตรง
ใช้ `markdown_index` และ JSON `index` ตรวจทุก page/case และ integrity ประกอบ
summary ไม่ใส่ inventory/findings ยาว ๆ; `findings: []` ในนั้นไม่ได้แปลว่าไม่มี findings
`reports_complete` กับ `analysis_complete` เป็นคนละสถานะ ต้องตรวจทั้งคู่

ผลขนาดเล็กยังมีเอกสาร JSON, Markdown และ SARIF ใน `data.reports` ตาม formats ที่เลือก
ผลขนาดใหญ่ไม่ตัด cases เพื่อบีบลงเอกสารก้อนเดียว ใช้ index ของรายงานทุกส่วนแทน
ทุก page มี `scan.json` สำหรับ case prompts และ SHA-256 สำหรับตรวจความครบถ้วน

ตัวอย่าง PowerShell สำหรับเก็บสถานะและหาตัวรายงาน โดยไม่ dump inventory ทั้งหมด:

```powershell
$result = devsift scan --all --summary --report-language th | ConvertFrom-Json
$scanExitCode = $LASTEXITCODE
$result.data.report_bundle.report
```

CLI ยังคงส่ง JSON envelope สร้าง session/report ของตนเองภายนอก source โดยอัตโนมัติ
หรือใช้ `--report-dir ABSOLUTE_NEW_DIRECTORY` เพื่อเลือกที่เก็บ และ
`--resume ABSOLUTE_EXISTING_SESSION_DIRECTORY` เพื่อทำต่อด้วย options เดิม
ห้ามใช้ `data.reports.markdown` ที่ว่างของผลแบบหลายส่วนไปเขียนทับไฟล์รายงานของผู้ใช้
การบันทึกรายงานครบไม่ได้แปลว่า analysis ผ่านหรือให้สิทธิ์แก้ source

Agent ส่งคำตอบพร้อมลิงก์ไฟล์ `REPORT.md` จริง เริ่มด้วย executed coverage, findings,
incomplete causes และ next action ไม่ส่งแค่ path ของ folder/JSON ถ้า executed เป็น 0
ให้บอกว่า analyzer ยังไม่ได้วิเคราะห์ source ไม่สรุปว่าไม่พบปัญหา แยก fresh/reused targets
และอ่านทุก case page โดยคง UNKNOWN, source unresolved และ proposal ที่ยังไม่มีตามจริง

| Exit code | ความหมาย |
| --- | --- |
| `0` | คำสั่งทำงานครบตามขอบเขตที่รองรับ; ไม่ได้แปลว่า coverage ครบทุกภาษา |
| `1` | วิเคราะห์ครบและพบ violation ที่บังคับใช้ |
| `2` | วิเคราะห์ไม่ครบ, provider ขาด/ล้มเหลว หรือมี review ที่ยังค้าง |
| `3` | คำสั่งหรือ argument ไม่ถูกต้อง |

ผล incomplete มีความสำคัญเหนือ exit แบบ enforced findings ว่างในผลที่ incomplete
ไม่ได้พิสูจน์ว่า clean และ complete scan ก็ครอบคลุมเพียง rules/tools ที่ระบุไว้
หาก complete legacy scan ส่ง security escalation ให้ประมวลผล flag นั้นแยกต่างหาก
แม้ exit code จะเป็น `0`

## ตรวจ policy และ cache แบบอ่านอย่างเดียว

```sh
devsift doctor --policy /absolute/policy.json --cache-path /absolute/cache
```

ต้องเลือก path อย่างชัดเจน Doctor ไม่สร้างหรือ clean cache และไม่สแกน source
ดู [Doctor reference](reference/DOCTOR.md)

## ทบทวน finding รายกรณี

เลือก `scan.json` ของ page ที่มี case นั้นจาก report index (หรือบันทึก scan envelope
ขนาดเล็กจาก stdout ไปนอก source) แล้วเลือก `CASE-ID` ที่มีอยู่จริงในผลลัพธ์:

```sh
devsift prompt CASE-1 --mode review --scan-input /absolute/scan.json
```

คำสั่งนี้ประกอบ prompt จาก source ที่ตรวจยืนยันใหม่ ไม่ได้สแกนซ้ำและไม่ใช่ผล quality pass
การสร้าง prompt สำเร็จหมายถึงสร้าง prompt ได้เท่านั้น

```sh
devsift prompt CASE-1 --mode implement --approved-case CASE-1 --scan-input /absolute/scan.json
```

เพิ่ม `--approval-file /absolute/operator-approval.json` เมื่อต้องตรวจ record ที่ผู้ใช้เลือกไว้
ดูรูปแบบ record ใน [case workflow](reference/CASE-PROMPTS.md) ก่อนสร้างหรือส่งไฟล์

โหมด implement ใช้สร้างข้อเสนอสำหรับทบทวน ไม่ได้แก้ไฟล์ `--approved-case` ที่ตรงกันเพียงอย่างเดียว
ไม่ใช่การอนุมัติ หาก workflow ต้องตรวจ operator record ต้องผูกกับ case, source SHA,
fingerprint, prompt digest, mode และช่วงเวลาที่ใช้ได้ แม้ record ตรงกันก็อนุญาตเพียงการวางแผน
ด้วยคนเมื่อผลกระทบยังไม่ทราบ ไม่มีคำสั่งใดใน workflow นี้นำ patch ไปใช้โดยอัตโนมัติ
ดู [case prompts and approval](reference/CASE-PROMPTS.md)

`report --latest` และการค้นหา storage อัตโนมัติของ `explain` ยังไม่พร้อมใช้งาน
ใช้ report ที่ส่งคืนจากคำสั่งปัจจุบันและระบุ scan input เองตามรูปแบบที่รองรับ

## เริ่มจาก agent chat

ตัวอย่างนี้เป็นข้อความสำหรับ host ที่ติดตั้ง DevSift Skill แล้ว ไม่ใช่คำสั่ง terminal:

> ใช้ DevSift ตรวจโปรเจกต์นี้ทั้ง repository ส่งรายงานฉบับเต็มภาษาไทยพร้อมลิงก์ REPORT.md
> บอก actual analyzer coverage, findings, สาเหตุที่ยังไม่ครบ และ next action โดยยังไม่แก้ source

Skill ช่วย agent ใช้ CLI และอธิบายผลตามข้อจำกัดที่มี แต่ไม่เพิ่มความสามารถของ host
ไม่ติดตั้ง CLI ให้อัตโนมัติ และไม่แปลงคำขอตรวจเป็นสิทธิ์แก้ source

## ข้อจำกัดความพร้อมใช้งาน

`report --latest` และ storage discovery สำหรับ `explain` ยัง pending; อย่าอ้างว่ามีการดึง
ผลเก่าหรืออธิบายตำแหน่งที่ไม่ได้ยืนยัน `prompt` ไม่ใช่ scan pass หรือ patch application
การขาด native analyzer ทำให้ coverage ของภาษานั้นไม่พร้อม ไม่ใช่ผล clean
ดู [สารบัญเอกสาร](README.md) สำหรับ workflow และเอกสารอื่น
