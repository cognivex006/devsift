# วิธีแก้ปัญหา

DevSift fail-closed: เมื่อหลักฐานหรือ provider coverage ไม่ครบ ผลต้องคงสถานะ
incomplete เริ่มจากตรวจ `complete`, `status`, `errors`, scope และ provider
coverage ไม่ใช่ดูแค่รายการ findings

| อาการ | ความหมาย | วิธีตรวจ/แก้ |
| --- | --- | --- |
| `No module named devsift` | Python environment ที่เลือกไม่มี CLI ติดตั้งอยู่ | ใช้ interpreter จาก environment ที่ติดตั้ง DevSift แล้ว จาก target Git root รัน `python -I -B -m devsift --help`; isolated mode จะไม่ fallback ไป source ใน current directory หรือ `PYTHONPATH` ดู [INSTALL.md](INSTALL.md) |
| Doctor แจ้ง provider unavailable; scan จบด้วย `2` | Doctor รายงาน availability แต่ไม่ได้ scan source; native providers ที่ไม่ได้ตั้งค่าทำให้ analysis ที่เกี่ยวข้องไม่ครบ | ตรวจ provider diagnostics หากต้องใช้ native analysis ให้ทำ trusted setup ตาม [NATIVE-SETUP.md](NATIVE-SETUP.md) แล้วส่ง absolute manifest path พร้อม digest ที่เชื่อถือได้อย่างอิสระ |
| Native manifest หาย, รูปแบบไม่ถูกต้อง หรือ digest ไม่ตรง | Native configuration เป็น input ที่รันโปรแกรมได้ และยังไม่ผ่านการตรวจ trust/integrity | ตรวจว่า bytes ของ manifest ตรงกับ SHA256 ที่เชื่อถือได้จากภายนอก path เป็น absolute และ helper ทุกตัวมีอยู่พร้อม pinned hash อย่าคำนวณ digest ใหม่จาก manifest ที่ยังไม่ตรวจทานแล้วใช้ยืนยันความน่าเชื่อถือ ตัดสินใจ rebuild หรือเปลี่ยน pins ผ่าน trusted setup อย่างชัดเจนเท่านั้น |
| ไม่พบ findings แต่ `complete` เป็น false | Analysis บางส่วนที่เลือกไว้ทำไม่สำเร็จ รายการ findings ว่างจึงไม่ใช่ผล clean | ตรวจ `errors` และ provider coverage คืน provider ที่ขาดหรือแก้ปัญหา source/history/configuration แล้วรันใหม่ คงสถานะ incomplete ไว้จน scope ที่ต้องการวิเคราะห์ครบ |
| Scan/CI จบด้วย `2` และ origin/lifecycle เป็น `UNKNOWN` | อาจยืนยัน source ได้ แต่ Git history ยังบอกไม่ได้ว่า finding ใหม่หรือเป็น legacy | ตรวจ Git root, CI base ที่ระบุ และประวัติ commit ที่มีอยู่ สำหรับ CI ให้ส่ง `--base` ที่ต้องการ อย่าเปลี่ยน UNKNOWN เป็น label อื่นหรือถือว่า clean เพื่อให้ gate ผ่าน ดู [CI-GATE.md](CI-GATE.md) |
| `ci` จบด้วย `2` และแจ้ง base/history หรือ review ค้าง | CI ต้องใช้ source scope และ history ที่ระบุเพื่อจำแนก finding; critical security review เป็นข้อกำหนดอิสระ | ตรวจว่า base ref มีใน local repository และมี history ที่ต้องใช้ จัดการ review ที่แจ้งไว้ quality threshold ปกติลบล้าง critical security review ไม่ได้ |
| `report --latest` หรือ `explain` ใช้ไม่ได้ | Persisted report storage/discovery backend ยัง pending | ใช้ report ปัจจุบันใน `data.reports` หากต้องการสร้าง case prompt ให้บันทึก scan envelope แยกจาก source แล้วส่ง path ด้วย `prompt --scan-input`; คำสั่งนี้ตรวจ source ซ้ำแต่ไม่ได้ scan ใหม่ |
| Prompt ขอ `--scan-input` หรือแจ้ง source unresolved | Prompt generation ต้องใช้ scan envelope ที่ระบุเองและ source proof ที่ตรงกับปัจจุบัน | บันทึก JSON scan command envelope นอก source tree ส่ง absolute path ด้วย `--scan-input` และใช้ case ID ที่ตรงกับ envelope อย่าใช้ rendered report เป็นหลักฐาน ความสำเร็จของ review คือ prompt generation ไม่ใช่ analysis |
| `doctor` จบด้วย `2` | การตรวจ runtime/provider ขาด ไม่ถูกต้อง หรือไม่ครบ Doctor ไม่วิเคราะห์ target source และไม่ติดตั้ง tools | ทำตาม diagnostic action ที่ระบุแล้วรัน doctor ซ้ำ Doctor จะ probe native program เฉพาะเมื่อส่ง manifest/digest pair อย่างชัดเจน ดู [DOCTOR.md](DOCTOR.md) |
| CLI จบด้วย `3` | คำสั่งหรือ option ไม่ถูกต้อง หรือ argument pair ที่จำเป็นมีรูปแบบผิด | ตรวจ `python -I -B -m devsift <command> --help` อีกครั้ง ตัวเลือกเข้มงวด และ manifest/digest ต้องส่งเป็นคู่ |

## รักษาหลักฐานเดิม

อย่าแก้ target source หรือติดตั้ง/build target dependencies เพื่อเลี่ยงปัญหา
คำสั่ง DevSift อ่านอย่างเดียว ส่วนการติดตั้งและ native helper setup เป็นขั้นตอนแยก
คำอธิบายหรือ proposal จาก agent ไม่ได้แก้ไฟล์และแทนการ review ไม่ได้ หากต้องการ
ดู source position, redaction และกรณี unresolved ให้อ่าน
[ตัวอย่าง report](cases/REPORT-WALKTHROUGH.md); ความหมายคำสั่งทั้งหมดอยู่ที่
[รายละเอียด CLI](CLI.md)
