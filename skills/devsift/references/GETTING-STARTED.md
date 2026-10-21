# เริ่ม lint โปรเจกต์และเปิดรายงานฉบับเต็ม

ติดตั้งตาม [INSTALL](INSTALL.md) แล้วเปิด terminal/agent ใหม่ให้เห็น `devsift` บน PATH
ใช้จาก Git root ของโปรเจกต์เป้าหมาย ไม่ต้องมี devsift-specs หรือเปิดกฎพัฒนา DevSift

Workflow setup/registry และภาษา `REPORT.md` ต่อไปนี้ใช้ **DevSift 0.1.16 ขึ้นไป**
ตรวจ help ของ CLI หากใช้รุ่นเก่า; 0.1.15 มี session/pages แต่ยังไม่มี setup หรือ `--report-language`

## ตรวจ readiness ครั้งแรก

```text
devsift --help
devsift setup --status
devsift doctor
```

ตัวติดตั้งใหม่เตรียม companion และลงทะเบียน user trust ให้ ถ้ามี manifest เดิมที่ทบทวนแล้ว
ลงทะเบียนครั้งเดียวตาม [Native setup](NATIVE-SETUP.md) ไม่ต้องป้อน native flags ทุกครั้ง
หากไม่มีทั้ง registration และคู่ explicit trust ที่เลือกไว้ ให้แก้ installation/setup
ก่อนเรียกผลว่า native lint ที่ทำงานแล้ว คู่ override ที่เชื่อถือได้ใช้ตรง ๆ ได้โดยไม่ต้องสร้าง registry
Doctor อาจรายงานภาษาที่ไม่ครอบคลุม; ใช้ coverage ของไฟล์ที่ตรวจจริง ไม่อ้างว่าพร้อมทุกภาษา
หาก native helpers ที่ใช้กับโปรเจกต์ READY แล้ว แต่ Doctor overall เป็น 2 เพราะ Python
ไม่รองรับ ให้ตรวจ eligible scope ต่อ ไม่หยุดเสมือนยังไม่มี analyzer หรือแต่ง Python coverage

## ตรวจทั้งโปรเจกต์

```text
devsift scan --all --legacy-mode recommend --summary --report-language th
```

คำขอ “ตรวจโปรเจกต์”, “ตรวจสอบโค้ด” หรือ “review project” ให้ใช้ scope ทั้ง repository
ใช้ `--changed` เฉพาะเมื่อผู้ใช้เลือกงานเปลี่ยนแปลง/staged/working changes อย่างชัดเจน
ภาษาอังกฤษใช้ `--report-language en` การเลือกภาษาไม่เปลี่ยน rule IDs, path, SHA หรือ proof

## เปิดสิ่งที่ใช้ทำงานต่อได้

อ่าน compact JSON แม้ exit 2 แล้วเปิด **ไฟล์ `REPORT.md` จาก `data.report_bundle.report`**
รายงานสำหรับคนอ่านมีทุก case พร้อม evidence, ข้อจำกัด, ผลกระทบทั้งสองทิศทาง,
สถานะข้อเสนอ, verification/rollback และ review/proposal prompts
`data.report_bundle.index` และ `markdown_index` ใช้ตรวจ/เปิดทุก page และ checksum ประกอบ
ไม่ส่งผู้ใช้เพียง folder path หรือ JSON แล้วให้ค้นหารายงานเอง

เมื่อให้ AI ช่วย ขอได้ตรง ๆ:

> ใช้ DevSift ตรวจโปรเจกต์นี้ทั้ง repository ส่งรายงานฉบับเต็มภาษาไทยพร้อมลิงก์ REPORT.md
> บอกจำนวนไฟล์ที่ analyzer ตรวจ, findings, สาเหตุที่ยังไม่ครบ และควรทำอะไรต่อ อย่าแก้ source

AI ต้อง execute คำขอ read-only นี้ใน session ที่รันคำสั่งได้ ไม่หยุดที่แผน Actual host Plan
mode ยังมีผล ไม่มีการอ้างว่าตรวจแล้วเมื่อเพียงอ่านเอกสารหรือเช็ก setup
ดู [Agent integrations](AGENT-INTEGRATIONS.md) สำหรับวิธีโหลด skill/plugin ของแต่ละ host

## อ่านสถานะตามจริง

| ข้อมูล | ความหมาย |
| --- | --- |
| `data.counts.executed` | coverage ที่มีผล analyzer; แยก fresh/reused ด้วย `data.execution` |
| `data.finding_count` | จำนวน cases ทั้งหมด; summary มี `findings: []` โดยตั้งใจ |
| `reports_complete` | มีทุก case/format และผ่าน artifact integrity checks |
| `analysis_complete`, `complete`, errors | การวิเคราะห์/หลักฐานยังขาดส่วนใด |
| exit 0 / 1 / 2 / 3 | complete-clean / enforced / incomplete / argument misuse |

ถ้า executed เป็น 0 ให้บอกว่า analyzer ยังไม่ได้วิเคราะห์ source ไม่ตีความ inventory
หรือ findings ว่างว่า clean ถ้า analysis ไม่ครบให้ระบุ provider/parse/source proof ที่ขาด
และ next action ที่แก้ปัญหานั้น รายงานครบไม่ได้ทำให้ UNKNOWN กลายเป็น verified
การสแกนไม่แก้ source, target dependencies หรือ Git configuration และไม่ดาวน์โหลด tools
ดู [ครบทุก case](COMPLETE-SCANS.md) สำหรับ session/resume และงานขนาดใหญ่

## ตรวจข้อกำหนด dependencies และ SaaS (0.1.17+)

`scan` และ `ci` ตรวจ third-party terms แยกจากคุณภาพ source โดยอัตโนมัติ
หากไม่มีหลักฐาน review สำหรับ component ที่พบ ผลส่วนนี้เป็น incomplete
เริ่มด้วย `devsift terms history` แล้วศึกษา official license/ToU/ToS/AUP และการใช้จริง
จากนั้นใช้ `devsift terms check --summary --report-language th`
หรือส่ง catalog/hash ที่ผู้มีอำนาจตรวจแล้วตาม [คู่มือ](THIRD-PARTY-TERMS.md)
คำสั่งนี้ไม่ต้องใช้ native analyzer และไม่อ้างว่า lint source แล้ว
ข้อขัดแย้งร้ายแรงที่ยืนยันแล้ว Block ต่อแม้ Owner เลือกไม่แก้ไข
คำตัดสินเดิมถูกเก็บถาวรและเรียก reconsider ได้ โดยไม่ลบประวัติ
