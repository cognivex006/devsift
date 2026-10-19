# เตรียม analyzer ครั้งเดียว แล้วใช้ DevSift lint ได้ตามปกติ

ทะเบียนผู้ใช้และ companion ในหน้านี้เป็น **candidate 0.1.16** ตรวจ `devsift setup --help`
ของ CLI ที่ติดตั้ง รุ่น 0.1.15 และเก่ากว่ายังใช้ manifest/digest แบบระบุทุกคำสั่ง
Platform/release gates ยังต้องผ่านก่อนเผยแพร่ เอกสารนี้ไม่ได้ยืนยันว่า assets ใหม่ public แล้ว

## ติดตั้งปกติ

ตัวติดตั้งใหม่เตรียม verified platform companion พร้อม CLI และลงทะเบียน analyzer
ใน user scope ดู [INSTALL](INSTALL.md) ไม่ต้องมี .NET/Go/Node SDK เพื่อใช้ชุด binary นี้
การตรวจ source/Git evidence ยังต้องมี Git ที่ติดตั้งและเชื่อถือได้ กับ target Git root
Helper สี่ตัวให้ coverage ตามกฎที่รองรับ ไม่ได้แปลว่าตรวจทุกภาษา ทุก rule หรือ business impact
ชุดนี้ครอบคลุม C#, SQL, Go และ TypeScript/JavaScript ตาม provider ไม่มี Python quality
analyzer ใหม่ใน workflow นี้ `analysis_ready` หมายถึง configured native providers พร้อม
Doctor ยังอาจ exit 2 เพราะภาษาอื่นเช่น Python ไม่ครอบคลุม ให้ตรวจราย provider แล้วรัน
scope ที่รองรับต่อได้ ไม่ตีความว่าไม่มี analyzer ทั้งหมดจาก overall exit เพียงตัวเดียว

ตรวจ readiness แยกจากการสแกน:

```text
devsift setup --status
devsift doctor
```

`setup --status` อ่านสถานะทะเบียน ไม่ดาวน์โหลด ไม่ลงทะเบียนใหม่ และไม่วิเคราะห์ source
Doctor ตรวจ runtime/provider และ probe เฉพาะโปรแกรมที่ได้รับ trust แล้ว ไม่มีการ build
หาก registry หายหรือ provider ใช้ไม่ได้ อย่าอ้างว่า lint ผ่านจากการทำ inventory อย่างเดียว

## ลงทะเบียน manifest ที่ทบทวนแล้ว

เมื่อมี native setup เดิมที่เชื่อถือได้ ลงทะเบียนครั้งเดียว:

```text
devsift setup --native-manifest ABSOLUTE_MANIFEST --native-manifest-digest TRUSTED_SHA256
devsift setup --status
devsift doctor
```

แทน placeholders ด้วย absolute path และ SHA256 ของ manifest bytes ที่ได้รับมาจาก
แหล่ง trust ที่ตรวจทานแล้ว การคำนวณ digest ของ manifest ที่พบใน target แล้วใช้อนุมัติ
ตัวเองไม่สร้างความน่าเชื่อถือ Manifest เป็น executable configuration; ต้องทบทวน
โปรแกรม, arguments, runtime/helper pins และ SQL dialect ก่อนลงทะเบียน

ทะเบียนอยู่ที่ `~/.local/share/devsift/analyzers.json` นอก target ใช้โดย `scan`, `doctor`
และ `ci` โดยปริยาย จึงไม่ต้องป้อน path/digest ซ้ำ การลงทะเบียนต้องเป็น explicit setup
และไม่เกิดจากการอ่าน project configuration หรือค้นหาไฟล์ใน target

```text
devsift scan --all --legacy-mode recommend --summary --report-language th
devsift ci --changed --base TRUSTED_BASE_REF --summary
```

การระบุ `--native-manifest` และ `--native-manifest-digest` เป็นคู่ในคำสั่งใดคำสั่งหนึ่ง
ใช้แทน registry สำหรับคำสั่งนั้น ไม่แก้ทะเบียน ถ้าคู่ explicit ผิด ไม่ fallback ไป trust
อีกชุดเพื่อซ่อนข้อผิดพลาด การส่งมาเพียงตัวเดียวไม่ครบเป็น misuse

