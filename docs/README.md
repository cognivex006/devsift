# เอกสาร DevSift

DevSift อ่าน source ใน repository แล้วรายงานหลักฐานให้คนตรวจทาน หากเพิ่งเริ่มใช้
ให้อ่านตามลำดับนี้:

1. [ติดตั้ง](INSTALL.md) CLI ใน Python environment ที่เชื่อถือได้ และถ้า agent host
   รองรับ skill ให้ติดตั้งไฟล์ skill ทั้งสองไฟล์ตามตำแหน่งที่ host ระบุ
2. [เริ่มใช้งาน](GETTING-STARTED.md) ด้วยคำสั่ง terminal หรือคำขอใน agent chat
3. เปิด [วิธีแก้ปัญหา](TROUBLESHOOTING.md) เมื่อ provider ใช้ไม่ได้ ผลไม่ครบ
   หรือไม่แน่ใจว่าผลหมายถึงอะไร

## คู่มือผู้ใช้

- [ติดตั้ง](INSTALL.md): checkout ที่เชื่อถือได้, Python virtual environment,
  ติดตั้ง skill ด้วยตนเอง และ native helper ที่เป็นทางเลือก
- [เริ่มใช้งาน](GETTING-STARTED.md): ตรวจครั้งแรก เลือก scope และอ่านผล
- [คู่มือคำสั่ง](USAGE.md): command cookbook และคำแนะนำการใช้งานเพิ่มเติม
- [วิธีแก้ปัญหา](TROUBLESHOOTING.md): อาการจาก setup และผลวิเคราะห์ที่พบบ่อย
- [นำไปใช้กับ codebase เดิม](MIGRATION.md): ค่อย ๆ ตรวจ legacy findings
- [ตัวอย่าง report](cases/REPORT-WALKTHROUGH.md): source proof, redaction และ
  กรณีที่ยังยืนยันไม่ได้ ผ่านตัวอย่างชั่วคราว

## คำสั่งและความสามารถ

- [คำสั่ง CLI, JSON envelope และ exit code](CLI.md)
- [Doctor diagnostics](DOCTOR.md)
- [ตั้งค่า native tools และ explicit trust](NATIVE-SETUP.md)
- [CI gate](CI-GATE.md)
- [ขอบเขต security analysis](SECURITY-ANALYSIS.md)
- [case prompts และ approval](CASE-PROMPTS.md)
- [report context](REPORT-CONTEXT.md)

## เอกสารสำหรับผู้ดูแล

[Development](../DEVELOPMENT.md), [packaging](PACKAGING.md) และเอกสารเทคนิคอื่น ๆ
อธิบายการพัฒนาและดูแล DevSift แผนงานและ execution ledger กลางอยู่ใน
[devsift-specs](https://github.com/orchex006/devsift-specs); ผู้ใช้ไม่ต้อง checkout
repository นั้น ใช้ ledger หรือเตรียม maintainer tooling เพื่อใช้ DevSift

เวอร์ชันใน package ตอนนี้คือ `0.0.0.dev0` ซึ่งเป็น placeholder สำหรับการพัฒนา
ไม่ได้หมายความว่ามี release หรือมีการเลือก license ของโครงการแล้ว
