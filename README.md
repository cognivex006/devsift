# DevSift

DevSift ช่วยตรวจคุณภาพและความปลอดภัยของโค้ดแบบอ่านอย่างเดียว ใช้ได้จาก terminal
และ AI agent ผลระบุหลักฐาน ขอบเขตที่ตรวจได้ และสิ่งที่ยังยืนยันไม่ได้อย่างชัดเจน
รองรับ native analyzers สำหรับ .NET, TypeScript, Go และ SQL เมื่อตั้งค่าเครื่องมือที่เชื่อถือได้

## Workflow ใหม่ใน source (Unreleased)

ตัวติดตั้งใหม่เตรียม analyzer companion ที่ตรวจสอบแล้วและลงทะเบียนใน user scope
ตรวจ readiness ครั้งแรก แล้วสั่ง lint ทั้งโปรเจกต์ได้โดยไม่ต้องส่ง native flags ซ้ำ:

```sh
devsift setup --status
devsift doctor
devsift scan --all --legacy-mode recommend --summary --report-language th
```

เปิดไฟล์ `REPORT.md` จาก `data.report_bundle.report` เพื่ออ่านทุก case และสิ่งที่ต้องทำต่อ
AI ต้องส่งลิงก์ไฟล์นี้พร้อมจำนวนไฟล์ที่ analyzer ตรวจ, findings และสาเหตุที่ผลยังไม่ครบ
การมีเพียง inventory หรือ JSON/folder ไม่ใช่การส่งมอบ lint ที่ใช้งานได้
ใช้ `--changed` เฉพาะเมื่อขอตรวจการเปลี่ยนแปลง ดู [เริ่มตรวจ](docs/GETTING-STARTED.md)

`setup`, registry, analyzer companion และ `--report-language` ใน workflow นี้ยังเป็น
Unreleased; ตรวจ help ของ CLI ที่ติดตั้ง รุ่นที่เผยแพร่ก่อนหน้ายังต้องทำ native setup
แยกและไม่มี flags เหล่านี้ งานนี้ไม่ประกาศ version ใหม่หรือเปลี่ยน public release

## ติดตั้งและอัปเดต

ต้องมี Python 3.12 ขึ้นไป ตัวติดตั้งจัดการ CLI และ consumer skill สำหรับ
Codex, Claude Code, Gemini CLI, Antigravity, Cursor และ Copilot ใน user scope

**Windows PowerShell — ติดตั้ง / อัปเดต:**

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://github.com/orchex006/devsift/releases/latest/download/install.ps1 | iex"
powershell -ExecutionPolicy Bypass -c "irm https://github.com/orchex006/devsift/releases/latest/download/update.ps1 | iex"
```

**macOS / Linux — ติดตั้ง / อัปเดต:**

```sh
curl --progress-bar -fL https://github.com/orchex006/devsift/releases/latest/download/install.sh | sh
curl --progress-bar -fL https://github.com/orchex006/devsift/releases/latest/download/update.sh | sh
```

Release ปัจจุบันคือ [v0.1.15](https://github.com/orchex006/devsift/releases/tag/v0.1.15)
ดู [วิธีติดตั้งจาก source](docs/INSTALL.md#ติดตั้งจาก-source) หากต้องการ build เอง

เปิด terminal และ agent session ใหม่ จาก Git root ของโปรเจกต์ที่ต้องการตรวจ:

```sh
devsift --help
devsift doctor
devsift scan --all --legacy-mode recommend --summary
```

ตัวติดตั้งใช้ Python environment ส่วนตัวและ launcher ที่แยก import path จากโปรเจกต์เป้าหมาย
Native analyzers เป็น [ขั้นตอนตั้งค่าแยก](docs/NATIVE-SETUP.md); การไม่มี analyzer
หมายถึงตรวจไม่ครบ ไม่ใช่ผล clean

## ใช้ผ่าน AI

หลังติดตั้ง skill ให้เริ่ม chat ใหม่ แล้วขอ เช่น:

> ใช้ DevSift ตรวจโปรเจกต์นี้ทั้ง repository ส่งรายงานฉบับเต็มภาษาไทยพร้อมลิงก์
> REPORT.md บอกว่า analyzer ตรวจจริงกี่ไฟล์ พบอะไร ยังตรวจไม่ครบเพราะอะไร
> และควรทำอะไรต่อ โดยยังไม่แก้ source

Skill มีคู่มือการใช้งานแนบไปด้วย ครอบคลุม doctor, scan, CI, reports และ case review/proposal
ดู [การติดตั้ง skill และ plugin](docs/AGENT-INTEGRATIONS.md)

## อ่านต่อ

| ต้องการ | เอกสาร |
| --- | --- |
| เริ่มตรวจครั้งแรก | [เริ่มต้นใช้งาน](docs/GETTING-STARTED.md) |
| ติดตั้ง อัปเดต และจัดการ PATH | [ติดตั้ง](docs/INSTALL.md) |
| เลือกคำสั่งและอ่านผล | [คู่มือใช้งาน](docs/USAGE.md) |
| รูปแบบรายงานฉบับเต็มสำหรับ AI | [Report template](docs/REPORT-TEMPLATE.md) |
| ใช้ skill หรือ plugin กับ AI | [Agent integrations](docs/AGENT-INTEGRATIONS.md) |
| แก้ปัญหา | [Troubleshooting](docs/TROUBLESHOOTING.md) |
| ค้นหาคู่มือและเอกสารอ้างอิง | [เอกสารผู้ใช้](docs/README.md) |
| พัฒนา DevSift / ให้ agent เรียนรู้ระบบ | [เอกสารพัฒนา](docs/development/README.md) |

Scan และ CI ส่ง JSON envelope ตั้งแต่รุ่น 0.1.15 รองรับการตรวจต่อจนจบและ
รายงานทุก case แบบหลายส่วน พร้อม session/resume นอก source ดู [COMPLETE-SCANS](docs/COMPLETE-SCANS.md)
Exit `2` หมายถึงผลไม่ครบหรือยังมี review ค้าง แม้ findings ว่าง
`report --latest` และ storage lookup ของ `explain` ยังไม่พร้อมใช้งาน

Marketplace/repository plugin installation (รวม Copilot): ดู [agent integrations](docs/AGENT-INTEGRATIONS.md) สำหรับคำสั่งและสถานะของแต่ละ host สำหรับรุ่น 0.1.15