## ติดตั้ง companion แบบ offline

สำหรับ operator ที่ได้รับ ZIP และ digest จากแหล่งที่เชื่อถือได้:

```text
devsift setup --analyzer-bundle ABSOLUTE_ZIP --bundle-digest TRUSTED_SHA256
devsift setup --status
```

ชื่อ release asset ใช้รูปแบบ `devsift-analyzers-PLATFORM-ARCH.zip` และ `.zip.sha256`
โดย platform เป็น windows/linux/macos และ arch เป็น x64/arm64 เฉพาะคู่ที่มี asset
และผ่าน validation จริงเท่านั้น ไม่อนุมานว่ามีครบทุกคู่ ถ้า platform ไม่รองรับให้รายงาน
availability ตามจริง ไม่ติดตั้ง companion คนละระบบหรือ build target เพื่อทดแทน
Checksum เป็น integrity record ไม่ใช่ลายเซ็น ต้องเชื่อถือผู้เผยแพร่/ช่องทางที่เลือกด้วย

Installer/setup แตก companion เฉพาะพื้นที่ที่เป็นเจ้าของ ตรวจ expected pins และปรับ
ตำแหน่งให้ตรงกับการติดตั้งนั้น การปรับ path ไม่ใช่การ repin โปรแกรมที่เปลี่ยน bytes
ไม่มีการรับ manifest จาก target หรือแก้ hash ให้ตรงกับ executable ที่ยังไม่ผ่าน trust

## ขอบเขต trust และข้อจำกัด

ทั้ง manifest ต้องผ่าน schema/digest validation ก่อน probe ใด ๆ ทุก execution ตรวจ
expected executable/helper hashes เดิม ไม่คำนวณ pins ใหม่เพื่ออนุมัติไฟล์ที่ถูกเปลี่ยน
Manifest schema 1 ใช้ `schema_version` และ `tools`; แต่ละ entry มี definition/dialect
พร้อม identity/version/languages, process contract, absolute paths และ expected hashes
SQL เลือก `tsql150`/`tsql160` ชัดเจน ไม่เดา dialect จากโปรเจกต์

Duplicate keys/identities, unknown fields, overlapping tool languages, malformed limits
และ digest mismatch ถูกปฏิเสธ ไม่สะท้อน commands หรือ raw tool stderr ใน error สาธารณะ
Trust นี้อนุญาตให้รัน helper ที่เลือก ไม่ใช่ OS filesystem/network sandbox ของโปรแกรมนั้น

การสแกนไม่ดาวน์โหลด ไม่ติดตั้ง dependencies ไม่ build helpers หรือรันแอปของ target
Provider readiness ไม่ใช่ source analysis, clean scan หรือครอบคลุมทุก semantic rule
ผลที่ missing/failed/unresolved ต้องคง incomplete แม้ findings ว่าง รายงาน UNKNOWN ตามจริง

## Advanced source setup สำหรับผู้ดูแล

หากเลือกสร้าง helper เอง ใช้ DevSift checkout ที่ทบทวนแล้วและ toolchain ตาม
`python tools/build_native.py` ขั้นตอนนี้ต้องมี SDK/runtime ที่ pin ไว้ และอาจดาวน์โหลด
dependencies ของ DevSift เอง จึงเป็น setup ที่ได้รับอนุญาตแยกจาก ordinary scan
ไม่ใช่ขั้นตอนบังคับของผู้ใช้ companion installer

Builder เก็บ manifest และ digest ใน `.devsift/local/native-manifest.json` กับ
`.devsift/local/native-manifest.sha256` ของ checkout ที่ใช้ setup ให้ตรวจโปรแกรม/pins
และเก็บ digest จากขั้นตอนที่เชื่อถือได้ก่อนลงทะเบียนด้วย `devsift setup` ด้านบน
การ build, เปลี่ยน runtime หรือ update helper เป็นการเปลี่ยน trust โดยชัดแจ้ง
ห้ามเรียก builder อัตโนมัติเพียงเพราะ scan พบว่า provider ยังไม่พร้อม
