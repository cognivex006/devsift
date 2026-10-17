# พัฒนาและดูแล DevSift

เอกสารนี้สำหรับผู้พัฒนา DevSift และ agent ที่แก้ระบบ DevSift เอง
คู่มือใช้ผลิตภัณฑ์อยู่ที่ [เอกสารผู้ใช้](../README.md)

## เริ่มทำงาน

อ่าน [repository instructions](../../AGENTS.md) และ [development setup](../../DEVELOPMENT.md)
ก่อนแก้ source ใช้ [agent scope](AGENT-SCOPE.md) เพื่อแยกงานพัฒนาระบบจากงานใช้ผลิตภัณฑ์
ข้อกำหนด แผนงาน และ ledger อยู่ใน [devsift-specs](https://github.com/orchex006/devsift-specs)
ไม่ติดตั้ง governance ของผู้ดูแลเข้าโปรเจกต์ของผู้ใช้

## โครงสร้างระบบ

- [Scan coordinator](SCAN-CORE.md), [process runner](PROCESS-RUNNER.md), [native protocol](NATIVE-PROTOCOL.md)
- [.NET](DOTNET-ADAPTER.md), [TypeScript](TYPESCRIPT-ADAPTER.md), [Go](GO-ADAPTER.md), [SQL](SQL-ADAPTER.md)
- [Report model](REPORT-MODEL.md), [Markdown report](MARKDOWN-REPORT.md), [source evidence](EVIDENCE.md), [Git provenance](GIT-PROVENANCE.md)
- [Runtime policy model](POLICY.md), [security gates](SECURITY-GATE.md), [threat model](THREAT-MODEL.md)
- [Observability](OBSERVABILITY.md), [change budget](CHANGE-BUDGET.md), [verification evidence](VERIFICATION-EVIDENCE.md)

## ตรวจสอบและส่งมอบ

- [Backend tests](BACKEND-TESTS.md), [frontend tests](FRONTEND-TESTS.md), [SQL tests](SQL-TESTS.md)
- [End-to-end](E2E.md), [observability tests](OBSERVABILITY-TESTS.md), [case prompt evaluation](CASE-PROMPT-EVAL.md)
- [CI workflow](CI-WORKFLOW.md), [packaging](PACKAGING.md), [installer assets](INSTALLER.md)
- [Release readiness](RELEASE-READINESS.md), [release checklist](RELEASE-CHECKLIST.md), [release draft](RELEASE-DRAFT.md)

## การเขียนเอกสาร

คู่มือผู้ใช้สอนติดตั้ง เลือกคำสั่ง และแปลผล เอกสารอ้างอิงอธิบาย flags และ contracts
เอกสารพัฒนาอธิบาย implementation และวิธีทดสอบ ส่วนกติกาการทำงานอยู่ใน `AGENTS.md`
และ repository ข้อกำหนดที่แยกไว้ ใช้ชื่อความสามารถแทนเลข Requirement, task หรือ goal
ในเอกสารผลิตภัณฑ์ และใช้ `devsift` เป็นคำสั่งสาธารณะทุกตัวอย่าง
เมื่อแก้คู่มือใช้งานให้รัน `python tools/sync_skill_docs.py` เพื่ออัปเดตคู่มือที่แนบกับ skill
