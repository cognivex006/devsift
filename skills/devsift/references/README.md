# เอกสารผู้ใช้ DevSift

เอกสารส่วนนี้สำหรับผู้ใช้ CLI และ AI ที่ใช้ DevSift ตรวจโปรเจกต์ของผู้ใช้
เริ่มจากติดตั้ง → ตรวจ readiness → lint → เปิดรายงานฉบับเต็ม
ทะเบียน analyzer และรายงาน `REPORT.md` ตามภาษาเป็น workflow ใหม่ใน source (Unreleased)
ตรวจ `devsift setup --help` และ `devsift scan --help` ก่อนใช้กับ CLI รุ่นเก่า

| งาน | คู่มือ |
| --- | --- |
| ติดตั้งและอัปเดต CLI / skill | [INSTALL](INSTALL.md) |
| ตรวจโปรเจกต์ครั้งแรกและรับลิงก์รายงาน | [GETTING-STARTED](GETTING-STARTED.md) |
| คำสั่งใช้งานประจำวันและอ่านผล | [USAGE](USAGE.md) |
| ตรวจต่อจนจบและรายงานทุก case | [COMPLETE-SCANS](COMPLETE-SCANS.md) (0.1.15 ขึ้นไป) |
| Codex / Claude / Gemini / Antigravity / Cursor / Copilot | [AGENT-INTEGRATIONS](AGENT-INTEGRATIONS.md) |
| แก้ปัญหาการติดตั้งและผลไม่ครบ | [TROUBLESHOOTING](TROUBLESHOOTING.md) |
| ตรวจ codebase เดิม | [MIGRATION](MIGRATION.md) |
| ตั้งค่า native analyzers | [NATIVE-SETUP](NATIVE-SETUP.md) |
| อ่าน report จากตัวอย่าง | [REPORT-WALKTHROUGH](cases/REPORT-WALKTHROUGH.md) |
| แบบฟอร์มรายงานฉบับเต็มสำหรับผู้ใช้และ AI | [REPORT-TEMPLATE](REPORT-TEMPLATE.md) |
| ดูรูปแบบรายงานเมื่อผลไม่ครบ | [REPORT-EXAMPLE](cases/REPORT-EXAMPLE.md) |

## รายละเอียดอ้างอิง

[CLI](reference/CLI.md), [Doctor](reference/DOCTOR.md), [CI gate](reference/CI-GATE.md),
[security](reference/SECURITY-ANALYSIS.md), [case prompts](reference/CASE-PROMPTS.md),
[project policy configuration](reference/PROJECT-POLICY.md), [baseline](reference/BASELINE.md),
[scan results](reference/SCAN-RESULTS.md), [report context](reference/REPORT-CONTEXT.md),
[report decisions](reference/REPORT-DECISIONS.md) และ [report export](reference/REPORT-EXPORT.md)

## พัฒนา DevSift

ผู้ดูแลและ agent ที่พัฒนา DevSift เริ่มที่ [เอกสารพัฒนา](https://github.com/orchex006/devsift/blob/main/docs/development/README.md)
ซึ่งแยก architecture, test strategy, repository rules และ release engineering
ออกจากคู่มือผู้ใช้ ผู้ใช้ไม่ต้องอ่านเอกสารพัฒนาเพื่อตรวจโปรเจกต์ของตน
