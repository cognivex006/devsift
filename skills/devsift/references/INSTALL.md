# ติดตั้ง DevSift

ต้องมี Python 3.12 ขึ้นไปและ Git สำหรับตรวจ repository ตัวติดตั้งติดตั้ง CLI ใน
private virtual environment พร้อม skill สำหรับ Codex, Claude Code, Gemini CLI,
Antigravity และ Cursor โดยไม่ต้องเปิดสิทธิ์ administrator

## ติดตั้งจาก release

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://github.com/orchex006/devsift/releases/latest/download/install.ps1 | iex"
```

macOS / Linux:

```sh
curl --progress-bar -fL https://github.com/orchex006/devsift/releases/latest/download/install.sh | sh
```

ตัวติดตั้งดาวน์โหลด `devsift-install.zip` และตรวจ SHA256 จาก release เดียวกันก่อนติดตั้ง
checksum ตรวจความเสียหายของไฟล์ ไม่ใช่ลายเซ็นรับรองผู้เผยแพร่
ต้องเชื่อถือ repository และ release ที่เลือกติดตั้ง

ตัวติดตั้งรุ่น 0.1.13 ใช้พื้นที่สองบรรทัดเดิม: bar พร้อมเปอร์เซ็นต์ด้านบน
และ spinner/ขั้นตอนปัจจุบันด้านล่าง:
ตรวจ Python → ดาวน์โหลด → ตรวจ checksum → แตก bundle → เตรียม environment →
ติดตั้ง CLI/skills → ตั้งค่า PATH ดาวน์โหลดแสดงเปอร์เซ็นต์จาก bytes จริง ส่วน
ขั้นตอนในเครื่องแสดงความคืบหน้ารวมและเวลาที่ผ่านไป เมื่อไม่ทราบขนาดดาวน์โหลด
จะแสดง `size unknown` พร้อมจำนวน bytes แทนการเดาเปอร์เซ็นต์

หน้าจอปกติไม่แสดง pip/build logs หลังเสร็จสรุปเฉพาะเวอร์ชัน ตำแหน่ง CLI,
hosts ที่ติดตั้ง และคำสั่งถัดไป หากล้มเหลวจะบอกขั้นตอนและสาเหตุ ไม่แสดงสถานะ Ready

Installer assets เผยแพร่พร้อม [v0.1.13](https://github.com/orchex006/devsift/releases/tag/v0.1.13)
หากดาวน์โหลดไม่ได้ให้ตรวจ network หรือใช้ source installation ด้านล่าง

เปิด terminal ใหม่ แล้วตรวจจาก Git root ของ target:

```sh
devsift --help
devsift doctor
devsift scan --changed
```

Windows เพิ่ม `%USERPROFILE%\.local\bin` เข้า user PATH ส่วน macOS/Linux เพิ่ม
`$HOME/.local/bin` ผ่าน `.profile`, `.bashrc` และ `.zshrc` หรือรัน `export PATH="$HOME/.local/bin:$PATH"` ใน session นั้น
Agent host ที่เปิดอยู่แล้วต้อง restart เพื่อรับ PATH และ skill ใหม่

## อัปเดต

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://github.com/orchex006/devsift/releases/latest/download/update.ps1 | iex"
```

```sh
curl --progress-bar -fL https://github.com/orchex006/devsift/releases/latest/download/update.sh | sh
```

อัปเดต CLI และคู่มือ skill พร้อมกัน ใช้ environment ใหม่และตรวจ help ก่อนเปลี่ยน launcher
เก็บ environment เดิมไว้ใน `~/.local/share/devsift/versions/`
หาก pip หรือตรวจ CLI ไม่สำเร็จ launcher เดิมยังใช้งานได้
Skill directory ที่ไม่ได้ติดตั้งโดย DevSift จะไม่ถูกเขียนทับ ให้ย้าย directory นั้นไว้ก่อน

## ติดตั้งจาก source

เลือก checkout ที่เชื่อถือได้:

```sh
git clone https://github.com/orchex006/devsift.git
cd devsift
python -m pip install setuptools==83.0.0 wheel
python tools/build_installer.py --output dist/installer
```

คำสั่งนี้เตรียม bundle ของ CLI, skill และ plugin metadata จาก checkout ปัจจุบัน
แล้วแตก `dist/installer/devsift-install.zip` ไปยัง directory ชั่วคราว

PowerShell:

```powershell
Expand-Archive dist/installer/devsift-install.zip -DestinationPath dist/installer/local
python -I -B dist/installer/local/install.py
$env:Path = "$HOME\.local\bin;$env:Path"
devsift --help
```

macOS / Linux:

```sh
python3 -m zipfile -e dist/installer/devsift-install.zip dist/installer/local
python3 -I -B dist/installer/local/install.py
export PATH="$HOME/.local/bin:$PATH"
devsift --help
```

เพิ่ม `~/.local/bin` เข้า PATH ถาวรใน shell หรือ user environment ของคุณสำหรับ source installation
ใช้ `--hosts codex claude` เป็นต้น หากต้องการเฉพาะบาง host; ค่าเริ่มต้นติดตั้งครบทั้งหก host (รวม Copilot โดยใช้ skill ร่วมกับ Codex)
ใช้ `--home <directory>` และ `--bin-dir <directory>` เมื่อต้องการ destination แยก
ติดตั้งเฉพาะ CLI ลง environment ที่จัดการเองได้ด้วย `python -m pip install .`
จากนั้น activate environment ก่อนเรียก `devsift`

## สิ่งที่ติดตั้ง

| ตำแหน่ง | เนื้อหา |
| --- | --- |
| `~/.local/bin/devsift` หรือ `devsift.cmd` | launcher ของ CLI |
| `~/.local/share/devsift/versions/` | Python environments |
| `~/.local/share/devsift/installation.json` | path และ host ที่ติดตั้งล่าสุด |
| `~/.local/share/devsift/plugin/` | plugin bundle สำหรับ import ตามวิธีของ host |
| skill paths ของ host | skill พร้อมคู่มือออฟไลน์ ดู [integrations](AGENT-INTEGRATIONS.md) |

การคัดลอก skill ไม่ได้ลงทะเบียน plugin marketplace ให้ host
Python wheel และ installer ไม่ bundle native binaries ให้ตั้งค่าตาม
[Native setup](NATIVE-SETUP.md) เมื่อต้องการ coverage ของภาษาเหล่านั้น

## ถอนการติดตั้ง

อ่าน `~/.local/share/devsift/installation.json` เพื่อดูไฟล์ที่ installer เป็นเจ้าของ
ลบ launcher, skill directory ที่มี `.devsift-managed` และ `~/.local/share/devsift`
พร้อมนำ PATH entry หรือบล็อก `# DevSift CLI` ออกจาก shell profile ตามที่ติดตั้ง
