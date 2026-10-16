# ติดตั้ง DevSift

DevSift ต้องใช้ Python 3.12 ขึ้นไป รวมถึงรุ่นที่ใหม่กว่า ให้ติดตั้งจาก source checkout ของ DevSift ที่
เชื่อถือได้ลงใน virtual environment เวอร์ชัน package ปัจจุบันคือ `0.0.0.dev0`
ซึ่งเป็น development placeholder รายการ Python runtime dependencies ว่างเปล่า
การติดตั้งอาจใช้ build backend ที่ pin ไว้และเขียนไฟล์ใน virtual environment
การติดตั้งแยกจากการ scan ซึ่งเป็นคำสั่งอ่านอย่างเดียว

## Checkout source ที่เชื่อถือได้และติดตั้ง CLI

จากโฟลเดอร์ parent ให้ clone repository ที่เชื่อถือได้:

```text
git clone https://github.com/orchex006/devsift.git
cd devsift
```

Windows PowerShell: สร้าง environment แล้วเก็บ absolute path ของ interpreter ไว้
เพื่อเรียกใช้ต่อหลังเปลี่ยนโฟลเดอร์:

```powershell
py -3.12 -m venv .venv
$DevSiftPython = (Resolve-Path .venv\Scripts\python.exe).Path
& $DevSiftPython -m pip install .
& $DevSiftPython -I -B -m devsift --help
```

Linux หรือ macOS:

```sh
python3.12 -m venv .venv
DEVSIFT_PYTHON="$(pwd)/.venv/bin/python"
"$DEVSIFT_PYTHON" -m pip install .
"$DEVSIFT_PYTHON" -I -B -m devsift --help
```

ถ้าเครื่องมี Python รุ่นใหม่กว่าแต่ไม่มี 3.12 ให้เลือก interpreter รุ่นนั้น
เพื่อสร้าง environment ได้เช่นกัน โดยต้องเป็น Python 3.12 ขึ้นไป

หรือ activate virtual environment ใน shell ก่อนใช้ `python` เมื่อเปลี่ยนไปยัง
consumer repository ให้ใช้ interpreter จาก environment ที่ติดตั้ง DevSift ไว้
(หรือ activate environment ที่นั่น) โหมด `-I` จะไม่ค้นหา DevSift จาก
`PYTHONPATH` หรือ current directory ของ consumer อย่าแก้ปัญหาด้วยการเพิ่ม path
ของ target repository เข้า Python import path

## อัปเดต CLI และ skill

เมื่อต้องการอัปเดต ให้ใช้ DevSift checkout ที่ตรวจสอบและทบทวน source แล้ว จาก
โฟลเดอร์ checkout นั้นเรียก pip ด้วย interpreter เดิม:

```powershell
Set-Location 'D:\path\to\reviewed-devsift-checkout'
& $DevSiftPython -m pip install .
```

หรือ Linux/macOS:

```sh
cd /path/to/reviewed-devsift-checkout
"$DEVSIFT_PYTHON" -m pip install .
```

แทน path ตัวอย่างด้วยตำแหน่ง checkout ที่ตรวจสอบแล้ว คำสั่งนี้ติดตั้ง CLI
version จาก checkout นั้น ไม่มีคำสั่ง updater ที่ดาวน์โหลดหรือเปลี่ยน source
ให้อัตโนมัติ หากใช้ agent skill ให้คัดลอก `skills/devsift/SKILL.md` และ
`skills/devsift/CONSUMER-SCOPE.md` จาก checkout ที่อัปเดตแล้วไปยัง skill directory
ที่ host ระบุ โดยคงชื่อไฟล์และ relative link แล้วทำตามขั้นตอน reload/register
ของ host เอง

## ติดตั้ง consumer skill ด้วยตนเอง

