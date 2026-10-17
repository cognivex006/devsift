# ใช้ DevSift กับ AI agent

ตัวติดตั้ง CLI ติดตั้ง consumer skill พร้อมคู่มือออฟไลน์ให้ทั้งห้า host ใน user scope
เปิด terminal และ host ใหม่ แล้วตรวจว่า agent เรียก `devsift --help` ได้
Skill ไม่พกกติกาการพัฒนา DevSift หรือข้อกำหนดการทำงานของผู้ดูแลไปบังคับ target project

## ตำแหน่ง skill

| Host | ตำแหน่งที่ installer ใช้ | ตรวจการโหลด |
| --- | --- | --- |
| Codex | `~/.agents/skills/devsift/` | เปิด session ใหม่ แล้วเลือก/เรียก skill `devsift` |
| Claude Code | `~/.claude/skills/devsift/` | เปิด session ใหม่ แล้วเรียก `/devsift` |
| Gemini CLI | `~/.gemini/skills/devsift/` | `gemini skills list --all` |
| Antigravity IDE | `~/.gemini/config/skills/devsift/` | ดู Customizations ใน agent panel |
| Antigravity CLI | `~/.gemini/antigravity-cli/skills/devsift/` | เปิด session ใหม่และตรวจรายการ skills |
| Cursor | `~/.cursor/skills/devsift/` | เปิด chat ใหม่และตรวจรายการ skills |

แต่ละ directory มี `SKILL.md`, `CONSUMER-SCOPE.md` และ `references/` ซึ่งแนบ USAGE
พร้อมคู่มือผู้ใช้และรายละเอียดคำสั่งทั้งหมด Agent จึงอ่าน workflow ได้แม้ไม่เชื่อมต่อ GitHub
ตำแหน่งเหล่านี้อ้างอิง [Codex skills](https://developers.openai.com/codex/skills),
[Claude skills](https://code.claude.com/docs/en/skills), [Gemini skills](https://geminicli.com/docs/cli/skills/),
[Antigravity skills](https://antigravity.google/docs/skills) และ [Cursor skills](https://cursor.com/docs/skills)

## ติดตั้งแบบ plugin หรือ extension

Installer เตรียม bundle ที่ `~/.local/share/devsift/plugin/` ประกอบด้วย `skills/`
และ manifest ของ Codex, Claude Code, Cursor และ Gemini ไม่ลงทะเบียน marketplace โดยอัตโนมัติ
ใช้วิธีของ host ด้านล่างหากต้องการจัดการผ่าน plugin แทน standalone skill
หากใช้ทั้งสองแบบอาจพบ skill ชื่อซ้ำ ให้เลือกวิธีเดียวต่อ host

**Codex:** เพิ่ม local plugin ผ่าน personal marketplace โดยชี้ source ไปยัง bundle
แล้วเปิดใช้งานจาก Plugins ใน client ตาม [คู่มือ package/import ของ Codex](https://developers.openai.com/plugins/build/plugins)
หากมี marketplace เดิมอยู่ให้รวม entry เข้าไฟล์เดิม ดูตัวอย่าง JSON ใน repo ที่
[Codex marketplace](../.agents/plugins/marketplace.json) แล้วเปลี่ยน path ให้ตรงกับ bundle ในเครื่อง

**Claude Code:** ทดสอบ plugin จาก bundle ได้ด้วย:

```sh
claude --plugin-dir /absolute/path/to/.local/share/devsift/plugin
```

ใช้ `/devsift:devsift` เมื่อโหลดแบบ plugin รายละเอียดอยู่ที่
[Claude plugin reference](https://code.claude.com/docs/en/plugins-reference)

**Gemini CLI:** ติดตั้ง extension จาก bundle ที่มี `gemini-extension.json`:

```sh
gemini extensions install /absolute/path/to/.local/share/devsift/plugin
```

Gemini คัดลอก extension ตอนติดตั้ง หลังอัปเดต DevSift ให้ใช้กระบวนการ update ของ Gemini
ด้วย ดู [extension reference](https://geminicli.com/docs/extensions/reference/)

**Antigravity CLI:** รุ่นที่รองรับ skill-bundle plugin ใช้:

```sh
agy plugin install /absolute/path/to/.local/share/devsift/plugin
agy plugin list --json
```

Antigravity IDE ใช้ standalone skill ในตารางด้านบน ดู
[skills และ plugin bundles](https://antigravity.google/docs/skills)

**Cursor:** bundle มี `.cursor-plugin/plugin.json` และ `skills/` สำหรับโหลดผ่าน plugin flow
ของ Cursor ตาม [plugin reference](https://prod.cursor.com/docs/reference/plugins)
Standalone skill ใช้งานได้ทันทีจาก directory ในตาราง ไม่ต้องรอเผยแพร่ marketplace

เปลี่ยน `/absolute/path/to/` เป็น path จริงบนเครื่อง Windows ใช้ path แบบ `C:/Users/...`
ได้ในคำสั่งที่ host รองรับ Bundle เป็นไฟล์พร้อมนำเข้า ความสามารถโหลดจริงขึ้นกับรุ่นและ
การตั้งค่าของ host งานนี้ทดสอบโครงสร้างและ installer แต่ไม่ได้รัน AI clients ทั้งห้าตัว

## ขอให้ AI ทำงาน

> ใช้ DevSift ตรวจ working changes พร้อม security checks แล้วสรุป scope,
> completion, coverage, findings และสิ่งที่ยัง UNKNOWN

> ใช้ DevSift ทบทวน codebase เดิมแบบ legacy recommend โดยยังไม่แก้ไฟล์

> ใช้ scan envelope ที่ฉันระบุ ทบทวน finding นี้และสร้าง implementation proposal

Agent ต้องอ่าน [USAGE](USAGE.md) เลือก workflow และตรวจ help ให้ตรงกับ CLI ที่ติดตั้ง
รักษา exit code และข้อจำกัดตามจริง `report --latest` และ `explain` storage ยัง pending
การใช้ skill ไม่ได้อนุมัติการแก้ source ติดตั้ง dependencies หรือ build target
