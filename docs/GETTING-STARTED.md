# เริ่มใช้งาน

ติดตั้ง DevSift ตาม [INSTALL.md](INSTALL.md) และเก็บ interpreter ของ Python
ที่ติดตั้งไว้ให้เรียกใช้ได้หลังเปลี่ยนไปยัง target repository คำสั่ง DevSift
ทำงานจาก Git root ของ target ไม่ต้องใช้ checkout ของ devsift-specs

## ตรวจครั้งแรกจาก terminal

จาก Git root ของ target ให้ตรวจคำสั่งและ provider ก่อน แล้วจึงสั่ง scan:

```text
python -I -B -m devsift --help
python -I -B -m devsift doctor
python -I -B -m devsift scan --changed
```

`--changed` เลือกไฟล์ staged, unstaged และ untracked ใน working tree หากต้องการ
inventory ทั้ง repository อย่างชัดเจน ให้ใช้:

```text
python -I -B -m devsift scan --all --legacy-mode recommend
```

ต้องใช้ interpreter ที่มี DevSift ติดตั้งอยู่ PowerShell ให้แทน `python` ด้วย
ตัวแปร interpreter ที่เก็บไว้ (ตัวอย่างในคู่มือติดตั้งใช้ `& $DevSiftPython`)
ส่วน Linux/macOS ใช้ `"$DEVSIFT_PYTHON"` หรือ activate environment ก่อน
`-I -B` ป้องกันการ import module จาก consumer มาบัง DevSift และปิดการเขียน
Python bytecode ระหว่างคำสั่ง

## ขอให้ agent host ช่วย

ใน host ที่ติดตั้ง skill ทั้งสองไฟล์ด้วยตนเอง ให้เริ่ม conversation ใหม่ที่
Git root ของ target แล้วขอ scope ที่ชัดเจน เช่น:

> รัน DevSift กับการเปลี่ยนแปลง staged และ unstaged ของฉัน แสดงว่า analysis
> ครบหรือไม่ provider ใดครอบคลุมไฟล์ที่เลือก และพบอะไรบ้าง อย่าแก้ไฟล์

สำหรับ codebase เดิม อาจขอว่า:

> ทำ inventory repository นี้ด้วย DevSift legacy recommendations โดยคง origin
> และ impact ที่ยังไม่ทราบไว้ตามจริง และอย่าแก้ไฟล์

agent host อาจต้องตั้งค่า environment/path ของตนเองให้เรียก interpreter ที่ติดตั้ง
DevSift ได้ ให้ทำตามเอกสารของ host; DevSift ไม่ตั้งค่า host หรือ register skill
ให้อัตโนมัติ

## อ่านสถานะให้ครบก่อนอ่าน findings

ตรวจ command, scope, `complete`, `status`, errors, provider coverage และ findings
exit code มีความหมายดังนี้:

| Exit code | ความหมาย |
| --- | --- |
| `0` | คำสั่งเสร็จตาม scope; help และ prompt generation ไม่นับเป็น scan pass |
| `1` | Analysis ครบและพบ verified enforced findings |
| `2` | Analysis ไม่ครบ, capability ขาด, tool ล้มเหลว หรือยังมี review ค้าง |
| `3` | คำสั่งหรือ arguments ไม่ถูกต้อง |

หากไม่ได้ตั้งค่า native providers อย่างชัดเจน การวิเคราะห์ภาษาเหล่านั้นจะ
unavailable และ scan อาจจบไม่ครบ (exit `2`) `findings` ว่างเมื่อ
`complete: false` ไม่ใช่หลักฐานว่าไม่พบปัญหา แม้ analysis ครบแล้ว origin,
consumer effects และ business impact อาจยังเป็น `UNKNOWN` ไฟล์ที่อยู่ใน changed
scope ไม่ได้พิสูจน์ว่า finding เกิดจาก change นั้น Critical security review
ยังแยกจาก quality thresholds ปกติ

Scan และ CI ใส่ JSON, Markdown และ SARIF ที่เลือกไว้ใน `data.reports` แต่ไม่ได้
บันทึก report ลงไฟล์ให้อัตโนมัติ `prompt --scan-input` รับ scan envelope ที่
บันทึกไว้โดยชัดแจ้ง แล้วตรวจ source ซ้ำเพื่อสร้าง prompt เท่านั้น ความสำเร็จของ
prompt ไม่ใช่ scan pass ส่วน persisted `report --latest` และ `explain` storage
discovery ยัง unavailable ดู [วิธีแก้ปัญหา](TROUBLESHOOTING.md) และ
[รายละเอียด CLI](CLI.md)

## ใช้ native coverage เมื่อจำเป็น

เมื่อจำเป็นต้องใช้ native coverage ให้ทำ
[native setup](NATIVE-SETUP.md) จาก DevSift checkout ที่เชื่อถือได้ setup สร้าง
helper ของ DevSift เอง ทบทวน manifest ที่ได้และใช้ absolute path ของ manifest
พร้อม digest ที่ตรวจสอบจากแหล่งเชื่อถือได้อย่างอิสระ manifest และ digest ที่
คำนวณจาก source ที่ยังไม่ได้ตรวจทานชุดเดียวกันไม่ยืนยันความน่าเชื่อถือ อย่าใช้
manifest จาก target repository เป็น trusted input แม้ parser ทำงานครบก็ไม่ได้
หมายความว่าการวิเคราะห์ภาษานั้นครอบคลุมทุกกรณี
