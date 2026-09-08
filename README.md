# 📋 ระบบตรวจ ปถ.05 และวิเคราะห์เวลาเรียนออนไลน์ (PT05 Online Auditor)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/gorthailand1617-glitch/pt05-online/blob/main/PT05_Online_Colab.ipynb)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://streamlit.io/cloud)

ระบบอัตโนมัติสำหรับดึงข้อมูลการประเมินผลการเรียนและเช็คเวลาเรียนของครูจากระบบ **SSS (`http://ay-software.in.th/ptn/`)** เพื่อ:
1. **สร้างเอกสารบันทึกการตรวจ ปถ.05 (.docx)** แยกตามรายบุคคล
2. **สร้างตารางสรุปการประเมินและแผนงานในรูป Excel (.xlsx)**
3. **วิเคราะห์และสังเคราะห์ AI เวลาเรียนนักเรียนกลุ่มเสี่ยง (<60% ขร./มส. และ 60-80% เฝ้าระวัง)** พร้อมแดชบอร์ดสรุปผลแบบ Interactive HTML

---

## 🌟 ช่องทางการใช้งานออนไลน์ (เลือกวิธีที่สะดวกได้เลย)

### วิธีที่ 1: เปิดใช้งานผ่าน Streamlit Cloud (แนะนำ - ฟรี 100% ใช้งานได้ทุกที่ผ่านมือถือ/คอม)
คุณสามารถนำโปรเจกต์นี้ขึ้น **Streamlit Community Cloud** ได้ฟรี โดยทำตามขั้นตอนสั้นๆ ดังนี้:
1. นำโค้ดนี้ขึ้น GitHub ในบัญชีของคุณ เช่น `https://github.com/gorthailand1617-glitch/pt05-online`
2. เข้าไปที่เว็บ [share.streamlit.io](https://share.streamlit.io) แล้วล็อกอินด้วยบัญชี GitHub
3. กดปุ่ม **"New app"**
4. เลือก Repository: `gorthailand1617-glitch/pt05-online`
5. Branch: `main` (หรือ `master`)
6. Main file path: `app.py`
7. กด **"Deploy!"**
8. ระบบจะสร้างลิงก์เว็บไซต์ให้คุณ (เช่น `https://pt05-online.streamlit.app`) ซึ่งสามารถเปิดใช้งานจากมือถือ แท็บเล็ต หรือคอมพิวเตอร์ที่ใดก็ได้ในโลกตลอด 24 ชั่วโมง!

---

### วิธีที่ 2: รันผ่าน Google Colab (รันบนคลาวด์ ไม่ต้องมีเซิร์ฟเวอร์)
1. กดที่ปุ่ม **[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/gorthailand1617-glitch/pt05-online/blob/main/PT05_Online_Colab.ipynb)**
2. รันเซลล์ตามลำดับ
3. อัปโหลดหรือพิมพ์ข้อมูลบัญชีครู
4. ดาวน์โหลดไฟล์ผลลัพธ์ `PT05_Results.zip` ได้ทันที

---

### วิธีที่ 3: สั่งรันบน GitHub Actions
1. เข้าไปที่แท็บ **Actions** ในหน้า Repository บน GitHub
2. เลือก Workflow **"Run PT05 Extraction & Attendance Risk Analysis"**
3. กดปุ่ม **"Run workflow"** (สามารถเลือกภาคเรียนและปีการศึกษาได้)
4. เมื่อรันเสร็จ สามารถกดดาวน์โหลดไฟล์ผลลัพธ์ได้จากส่วน **Artifacts**

---

### วิธีที่ 4: ใช้งานบนคอมพิวเตอร์ของคุณ (Local Web App / Batch)
- **แบบหน้าเว็บ (Web App)**: ดับเบิ้ลคลิกไฟล์ `run_web.bat` ระบบจะเปิดหน้าเว็บในบราวเซอร์ให้อัตโนมัติ
- **แบบเดิม (CLI Batch)**: ดับเบิ้ลคลิกไฟล์ `run_pt05.bat` หรือ `analyze_attendance_risk.bat`

---

## 🔒 ความปลอดภัยของข้อมูล (Security & Privacy)

- ไฟล์ `teachers.csv` (รหัสผ่านครูจริง) และโฟลเดอร์ผลลัพธ์ `output-pt05/` จะถูกตั้งค่าให้อยู่ใน `.gitignore` โดยอัตโนมัติ
- **จะไม่มีการอัปโหลดรหัสผ่านครูจริงขึ้น GitHub สาธารณะ** เพื่อความปลอดภัยของข้อมูลโรงเรียน
- บนหน้าเว็บ Streamlit คุณสามารถพิมพ์หรืออัปโหลดไฟล์ `teachers.csv` ได้แบบสดๆ ระบบจะประมวลผลในหน่วยความจำชั่วคราวและลบออกทันทีเมื่อประมวลผลเสร็จ

---

## 📁 โครงสร้างโปรเจกต์

```text
├── app.py                      # เว็บแอปพลิเคชันหลัก (Streamlit Web App)
├── requirements.txt            # ไลบรารีที่จำเป็นสำหรับระบบ
├── .streamlit/
│   └── config.toml             # ตั้งค่าสไตล์และขนาดอัปโหลดของ Streamlit
├── pt05.docx                   # เทมเพลตมาตรฐานสำหรับบันทึกการตรวจ ปถ.05
├── PT05_Online_Colab.ipynb     # สมุดงานสำหรับเปิดรันบน Google Colab
├── .github/
│   └── workflows/
│       └── run-pt05.yml        # สคริปต์รันบน GitHub Actions
├── run_web.bat / run_web.ps1   # สคริปต์เปิดรันหน้าเว็บในเครื่อง
├── run_pt05.bat / run_pt05.ps1 # สคริปต์รันแบบ CLI เดิม
├── tools/
│   ├── pt05_tool.py            # เอนจินหลักดึงข้อมูล ปถ.05 และสร้าง Word/Excel
│   ├── attendance_risk_tool.py # เอนจินวิเคราะห์เวลาเรียนและสร้าง Dashboard
│   └── teachers.sample.csv     # ตัวอย่างโครงสร้างไฟล์รายชื่อครู
└── .gitignore                  # กฎการป้องกันข้อมูลลับขึ้น GitHub
```
