# DevSift

DevSift ช่วยตรวจคุณภาพและความปลอดภัยของโค้ดแบบอ่านอย่างเดียว ใช้ได้จาก terminal
และ AI agent ผลระบุหลักฐาน ขอบเขตที่ตรวจได้ และสิ่งที่ยังยืนยันไม่ได้อย่างชัดเจน
รองรับ native analyzers สำหรับ .NET, TypeScript, Go และ SQL เมื่อตั้งค่าเครื่องมือที่เชื่อถือได้

## ติดตั้งและอัปเดต

ต้องมี Python 3.12 ขึ้นไป ตัวติดตั้งจัดการ CLI และ consumer skill สำหรับ
Codex, Claude Code, Gemini CLI, Antigravity และ Cursor ใน user scope

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

Release ปัจจุบันคือ [v0.1.14](https://github.com/orchex006/devsift/releases/tag/v0.1.14)
ดู [วิธีติดตั้งจาก source](docs/INSTALL.md#ติดตั้งจาก-source) หากต้องการ build เอง

เปิด terminal และ agent session ใหม่ จาก Git root ของโปรเจกต์ที่ต้องการตรวจ:

```sh
devsift --help
devsift doctor
devsift scan --changed
```

ตัวติดตั้งใช้ Python environment ส่วนตัวและ launcher ที่แยก import path จากโปรเจกต์เป้าหมาย
Native analyzers เป็น [ขั้นตอนตั้งค่าแยก](docs/NATIVE-SETUP.md); การไม่มี analyzer
หมายถึงตรวจไม่ครบ ไม่ใช่ผล clean

## ใช้ผ่าน AI

หลังติดตั้ง skill ให้เริ่ม chat ใหม่ แล้วขอ เช่น:

> ใช้ DevSift ตรวจการเปลี่ยนแปลงปัจจุบัน เพิ่ม security checks สรุป findings,
> coverage และสิ่งที่ตรวจไม่ครบ โดยยังไม่แก้ไฟล์

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

Scan และ CI ส่ง JSON envelope ซึ่งมี reports ใน `data.reports`; CLI ไม่บันทึกไฟล์ให้อัตโนมัติ
Exit `2` หมายถึงผลไม่ครบหรือยังมี review ค้าง แม้ findings ว่าง
`report --latest` และ storage lookup ของ `explain` ยังไม่พร้อมใช้งาน

Marketplace/repository plugin installation (รวม Copilot): ดู [agent integrations](docs/AGENT-INTEGRATIONS.md) สำหรับคำสั่งและสถานะของแต่ละ host สำหรับรุ่น 0.1.14
