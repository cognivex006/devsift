# คู่มือใช้งาน DevSift

คู่มือนี้เป็น cookbook สำหรับคำสั่งที่ติดตั้งแล้ว ต้องใช้ Python 3.12 ขึ้นไป
และรันจาก Git root ของโปรเจกต์เป้าหมายด้วย Python environment ที่ติดตั้ง DevSift
ตัวอย่างใช้ `python -I -B -m devsift` เพื่อไม่ให้ไฟล์ในโปรเจกต์บังโมดูลที่ติดตั้ง
และป้องกันการเขียน bytecode

การติดตั้ง CLI และ Skill เป็นขั้นตอนแยกกัน ดู [ติดตั้ง](INSTALL.md) หรือ
[เริ่มต้นใช้งาน](GETTING-STARTED.md) ก่อน หากต้องการแก้ปัญหาให้ดู
[การแก้ปัญหา](TROUBLESHOOTING.md)

## เลือกคำสั่งตามงาน

| งาน | คำสั่ง | ขอบเขตและข้อควรอ่าน |
| --- | --- | --- |
| ตรวจการแก้ไขปัจจุบัน | `python -I -B -m devsift scan --changed` | เลือก staged, unstaged และ untracked; วิเคราะห์ bytes ปัจจุบัน |
| ทบทวนโปรเจกต์เดิม | `python -I -B -m devsift scan --all --legacy-mode recommend` | ตรวจ scope ทั้งหมดที่รองรับ; legacy เป็นคำแนะนำ ไม่ใช่คำสั่งแก้ไข |
| เพิ่มตัวตรวจความปลอดภัยแบบ bounded | เพิ่ม `--security` ให้คำสั่ง scan | ขอบเขต detector มีจำกัด; review ที่จำเป็นยังมีผล |
| ตรวจ change ที่ commit แล้วใน CI | `ci --base <trusted-base-ref> ...` | ต้องมี manifest/digest สำหรับ native tools; ดู [CI gate](CI-GATE.md) |
| ตรวจเครื่องมือที่พร้อมใช้ | `python -I -B -m devsift doctor` | เป็น diagnostics ไม่ได้สแกน source และไม่ติดตั้งเครื่องมือ |
| ทบทวน finding รายกรณี | `prompt <CASE-ID> --mode review --scan-input <file>` | ใช้ case ID จริงและ scan envelope ที่บันทึกไว้อย่างชัดเจน |

คำสั่งสแกนไม่ได้พิสูจน์ว่า finding ทุกข้อเกิดจากไฟล์ที่เปลี่ยน การระบุที่มาที่ยังพิสูจน์ไม่ได้
คงเป็น UNKNOWN/incomplete; โหมด recommend ไม่ใช่การอนุมัติแก้ไข legacy แบบกลุ่ม

## สแกนงานที่กำลังเปลี่ยน

```sh
python -I -B -m devsift scan --changed
python -I -B -m devsift scan --changed --security
```

`--changed` เลือกไฟล์ staged, unstaged และ untracked ที่ root ของ repository
แล้วอ่าน bytes ปัจจุบันจาก working tree การเลือกไฟล์ไม่ได้ยืนยัน lifecycle ของ finding
เพิ่ม `--security` เพื่อรัน built-in detector แบบ bounded สำหรับ credential และรูปแบบ
logging/TLS ที่รองรับ

## ทบทวน codebase เดิม

```sh
python -I -B -m devsift scan --all --legacy-mode recommend
python -I -B -m devsift scan --all --legacy-mode recommend --security
```

โหมดนี้เหมาะสำหรับ inventory และทยอยทบทวนสิ่งที่พบ โดยไม่เปลี่ยน finding เดิมให้เป็น
ข้อผิดพลาดใหม่เพียงเพราะพบในปัจจุบัน Critical security review ยังแยกจาก quality threshold
การไม่มี provider หรือ source proof ทำให้ผลไม่สมบูรณ์ได้ แม้รายการ findings ว่าง

## Native analyzer และขอบเขตที่เชื่อถือได้

native analyzer ต้องได้รับอนุญาตอย่างชัดเจนด้วย absolute manifest path และ SHA256
ที่ผู้ปฏิบัติงานได้มาจากแหล่งเชื่อถือแยกต่างหาก อย่าคำนวณ digest จาก manifest ที่กำลังตรวจ
แล้วใช้ digest นั้นอนุมัติตัวเอง:

แทน `/absolute/trusted-tools.json` และ `<independently-trusted-sha256>` ด้วย path และ
digest จริงก่อนรัน ตัวอย่างเป็น template บรรทัดเดียว จึงนำไปปรับใช้ได้ทั้ง PowerShell
และ POSIX shell:

```text
python -I -B -m devsift scan --changed --native-manifest /absolute/trusted-tools.json --native-manifest-digest TRUSTED_SHA256
```

ใช้ flag คู่เดียวกันกับ `ci` เมื่อ workflow ต้องเรียก native tools ตัวอย่างสำหรับ change
ที่ commit แล้ว โดยแทน `<trusted-base-ref>` ด้วย Git ref ที่เชื่อถือได้ก่อนรัน:

