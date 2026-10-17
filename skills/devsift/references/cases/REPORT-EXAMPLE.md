# ตัวอย่างรายงาน DevSift

นี่เป็นตัวอย่างจำลองเพื่อแสดงวิธีใช้ [Report template](../REPORT-TEMPLATE.md)
ไม่ใช่ผลสแกน repository จริง ตัวอย่างเลือกกรณีไม่มี findings แต่ตรวจไม่ครบ
เพื่อแสดงว่าต้องรายงานข้อจำกัดก่อนสรุปผล

---

# DevSift report

| รายการ | ค่าในตัวอย่างจำลอง |
| --- | --- |
| Repository / selected root | demo-project |
| Scope / base ref | changed / not supplied |
| Status / complete / exit code | incomplete / false / 2 |
| Providers / coverage | ตัวตรวจภาษาที่จำเป็นยังไม่พร้อม จึงยังยืนยัน coverage ไม่ได้ |
| Enforced findings / security review | 0 / ต้องอ่าน flags จากผลจริงก่อนสรุป |

## Summary

ยังสรุปว่าโปรเจกต์ผ่านไม่ได้ เพราะการวิเคราะห์ไม่ครบ แม้ผลที่ส่งคืนไม่มี case
ต้องตั้งค่า provider ที่ขาดแล้วตรวจซ้ำตาม scope ที่ผู้ใช้เลือก

## Execution errors

ตัวอย่างนี้ไม่ได้ระบุ error code จริง ในการใช้งานให้คัดลอก code และคำอธิบายจาก
JSON envelope รวมถึง diagnostic action ที่แนะนำ อย่าสร้าง error code ขึ้นเอง

## Contextual recommendations

ยังไม่มี consumer/test evidence หรือ measured business impact ที่ตรวจยืนยัน
คงค่า UNKNOWN ไว้ และยังไม่มี AFTER proposal หรือสิทธิ์แก้ source จากรายงานนี้

---

สำหรับตัวอย่างที่รัน scan จริงและมี case, source proof และ redaction ให้ดู
[Report walkthrough](REPORT-WALKTHROUGH.md) เมื่อมี case ให้ใช้ full case section
ใน template สำหรับทุก finding แทนการย่อเหลือเพียงตารางสรุป
