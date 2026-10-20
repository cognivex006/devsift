# DevSift

DevSift ช่วยตรวจคุณภาพและความปลอดภัยของโค้ดแบบอ่านอย่างเดียว ใช้ได้จาก terminal
และ AI agent ผลระบุหลักฐาน ขอบเขตที่ตรวจได้ และสิ่งที่ยังยืนยันไม่ได้อย่างชัดเจน
รองรับ native analyzers สำหรับ .NET, TypeScript, Go และ SQL เมื่อตั้งค่าเครื่องมือที่เชื่อถือได้

## ติดตั้งแล้ว lint โปรเจกต์ได้ตรง ๆ

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

Workflow นี้ใช้ DevSift 0.1.16 ขึ้นไป ตรวจ help ของ CLI ที่ติดตั้ง; 0.1.15 ยังต้องตั้ง native
แยกและไม่มี `setup` หรือ `--report-language` อัปเดต installation เดิมก่อนใช้ workflow นี้

## ติดตั้งและอัปเดต

ต้องมี Python 3.12 ขึ้นไป ตัวติดตั้งจัดการ CLI และ consumer skill สำหรับ
Codex, Claude Code, Gemini CLI, Antigravity, Cursor และ Copilot ใน user scope

**Windows PowerShell — ติดตั้ง / อัปเดต:**

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://github.com/cognivex006/devsift/releases/latest/download/install.ps1 | iex"
powershell -ExecutionPolicy Bypass -c "irm https://github.com/cognivex006/devsift/releases/latest/download/update.ps1 | iex"
```

**macOS / Linux — ติดตั้ง / อัปเดต:**

```sh
curl --progress-bar -fL https://github.com/cognivex006/devsift/releases/latest/download/install.sh | sh
curl --progress-bar -fL https://github.com/cognivex006/devsift/releases/latest/download/update.sh | sh
```

Release ปัจจุบันคือ [v0.1.16](https://github.com/cognivex006/devsift/releases/tag/v0.1.16)
ดู [วิธีติดตั้งจาก source](docs/INSTALL.md#ติดตั้งจาก-source) หากต้องการ build เอง

เปิด terminal และ agent session ใหม่ จาก Git root ของโปรเจกต์ที่ต้องการตรวจ:

```sh
devsift --help
devsift setup --status
devsift doctor
devsift scan --all --legacy-mode recommend --summary --report-language th
```

ตัวติดตั้งใช้ Python environment ส่วนตัวและ launcher ที่แยก import path จากโปรเจกต์เป้าหมาย
ตัวติดตั้งปกติเตรียม native analyzers และลงทะเบียนให้โดยอัตโนมัติในขั้น installation
Wheel-only หรือการตั้งค่าเองใช้ [Native setup](docs/NATIVE-SETUP.md) การไม่มี analyzer
หมายถึงตรวจไม่ครบ ไม่ใช่ผล clean; coverage ยังจำกัดตามภาษาและ rules ที่รองรับ

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

Scan และ CI ส่ง JSON envelope พร้อม direct human report และรายงานทุก case แบบหลายส่วน
เก็บ session/resume นอก source ดู [COMPLETE-SCANS](docs/COMPLETE-SCANS.md)
Exit `2` หมายถึงผลไม่ครบหรือยังมี review ค้าง แม้ findings ว่าง
`report --latest` และ storage lookup ของ `explain` ยังไม่พร้อมใช้งาน

Marketplace/repository plugin installation (รวม Copilot): ดู [agent integrations](docs/AGENT-INTEGRATIONS.md) สำหรับคำสั่งและสถานะของแต่ละ host
