# ใช้ DevSift กับ AI agent

ติดตั้ง CLI ตาม [คู่มือติดตั้ง](INSTALL.md) แล้วเลือก standalone skill หรือ plugin
เพียงวิธีเดียวต่อ host เพื่อลด skill ชื่อซ้ำ Plugin มีคู่มือออฟไลน์ แต่ไม่ได้ติดตั้ง
CLI, native toolchains หรือเปลี่ยนโปรเจกต์เป้าหมายให้เอง

Catalog ใน repository รองรับ marketplace จาก Git ไม่ต้องสร้าง local bundle
ส่วนสองบรรทัดและ Copilot ในตัวติดตั้งอยู่ใน Unreleased สำหรับรุ่นถัดไป
release assets ปัจจุบันยังเป็น 0.1.12 คำสั่งด้านล่างใช้ source บน main หลังรวมการเปลี่ยนแปลง
ไม่ได้หมายความว่า DevSift ผ่านการขึ้น official directory แล้ว

## Marketplace / repository installation

ตรวจ help ของ host ก่อนใช้ Client รุ่นเก่าอาจยังไม่มี plugin commands
ไม่ได้รับรองว่าทุกเวอร์ชันของทุก host รองรับรูปแบบเดียวกัน
อ้างอิงเอกสารทางการที่ตรวจวันที่ 2026-10-18:

| Host | ช่องทางจาก repository | สถานะ directory สาธารณะ |
| --- | --- | --- |
| Codex | เพิ่ม marketplace แล้วติดตั้งด้วย plugin add หรือ Plugins UI | ยังไม่ได้ส่งขึ้น universal directory |
| Claude Code | เพิ่ม marketplace แล้ว install plugin | catalog ของโครงการ |
| Copilot CLI | เพิ่ม marketplace แล้ว install plugin | ยังไม่ได้ขึ้น awesome-copilot |
| Cursor CLI | เพิ่ม Git marketplace แล้วเลือกใน /plugin | ยังไม่ได้ส่งตรวจ Cursor Marketplace |
| Gemini CLI | extension จาก GitHub URL | ยังไม่ได้ส่งเข้า gallery |
| Antigravity CLI | plugin จาก GitHub URL | ยังไม่มี DevSift ใน official marketplace; ไม่รองรับ custom marketplace name |
| Antigravity IDE | standalone skill หรือ import ตามรุ่น IDE | CLI plugin ไม่ได้ทำให้ IDE โหลดอัตโนมัติ |

### Codex

    codex plugin marketplace add orchex006/devsift
    codex plugin marketplace list
    codex plugin add devsift@devsift

