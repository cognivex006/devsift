# Lint จนจบและส่งรายงานครบทุก case

DevSift ตั้งแต่ 0.1.15 เก็บ session และ paged reports นอก source ทะเบียนผู้ใช้,
`--report-language` และ combined `REPORT.md` ในหน้านี้อยู่ใน **candidate 0.1.16**
ตรวจ installed help ก่อนใช้; final platform/release checks ยังไม่ครบ ไม่อ้างว่า
public release เก่ามี flags ใหม่แล้ว

เมื่อ setup ที่เชื่อถือได้ลงทะเบียนไว้ ให้รันจาก target Git root:

```text
devsift setup --status
devsift scan --all --legacy-mode recommend --summary --report-language th
```

ภาษาอังกฤษใช้ `en` คำขอ project review ทั่วไปเลือกทั้ง repository; `--changed` ใช้เฉพาะ
เมื่อขอตรวจการเปลี่ยนแปลง Native manifest/digest ไม่ต้องใส่ซ้ำเมื่อใช้ user registration
คู่ explicit flags ยังคง override ได้ ดู [Native setup](NATIVE-SETUP.md)
หาก setup หายให้แก้ readiness ตาม scope ที่ได้รับอนุญาต ไม่ทำ silent install/build ระหว่าง scan

## รับรายงานที่เปิดอ่านและใช้ต่อได้

`--summary` คืน compact JSON ให้อ่านแม้ exit 2 ไม่ dump inventory ยาวลง tool response

| ข้อมูล | วิธีใช้ |
| --- | --- |
| `data.report_bundle.report` | path ตรงของ human `REPORT.md` ใน session root ส่งลิงก์นี้ให้ผู้ใช้ |
| `data.target_count`, `data.counts` | ขอบเขตและ actual analyzer coverage; skipped ไม่ใช่ analyzed |
| `data.finding_count` | จำนวน findings ทั้งหมด ไม่ใช้ `findings: []` ใน summary แทนจำนวนนี้ |
| `data.execution` | แยกงานใหม่จากผลเดิมที่ source/readiness ตรวจซ้ำแล้วใช้ต่อ |
| `data.report_bundle.index` | JSON index ทุก page/case พร้อม bytes และ SHA256 |
| `data.report_bundle.markdown_index` | ดัชนีเปิด artifacts ประกอบทุก page |
| `reports_complete` | รายงานทุก case/format ที่เลือกและ artifact integrity ครบ |
| `analysis_complete`, `complete`, errors | ข้อจำกัดจริงของ analyzer/source proof |

เริ่มคำตอบด้วย executed coverage, findings, สาเหตุ incomplete และ next action แล้วให้
ลิงก์ `REPORT.md` โดยตรง ไม่จบเพียง “เสร็จแล้ว” หรือส่ง storage folder ให้ค้นหาเอง
กรณี resume ให้บอกด้วยว่าส่วนใด reused ไม่เรียก cached coverage ว่า analyzer calls ใหม่

รายงานมนุษย์ต้องมีทุก case; เปิดทุก JSON/Markdown page จาก index แบบ incremental
ไม่เลือกอ่านเพียง top findings แล้วอ้างว่าครบ แต่ละ page มี requested formats และ
`scan.json` สำหรับ `prompt --scan-input` ของ case นั้น เก็บ machine IDs/path/SHA ตามจริง
ขนาดใหญ่ไม่ใช่เหตุให้ตัด case; การแปลต้องไม่เติม BEFORE, AFTER, consumer หรือผล test ที่ไม่มี
หากไม่ใช้ summary CLI stream findings/targets ทุกแถวไป stdout ผลเล็กอาจมี `data.reports` inline

รายงานครบไม่แปลว่าโค้ดผ่าน: parser error, analyzer ที่ขาด, unresolved source และ UNKNOWN
ต้องปรากฏตามจริง ถ้า executed เป็น 0 ให้บอกว่า source ยังไม่ได้วิเคราะห์ด้วย analyzer
ไม่ใช้ inventory เป็น lint pass ส่วนใดสูญหาย/เปลี่ยน/สร้างไม่ได้ต้องคง `reports_complete: false`

## เลือก directory และทำต่อ

ค่าเริ่มต้นอยู่ใต้ `~/.local/share/devsift/scans/` นอก target หรือระบุ absolute directory ใหม่:

```text
devsift scan --all --summary --report-language th --report-dir ABSOLUTE_NEW_DIRECTORY
devsift scan --all --summary --report-language th --resume ABSOLUTE_EXISTING_SESSION
```

ใช้ scope, registration/explicit trust, security, base, policy, formats และภาษาเดิม
ระบบตรวจ root/configuration, source และ current provider readiness อีกครั้ง
ไฟล์ที่เปลี่ยน/ยังวิเคราะห์ไม่ครบตรวจใหม่ ไฟล์ที่ถูกลบไม่คงใน coverage รอบใหม่
การ reuse ผลสมบูรณ์ที่ bytes ตรงกันไม่ข้าม current trust/readiness checks

Ctrl+C เก็บกวาดลูก process/หน้าจอและรักษาผลที่ commit ลง owned session เพื่อ resume
ไม่ overwrite user directory ไม่เปิด symlink/junction session และมี writer ได้ครั้งละตัว
Session/report writes อยู่นอก source; ไม่แก้ Git configuration, dependency หรือ build target

## งานนานและไฟล์ใหญ่

TTY ใช้สองบรรทัดเดิมแสดงไฟล์/ผล/เวลาและ spinner ของ stage จริง stdout เป็น JSON
redirected output ไม่มี ANSI animation Complete native transport รอจนจบหรือยกเลิก
พร้อมตรวจ protocol, actual exit, expected hash pins และ cleanup ไม่มี timer ที่สร้างเปอร์เซ็นต์ปลอม
Helper ใช้ private source snapshot และ diagnostics transport นอก target จึงไม่รับเพดาน
inline JSON มาเป็นเพดาน repository ไม่แบ่งโค้ดตาม bytes แล้วอ้างว่าเทียบเท่า AST ทั้งไฟล์

Parser ยังต้องใช้ RAM สำหรับไฟล์ปัจจุบัน ความล้มเหลวต้องเป็นข้อมูลในรายงาน ไม่ทิ้ง cases
ของไฟล์อื่น Oversized excerpts อาจเป็น `[REDACTED]` ทั้งช่วง แต่ coordinates/SHA ยังต้องพิสูจน์

CI ใช้ user registration และ report workflow เดียวกัน:

```text
devsift ci --all --base TRUSTED_BASE_REF --summary --report-language th
```

Source attribution, legacy recommendations, security review และการอนุมัติแก้ไขราย case
ยังคงเดิม รายงานหรือ prompt ไม่ให้สิทธิ์แก้ source อัตโนมัติ
