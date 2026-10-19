# วิธีแก้ปัญหา

DevSift fail-closed: เมื่อหลักฐานหรือ provider coverage ไม่ครบ ผลต้องคงสถานะ
incomplete เริ่มจากตรวจ `complete`, `status`, `errors`, scope และ provider
coverage ไม่ใช่ดูแค่รายการ findings

| อาการ | ความหมาย | วิธีตรวจ/แก้ |
| --- | --- | --- |
| ไม่มีทะเบียน analyzer / `setup --status` ยังไม่พร้อม | CLI มีอยู่แต่ native lint ยังไม่พร้อม ไม่ใช่ scan ที่ตรวจ source แล้ว | ใช้ตัวติดตั้ง 0.1.16+ หรือลงทะเบียน reviewed manifest ครั้งเดียวตาม [NATIVE-SETUP](NATIVE-SETUP.md) ไม่ดาวน์โหลด/build ระหว่าง ordinary scan |
| executed เป็น 0 แต่เห็น inventory/targets จำนวนมาก | แค่ enumerate scope ยังไม่ใช่ analyzer execution | บอกจำนวน executed ตามจริง ตรวจ provider/readiness แล้วเสนอขั้นตอน setup ไม่สรุปว่า clean จาก findings ว่าง |
| ได้เพียง JSON/folder ไม่มีรายงานให้เปิด | ต้องส่งตัวรายงานที่ใช้ทำงานต่อได้ | Source workflow ใหม่คืน `data.report_bundle.report` สำหรับ `REPORT.md` ส่ง direct link พร้อม findings, incomplete causes และ next action อ่านทุก case/page ไม่ส่งเฉพาะ top cases |
| `setup` หรือ `--report-language` ไม่อยู่ใน help | CLI เก่า เช่น 0.1.15 ยังไม่มี workflow ของ 0.1.16 | อัปเดตเป็น 0.1.16+ เมื่อได้รับอนุญาต ใช้ flags ที่ installed help รองรับ ไม่ส่ง flags ใหม่ให้ CLI เก่า |
| `devsift` not found / ไม่รู้จักคำสั่ง | PATH ของ terminal หรือ host ยังไม่เห็น launcher | เปิด terminal และ agent host ใหม่ ตรวจ `~/.local/bin` บน PATH หรือ activate environment ที่ติดตั้ง CLI ดู [INSTALL.md](INSTALL.md) |
| `REDACTION_FAILED` บน repository ขนาดใหญ่ใน 0.1.13–0.1.14 | ผล inventory ชนเพดานรวมของ redaction; 0.1.14 เพิ่มเพดาน nodes แต่ยังมีเพดานข้อความรวม | การแก้ใน 0.1.15 แยกตรวจทีละ target/finding และไม่นำ inventory ไปนับเป็นขนาด input ของรายงาน ข้อจำกัดของแต่ละรายการยังคงอยู่ ห้ามพิมพ์ข้อมูลที่ยังไม่ผ่าน redaction เพื่อหลบข้อผิดพลาด |
| Tool host แสดง Failed แต่ stdout มี JSON และ exit code2 | คำสั่งคืนผล incomplete ที่ใช้งานรายงานได้ | Parse JSON แม้ exitไม่เป็น0 อ่าน counts, targets และ reports ก่อนสรุป ไม่ใช้ป้าย Failed ของ shell แทนสถานะภายในผล |
| `No module named devsift` | Environment ที่ launcher อ้างถึงไม่สมบูรณ์ | ติดตั้งหรืออัปเดตใหม่ แล้วตรวจ `devsift --help` อย่าเพิ่ม source ของ target เข้า import path |
| Doctor แจ้ง provider unavailable; scan จบด้วย `2` | Doctor รายงาน availability แต่ไม่ได้ scan source; providers ที่ขาดทำให้ analysis ที่เกี่ยวข้องไม่ครบ | ตรวจ user registration และ diagnostics ตาม [NATIVE-SETUP.md](NATIVE-SETUP.md) ลงทะเบียน reviewed manifest/digest ครั้งเดียว หรือใช้ explicit pair override ไม่ต้องป้อนซ้ำทุกคำสั่งเมื่อ registry ใช้งานได้ |
| Native manifest หาย, รูปแบบไม่ถูกต้อง หรือ digest ไม่ตรง | Native configuration เป็น input ที่รันโปรแกรมได้ และยังไม่ผ่านการตรวจ trust/integrity | ตรวจว่า bytes ของ manifest ตรงกับ SHA256 ที่เชื่อถือได้จากภายนอก path เป็น absolute และ helper ทุกตัวมีอยู่พร้อม pinned hash อย่าคำนวณ digest ใหม่จาก manifest ที่ยังไม่ตรวจทานแล้วใช้ยืนยันความน่าเชื่อถือ ตัดสินใจ rebuild หรือเปลี่ยน pins ผ่าน trusted setup อย่างชัดเจนเท่านั้น |
| ไม่พบ findings แต่ `complete` เป็น false | Analysis บางส่วนที่เลือกไว้ทำไม่สำเร็จ รายการ findings ว่างจึงไม่ใช่ผล clean | ตรวจ `errors` และ provider coverage คืน provider ที่ขาดหรือแก้ปัญหา source/history/configuration แล้วรันใหม่ คงสถานะ incomplete ไว้จน scope ที่ต้องการวิเคราะห์ครบ |
| Scan/CI จบด้วย `2` และ origin/lifecycle เป็น `UNKNOWN` | อาจยืนยัน source ได้ แต่ Git history ยังบอกไม่ได้ว่า finding ใหม่หรือเป็น legacy | ตรวจ Git root, CI base ที่ระบุ และประวัติ commit ที่มีอยู่ สำหรับ CI ให้ส่ง `--base` ที่ต้องการ อย่าเปลี่ยน UNKNOWN เป็น label อื่นหรือถือว่า clean เพื่อให้ gate ผ่าน ดู [CI-GATE.md](reference/CI-GATE.md) |
| `ci` จบด้วย `2` และแจ้ง base/history หรือ review ค้าง | CI ต้องใช้ source scope และ history ที่ระบุเพื่อจำแนก finding; critical security review เป็นข้อกำหนดอิสระ | ตรวจว่า base ref มีใน local repository และมี history ที่ต้องใช้ จัดการ review ที่แจ้งไว้ quality threshold ปกติลบล้าง critical security review ไม่ได้ |
| `report --latest` หรือ `explain` ใช้ไม่ได้ | คำสั่งค้นหา latest/อธิบายแบบอัตโนมัติยัง pending | ใช้ `data.reports` ของผลขนาดเล็ก หรือ index ใน `data.report_bundle` และเลือก `scan.json` ของ page นั้นด้วย `prompt --scan-input`; คำสั่งนี้ตรวจ source ซ้ำแต่ไม่ได้ scan ใหม่ |
| Prompt ขอ `--scan-input` หรือแจ้ง source unresolved | Prompt generation ต้องใช้ scan envelope ที่ระบุเองและ source proof ที่ตรงกับปัจจุบัน | บันทึก JSON scan command envelope นอก source tree ส่ง absolute path ด้วย `--scan-input` และใช้ case ID ที่ตรงกับ envelope อย่าใช้ rendered report เป็นหลักฐาน ความสำเร็จของ review คือ prompt generation ไม่ใช่ analysis |
| `doctor` จบด้วย `2` | การตรวจ runtime/provider ขาด ไม่ถูกต้อง หรือไม่ครบ Doctor ไม่วิเคราะห์ target source และไม่ติดตั้ง tools | ทำตาม diagnostic action แล้วรัน doctor ซ้ำ Source CLI probe โปรแกรมที่ได้รับ trust จาก registry หรือ explicit pair; readiness ไม่ได้หมายถึง coverage ทุกภาษา ดู [DOCTOR.md](reference/DOCTOR.md) |
| CLI จบด้วย `3` | คำสั่งหรือ option ไม่ถูกต้อง หรือ argument pair ที่จำเป็นมีรูปแบบผิด | ตรวจ `devsift <command> --help` อีกครั้ง ตัวเลือกเข้มงวด และ manifest/digest ต้องส่งเป็นคู่ |
| Windows path ยาวแล้ว setup/report ใช้ไม่ได้ในรุ่นเก่า | ตั้งแต่ 0.1.16 รองรับ canonical home/namespace containment และ deep owned report paths | อัปเดต CLI ไม่แก้ global LongPaths policy หรือ source เพื่อหลบข้อผิดพลาด หากยังล้มเหลวให้เลือก report directory สั้นที่อยู่นอก source และตรวจ diagnostics |

## รักษาหลักฐานเดิม

อย่าแก้ target source หรือติดตั้ง/build target dependencies เพื่อเลี่ยงปัญหา
Scan/CI/Doctor ไม่แก้ target ส่วน installation/setup อาจเขียน owned registration และ
verified companion ภายนอก target เมื่อได้รับอนุญาต
คำอธิบายหรือ proposal จาก agent ไม่ได้แก้ไฟล์และแทนการ review ไม่ได้ หากต้องการ
ดู source position, redaction และกรณี unresolved ให้อ่าน
[ตัวอย่าง report](cases/REPORT-WALKTHROUGH.md); ความหมายคำสั่งทั้งหมดอยู่ที่
[รายละเอียด CLI](reference/CLI.md)

Complete runs starting in 0.1.15 create all report pages and an index; there is no
aggregate 1,000-case cutoff. See [complete scans](COMPLETE-SCANS.md). An actual
`REPORT_UNAVAILABLE` means a page is missing, changed or could not be rendered:
keep the job incomplete, inspect stored coverage/cases, and resume after resolving
the declared failure. Do not label partial raw candidates a complete report.