ถ้าไม่มี plugin add ให้เปิด Plugins เลือก marketplace devsift แล้วติดตั้ง
ดู [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)
คำสั่ง plugin add ตรวจจาก help ของ client ในเครื่องด้วย Catalog อยู่ที่
[.agents/plugins/marketplace.json](https://github.com/orchex006/devsift/blob/main/.agents/plugins/marketplace.json)

### Claude Code

    claude plugin marketplace add orchex006/devsift
    claude plugin install devsift@devsift
    claude plugin list

ใน session ใช้ /devsift:devsift แล้วให้ agent ตรวจ devsift --help
อัปเดตด้วย claude plugin marketplace update devsift แล้ว claude plugin update devsift@devsift
ดู [Claude marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
และ [catalog](https://github.com/orchex006/devsift/blob/main/.claude-plugin/marketplace.json)

### GitHub Copilot CLI

    copilot plugin marketplace add orchex006/devsift
    copilot plugin marketplace browse devsift
    copilot plugin install devsift@devsift
    copilot plugin list

อัปเดต catalog ด้วย copilot plugin marketplace update devsift แล้วตรวจ
copilot plugin update --help สำหรับรุ่นของ client
ดู [Copilot plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)
และ [catalog](https://github.com/orchex006/devsift/blob/main/.github/plugin/marketplace.json)
Root [plugin.json](https://github.com/orchex006/devsift/blob/main/plugin.json) ใช้ Agent Plugins format และค้น skill ใน skills/
Copilot ใน VS Code/IDE อื่นให้ตรวจการรองรับ Agent Plugins แยกตามรุ่น
นี่ไม่ใช่ VSIX extension หรือ GitHub App

### Cursor

    agent plugin marketplace add https://github.com/orchex006/devsift.git
    agent plugin marketplace list

จาก Cursor CLI เปิด /plugin เลือก marketplace devsift แล้วติดตั้ง
รุ่นที่รองรับใช้ /plugin marketplace add https://github.com/orchex006/devsift.git ได้ด้วย
ดู [Cursor CLI changelog](https://cursor.com/docs/cli/changelog),
[plugin reference](https://prod.cursor.com/docs/reference/plugins) และ
[catalog](https://github.com/orchex006/devsift/blob/main/.cursor-plugin/marketplace.json)
IDE ใช้ team marketplace เมื่อ plan/สิทธิ์รองรับ หรือ standalone skill ด้านล่าง
Public Cursor Marketplace ต้องส่ง repository ให้ Cursor ตรวจแยกต่างหาก

### Gemini CLI

    gemini extensions install https://github.com/orchex006/devsift
    gemini extensions list
    gemini extensions update devsift

ดู [Gemini extensions](https://geminicli.com/docs/extensions/)
นี่คือ remote repository installation; การแสดงใน gallery เป็นอีกขั้นตอน

### Antigravity CLI

    agy plugin install https://github.com/orchex006/devsift
    agy plugin list --json

ดู [Antigravity plugins](https://www.antigravity.google/docs/plugins?tab=cli)
และ [marketplace limitations](https://antigravity.google/docs/marketplace?tab=cli)
อย่าใช้ devsift@antigravity-plugins-official เพราะยังไม่มี listing
ไม่สร้างคำสั่งเพิ่ม custom marketplace ที่เอกสารปัจจุบันยังไม่รองรับ

## Standalone skill และ local import

Source installer รองรับ user scope ต่อไปนี้; ตัวเลือก --hosts copilot อยู่ใน Unreleased
ถ้าใช้ marketplace แล้วไม่ต้องติดตั้ง standalone ซ้ำใน host เดียวกัน

| Host | ตำแหน่งที่ installer ใช้ |
| --- | --- |
| Codex | ~/.agents/skills/devsift/ |
| Claude Code | ~/.claude/skills/devsift/ |
| Gemini CLI | ~/.gemini/skills/devsift/ |
| Antigravity IDE | ~/.gemini/config/skills/devsift/ |
| Antigravity CLI | ~/.gemini/antigravity-cli/skills/devsift/ |
| Cursor | ~/.cursor/skills/devsift/ |
| Copilot | ~/.agents/skills/devsift/ (ใช้ร่วมกับ Codex โดยไม่สร้างสำเนาซ้ำ) |

เปิด session ใหม่หลังติดตั้ง Skill มี SKILL.md, CONSUMER-SCOPE.md และ references/
พร้อม USAGE และคู่มือคำสั่ง ไม่พกกฎพัฒนา DevSift ไปบังคับ target
ดู [Copilot skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)

สำหรับ offline/local testing ยังใช้ bundle ที่ ~/.local/share/devsift/plugin/ ได้:

    claude --plugin-dir /absolute/path/to/.local/share/devsift/plugin
    gemini extensions install /absolute/path/to/.local/share/devsift/plugin
    agy plugin install /absolute/path/to/.local/share/devsift/plugin

แทน path ด้วยตำแหน่งจริง Windows ใช้ C:/Users/... เมื่อ host รองรับ
Installer ไม่เพิ่ม marketplace หรือเรียก host CLI ให้อัตโนมัติ การติดตั้งผ่าน host
ใช้ระบบดาวน์โหลดของ host นั้น และอัปเดตแยกจาก DevSift CLI

## ตรวจผลและถอนการติดตั้ง

ตรวจ plugin/skills ใน host แล้วเริ่ม session ใหม่ ให้ agent อ่าน USAGE
และเรียก devsift --help / devsift doctor จาก trusted CLI บน PATH
หาก CLI หาย ให้ติดตั้งแยก ห้ามนำเข้า code จาก target เพื่อทดแทน

การตรวจ JSON/manifests และ help ไม่ได้พิสูจน์การโหลดจริงของทุก AI client
ดูผลจริงใน PR/หลักฐานทดสอบ ไม่อ้างว่า public listing ผ่านแล้ว
ถอน plugin ด้วยคำสั่ง/เมนูของ host ก่อนลบ marketplace
อย่าลบ standalone skill ที่ปรับแต่งเองหรือแก้ config ของ host อื่น

## ขอให้ AI ทำงาน

> ใช้ DevSift ตรวจ working changes พร้อม security checks แล้วสรุป scope,
> completion, coverage, findings และสิ่งที่ยัง UNKNOWN

> ใช้ DevSift ทบทวน codebase เดิมแบบ legacy recommend โดยยังไม่แก้ไฟล์

Agent อ่าน [USAGE](USAGE.md) เลือก workflow และตรวจ subcommand help
การใช้ skill ไม่ได้อนุมัติการแก้ source ติดตั้ง dependencies หรือ build target