```text
python -I -B -m devsift ci --changed --base TRUSTED_BASE_REF --security --native-manifest /absolute/trusted-tools.json --native-manifest-digest TRUSTED_SHA256
```

`ci --base` ใช้ merge-base ถึง HEAD รวมกับการเปลี่ยนแปลงใน working tree ตามขอบเขตที่เลือก
หาก base หายไปหรือกำกวม การตรวจไม่ผ่านเป็น incomplete แทนการตีความว่าไม่มี change
manifest อนุญาตเฉพาะโปรแกรมที่ระบุและ pin ไว้ ไม่อนุญาตให้รันแอปพลิเคชันของเป้าหมาย
ดาวน์โหลด dependency หรือแก้ source การตั้งค่าเครื่องมือแยกจากการสแกน ดู
[native setup](NATIVE-SETUP.md) และ [CI gate](CI-GATE.md)

## อ่านผลและ exit code

คำสั่ง `--help` แสดงข้อความช่วยเหลือบน stdout และคืน exit code `0` ส่วนคำสั่งอื่นที่ใช้
argument ถูกต้องจะส่ง JSON envelope แม้ผลจะ incomplete; misuse ส่ง JSON บน stderr และคืน
exit code `3` scan และ CI วางเอกสาร JSON, Markdown และ SARIF
ที่ประกอบจากข้อมูล source-reproved ไว้ใน `data.reports` โดยค่าเริ่มต้น CLI ไม่เขียนไฟล์
การบันทึกด้วย shell redirection เป็นการเขียนที่ผู้ใช้สั่งเอง ควรเลือกปลายทางนอก source
และดูแลข้อมูลอ่อนไหวใน report

เลือก format ที่ต้องการได้ด้วยการระบุซ้ำ เช่น `--report-format markdown` หรือ
`--report-format json --report-format markdown`:

```text
python -I -B -m devsift scan --changed --report-format markdown
```

รายละเอียดการใช้ Python environment เดียวกับที่ติดตั้ง DevSift บน PowerShell และ POSIX
shell อยู่ใน [คู่มือติดตั้ง](INSTALL.md) และ [เริ่มต้นใช้งาน](GETTING-STARTED.md)

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

## ทบทวน finding รายกรณี

บันทึก scan envelope จาก stdout ด้วยวิธีที่เหมาะกับ shell ของคุณไปยังไฟล์นอก source
แล้วเลือก `CASE-ID` ที่มีอยู่จริงในผลลัพธ์:

```sh
python -I -B -m devsift prompt CASE-1 --mode review --scan-input /absolute/scan.json
```

คำสั่งนี้ประกอบ prompt จาก source ที่ตรวจยืนยันใหม่ ไม่ได้สแกนซ้ำและไม่ใช่ผล quality pass
การสร้าง prompt สำเร็จหมายถึงสร้าง prompt ได้เท่านั้น

โหมด implement ใช้สร้างข้อเสนอสำหรับทบทวน ไม่ได้แก้ไฟล์ `--approved-case` ที่ตรงกันเพียงอย่างเดียว
ไม่ใช่การอนุมัติ หาก workflow ต้องตรวจ operator record ต้องผูกกับ case, source SHA,
fingerprint, prompt digest, mode และช่วงเวลาที่ใช้ได้ แม้ record ตรงกันก็อนุญาตเพียงการวางแผน
ด้วยคนเมื่อผลกระทบยังไม่ทราบ ไม่มีคำสั่งใดใน workflow นี้นำ patch ไปใช้โดยอัตโนมัติ
ดู [case prompts and approval](CASE-PROMPTS.md)

`report --latest` และการค้นหา storage อัตโนมัติของ `explain` ยังไม่พร้อมใช้งาน
ใช้ report ที่ส่งคืนจากคำสั่งปัจจุบันและระบุ scan input เองตามรูปแบบที่รองรับ

## เริ่มจาก agent chat

ตัวอย่างนี้เป็นข้อความสำหรับ host ที่ติดตั้ง DevSift Skill แล้ว ไม่ใช่คำสั่ง terminal:

> ใช้ DevSift ตรวจการเปลี่ยนแปลงใน working tree เพิ่ม security checks แบบ bounded
> แล้วรายงาน scope, analyzer ที่ขาด, สถานะ complete และ finding ที่ต้องให้คนทบทวน

Skill ช่วย agent ใช้ CLI และอธิบายผลตามข้อจำกัดที่มี แต่ไม่เพิ่มความสามารถของ host
ไม่ติดตั้ง CLI ให้อัตโนมัติ และไม่แปลงคำขอตรวจเป็นสิทธิ์แก้ source

## ข้อจำกัดความพร้อมใช้งาน

`report --latest` และ storage discovery สำหรับ `explain` ยัง pending; อย่าอ้างว่ามีการดึง
ผลเก่าหรืออธิบายตำแหน่งที่ไม่ได้ยืนยัน `prompt` ไม่ใช่ scan pass หรือ patch application
การขาด native analyzer ทำให้ coverage ของภาษานั้นไม่พร้อม ไม่ใช่ผล clean
ดู [สารบัญเอกสาร](README.md) สำหรับ workflow และเอกสารอื่น
