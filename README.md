# DevSift

DevSift เป็นเครื่องมือช่วยตรวจโค้ดที่เน้นหลักฐานจาก source ประกอบด้วย:

- **Skill สำหรับ agent** ช่วยเลือกคำสั่ง อ่านผล และอธิบายข้อจำกัดตามขอบเขตของโปรเจกต์
- **Python CLI** สำหรับสแกนแบบอ่านอย่างเดียว สร้างผล JSON/Markdown/SARIF ในหน่วยความจำ และตรวจสถานะเครื่องมือ
- **Native analyzers แบบเลือกใช้** สำหรับ .NET, TypeScript, Go และ SQL เมื่อตั้งค่าเครื่องมือที่เชื่อถือได้อย่างชัดเจน

Python CLI เป็นตัวประสานงานหลัก; การไม่มี native analyzer ไม่ได้แปลว่าภาษานั้นผ่านการตรวจ

## เริ่มจากงานที่ต้องการทำ

| ต้องการ | อ่านต่อ |
| --- | --- |
| ติดตั้งและลองสแกนครั้งแรก | [เริ่มต้นใช้งาน](docs/GETTING-STARTED.md) |
| ติดตั้ง CLI และ Skill ในสภาพแวดล้อมของคุณ | [การติดตั้ง](docs/INSTALL.md) |
| เลือกคำสั่งให้ตรงกับงานและอ่านผลลัพธ์ | [คู่มือคำสั่ง](docs/USAGE.md) |
| แก้ปัญหา Python, Git หรือ native tools | [การแก้ปัญหา](docs/TROUBLESHOOTING.md) |
| ค้นหาเอกสารทั้งหมด | [สารบัญเอกสาร](docs/README.md) |

## เริ่มสแกนจาก terminal

ต้องใช้ Python 3.12 ขึ้นไป และติดตั้ง DevSift ใน Python environment ที่เชื่อถือได้ก่อน
จากนั้นรันจาก Git root ของโปรเจกต์เป้าหมาย:

```sh
python -I -B -m devsift --help
python -I -B -m devsift doctor
python -I -B -m devsift scan --changed
```

`doctor` ตรวจความพร้อมของเครื่องมือ ไม่ได้สแกน source ส่วน `scan --changed`
เลือกไฟล์ที่เปลี่ยนใน working tree เพื่อวิเคราะห์; ผลอาจยังไม่สมบูรณ์หากขาด analyzer
ดูวิธีติดตั้งจาก [คู่มือเริ่มต้น](docs/GETTING-STARTED.md) ก่อนใช้งานจริง

## เริ่มจาก agent chat

ถ้า host ของคุณรองรับการติดตั้ง skill ให้นำเข้า [DevSift Skill](skills/devsift/SKILL.md)
พร้อมไฟล์ [ขอบเขตการใช้งาน](skills/devsift/CONSUMER-SCOPE.md) แล้วสั่ง agent ด้วยภาษาธรรมชาติ
ตัวอย่าง:

> ช่วยตรวจเฉพาะการเปลี่ยนแปลงใน working tree ด้วย DevSift สรุปว่าตรวจอะไรได้ครบ
> มี analyzer ใดขาด และมีประเด็นความปลอดภัยที่ต้องให้คนทบทวนหรือไม่

การติดตั้ง CLI และการนำ Skill เข้า host เป็นคนละขั้นตอน; DevSift ไม่มีตัวติดตั้ง,
ตัวอัปเดต หรือการลงทะเบียน host แบบอัตโนมัติ คู่มือ Skill เป็นแนวทางให้ agent
และไม่เปลี่ยนคำขอให้สแกนเป็นสิทธิ์แก้ source

## เลือกขอบเขต

- **งานที่กำลังแก้:** `scan --changed` อ่านไฟล์ที่ staged, unstaged และ untracked
  โดยใช้ bytes ปัจจุบันใน working tree
- **ตรวจโปรเจกต์เดิม:** `scan --all --legacy-mode recommend` ตรวจ scope ทั้งหมดที่รองรับ
  และแนะนำการทบทวน legacy โดยไม่สั่งแก้เป็นชุด
- **ตรวจ change ที่ commit แล้วใน CI:** ใช้ `ci --base <trusted-base-ref>` พร้อม
  native manifest และ digest ที่เชื่อถือได้; CI ใช้ประวัติ Git เพื่อช่วยจำแนกที่มาของ finding

ไฟล์ที่ถูกแตะไม่ได้แปลว่า finding ทุกข้อเกิดจาก change นั้น และ finding ที่ยังระบุที่มาไม่ได้
คงสถานะ UNKNOWN/incomplete ไว้

## สิ่งที่ควรรู้ก่อนแปลผล

- ผลลัพธ์วิเคราะห์อยู่ใน `data.reports`; CLI ไม่บันทึก report ให้อัตโนมัติ
- exit code `2` หมายถึงวิเคราะห์ไม่ครบหรือยังมี review ที่ค้างอยู่; findings ว่างไม่ใช่หลักฐานว่า clean
- `--security` เพิ่มตัวตรวจแบบ bounded; ประเด็นความปลอดภัยอาจต้องทบทวนแยกจาก quality gate
- native analyzers ต้องระบุ manifest แบบ absolute และ SHA256 ที่ได้จากแหล่งเชื่อถือแยกต่างหาก
- คำสั่ง prompt สร้างข้อความสำหรับทบทวนหรือข้อเสนอเท่านั้น ไม่แก้ไฟล์; prompt สำเร็จไม่ใช่ผลสแกนผ่าน
- `report --latest` และการค้นหา storage ของ `explain` ยังไม่พร้อมใช้งาน
- โปรเจกต์ยังไม่มี public release channel และเจ้าของยังไม่ได้เลือก license

## โฟลเดอร์ไหนใช้ทำอะไร

| ตำแหน่ง | หน้าที่ |
| --- | --- |
| `skills/devsift/` | ไฟล์ Skill สำหรับนำเข้า agent host |
| `devsift/` | Python package ที่รันผ่าน `python -m devsift`; ชื่อซ้ำกับ repo เป็นโครงสร้าง package |
| `native/` | Source ของ analyzers ที่ Python CLI เรียกผ่าน native protocol |
| `docs/` | คู่มือใช้งานและเอกสารเทคนิคของ runtime |
| [devsift-specs](https://github.com/orchex006/devsift-specs) | ข้อกำหนด แผนงาน และ ledger สำหรับผู้ดูแล; ไม่ต้องติดตั้งเพื่อใช้ Skill/CLI |

Source ของผลิตภัณฑ์อยู่ใน repo นี้ ส่วนข้อกำหนดอยู่ใน devsift-specs ตามหน้าที่ข้างต้น

ผู้ดูแลที่ต้องการพัฒนา DevSift เองเริ่มจาก [DEVELOPMENT.md](DEVELOPMENT.md)
ส่วนประวัติข้อกำหนดและการประสานงานอยู่ใน [devsift-specs](https://github.com/orchex006/devsift-specs)