Pip ติดตั้ง CLI แต่ไม่ได้ติดตั้ง agent skill หาก host รองรับ skill ที่ผู้ใช้จัดการ
ให้คัดลอก **ทั้งสองไฟล์** คือ `skills/devsift/SKILL.md` และ
`skills/devsift/CONSUMER-SCOPE.md` ไปยัง directory สำหรับ skill ที่ host ระบุ
คงชื่อไฟล์และ relative link แล้วทำตามวิธี register/reload ของ host ตำแหน่งและ
การตั้งค่า host แตกต่างกัน DevSift จึงไม่สมมติว่ามี directory กลาง ไม่ register
ให้เอง และยืนยันไม่ได้ว่า host โหลด skill แล้ว ใช้ CLI โดยตรงได้แม้ไม่มี agent
host

## ตรวจ installation จาก target repository

เปลี่ยนไปที่ Git root ของ target repository แล้วเรียก interpreter ตัวเดิมที่ติดตั้ง
DevSift ไว้ ตัวอย่าง PowerShell โดยแทน path ด้วย Git root จริงของคุณ:

```powershell
$TargetRepo = 'D:\path\to\your-repo'  # เปลี่ยนเป็น path ของ target Git root
Set-Location $TargetRepo
& $DevSiftPython -I -B -m devsift doctor
& $DevSiftPython -I -B -m devsift scan --changed
```

ตัวอย่าง Linux/macOS:

```sh
TARGET_REPO=/path/to/your-repo  # เปลี่ยนเป็น path ของ target Git root
cd "$TARGET_REPO"
"$DEVSIFT_PYTHON" -I -B -m devsift doctor
"$DEVSIFT_PYTHON" -I -B -m devsift scan --changed
```

Doctor ตรวจ availability ของ provider แต่ไม่ได้ scan source หากยังไม่ได้ตั้งค่า
native provider การ scan อาจไม่ครบแม้ไม่พบ finding ดู
[เริ่มใช้งาน](GETTING-STARTED.md) และ
[วิธีแก้ปัญหา](TROUBLESHOOTING.md) ก่อนแปลผล

## Native analyzers ที่เป็นทางเลือก

Native setup เป็นขั้นตอนแยกที่ต้องรันจาก DevSift checkout ซึ่งเชื่อถือได้ และ
จำเป็นเมื่อต้องการ coverage จาก native language providers ที่ setup สร้างไว้
ต้องมี .NET SDK 9.0.205, Go 1.21.3, Node และ npm จาก checkout ที่เชื่อถือได้
ให้อ่าน [คู่มือตั้งค่า native](NATIVE-SETUP.md) แล้วสั่งโดยเจตนา:

```text
python tools/build_native.py
```

คำสั่งนี้ build helper ของ DevSift เอง และติดตั้ง locked dependencies ของ frontend
helper ไม่ได้ build consumer application เก็บไฟล์ที่สร้างใน
`.devsift/local/native-manifest.json` และ `.devsift/local/native-manifest.sha256`
ภายใน DevSift checkout ที่เชื่อถือได้ ทบทวน executable configuration และยืนยัน
digest จากช่องทางอิสระที่เชื่อถือได้ก่อนใช้คู่ไฟล์นี้ ต้องส่ง absolute manifest
path ควบคู่กับ digest ที่เชื่อถือได้ การส่งคู่นี้อนุญาตให้รันโปรแกรมที่ระบุไว้
ไม่ใช่ OS sandbox และไม่อนุญาตให้ build หรือแก้ consumer หากไม่ส่งคู่นี้ native
providers จะยัง unavailable และ coverage ไม่ครบ

Python package และ source ZIP ไม่ได้ bundle native helpers การติดตั้ง CLI ไม่
ต้องทำ native setup แต่การใช้ native provider ต้อง setup และส่ง manifest/digest
คู่นี้สำหรับแต่ละคำสั่งที่ใช้ ดู [NATIVE-SETUP.md](NATIVE-SETUP.md) สำหรับ
manifest fields, ขอบเขต trust และรายละเอียดการตรวจสอบ
