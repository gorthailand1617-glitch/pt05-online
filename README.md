# 📋 ระบบตรวจ ปถ.05 และวิเคราะห์เวลาเรียนออนไลน์ (PT05 Online Auditor)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/gorthailand1617-glitch/pt05-online/blob/main/PT05_Online_Colab.ipynb)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://streamlit.io/cloud)

ระบบอัตโนมัติสำหรับดึงข้อมูลการประเมินผลการเรียนและเช็คเวลาเรียนของครูจากระบบ **SSS (`http://ay-software.in.th/ptn/`)** เพื่อ:
1. **สร้างเอกสารบันทึกการตรวจ ปถ.05 (.docx)** แยกตามรายบุคคลตามแบบฟอร์มมาตรฐาน
2. **สร้างตารางสรุปการประเมินและแผนงานในรูป Excel (.xlsx)** ครบถ้วนทุกมิติ
3. **วิเคราะห์และสังเคราะห์เวลาเรียนนักเรียนกลุ่มเสี่ยง (<60% ขร./มส. และ 60-80% เฝ้าระวัง)** พร้อมแดชบอร์ดสรุปผลแบบ Interactive HTML

---

## 🌟 ฟีเจอร์หลัก (Key Features)

- 🤖 **เลขาฯ AI ประจำโรงเรียน (School AI Secretary)**: แชทสอบถามข้อมูลสดแบบ Real-time เช่น ตารางสอนครู, ขาดแถวหน้าเสาธง, สถิติมาเรียนทั้ง ร.ร., เด็กเสี่ยง มส. ผ่านหน้าเว็บ Streamlit (Gemini API / Fast Engine) หรือเชื่อมต่อ **ChatGPT Custom GPT (Actions)** ในแอปมือถือ
- 🔍 **Web Scraping อัตโนมัติ**: ล็อกอินและดึงข้อมูลผลการเรียน/เวลาเรียนจากระบบ SSS รองรับครูหลายท่านพร้อมกัน
- 📄 **Word Generator (.docx)**: แปลงข้อมูลผลการเรียนลงในแบบฟอร์มบันทึกการตรวจ ปถ.05 พร้อมใส่ค่าช่องสรุปอัตโนมัติ
- 📊 **Excel Reporting (.xlsx)**: สรุปผลการประเมิน แผนการสอน และบันทึกคะแนนรวมในไฟล์เดียว
- ⚠️ **Attendance Risk Analysis**: คัดกรองและจัดกลุ่มนักเรียนที่มีเวลาเรียนต่ำกว่าเกณฑ์ พร้อมออกรายงาน HTML Dashboard สีสันสวยงาม กรองรายวิชาและระดับชั้นได้ทันที
- 🌐 **ใช้งานได้ทุกแพลตฟอร์ม**: รันผ่าน Streamlit Web App, Google Colab, GitHub Actions หรือรันบนเครื่องตนเอง (Local)

---

## 🚀 ช่องทางการใช้งาน (Usage Options)

### วิธีที่ 1: เปิดใช้งานผ่าน Streamlit Cloud (แนะนำ - ฟรี 100% ใช้งานได้ทุกที่)
คุณสามารถนำโปรเจกต์นี้ขึ้น **Streamlit Community Cloud** ได้ฟรี โดยทำตามขั้นตอนดังนี้:
1. นำโค้ดนี้ขึ้น GitHub ในบัญชีของคุณ เช่น `https://github.com/gorthailand1617-glitch/pt05-online`
2. เข้าไปที่เว็บ [share.streamlit.io](https://share.streamlit.io) แล้วล็อกอินด้วยบัญชี GitHub
3. กดปุ่ม **"New app"**
4. เลือก Repository: `gorthailand1617-glitch/pt05-online`
5. Branch: `main` (หรือ `master`)
6. Main file path: `app.py`
7. กด **"Deploy!"**
8. ระบบจะสร้างลิงก์เว็บไซต์ให้คุณ (เช่น `https://pt05-online.streamlit.app`) สามารถเปิดใช้งานผ่านมือถือ แท็บเล็ต หรือคอมพิวเตอร์ได้ตลอด 24 ชั่วโมง

---

### วิธีที่ 2: รันผ่าน Google Colab (รันบนคลาวด์ ไม่ต้องติดตั้งโปรแกรม)
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

### วิธีที่ 4: ใช้งานบนคอมพิวเตอร์ของคุณ (Local Machine)

#### 1. ความต้องการของระบบ (Prerequisites)
- Python 3.9 ขึ้นไป
- ติดตั้งไลบรารีที่จำเป็น:
  ```bash
  pip install -r requirements.txt
  ```

#### 2. วิธีเริ่มใช้งาน
- **แบบหน้าเว็บ (Streamlit Web App)**: 
  - ดับเบิ้ลคลิกไฟล์ `run_web.bat` หรือรันคำสั่ง:
    ```bash
    streamlit run app.py
    ```
- **แบบรันผ่านสคริปต์ (CLI / PowerShell)**:
  - ดับเบิ้ลคลิก `run_pt05.bat` หรือ `analyze_attendance_risk.bat`
  - หรือรันผ่าน PowerShell:
    ```powershell
    .\run_pt05.ps1
    .\analyze_attendance_risk.ps1
    ```

---

## 📝 รูปแบบไฟล์ข้อมูลครู (teachers.csv)

สร้างไฟล์ `teachers.csv` หรือกรอกผ่านหน้าเว็บ โดยมีหัวตารางดังนี้:

```csv
name,username,password
นายสมชาย ใจดี,teacher01,Pass1234!
นางสมศรี รักเรียน,teacher02,Pass5678!
```

---

## 🔒 ความปลอดภัยของข้อมูล (Security & Privacy)

- ไฟล์ `teachers.csv` (รหัสผ่านครูจริง) และโฟลเดอร์ผลลัพธ์ `output-pt05/` ถูกตั้งค่าให้อยู่ใน `.gitignore` โดยอัตโนมัติ
- **ไม่มีการอัปโหลดรหัสผ่านครูขึ้น GitHub สาธารณะ** เพื่อความปลอดภัยของข้อมูลโรงเรียน
- บนหน้าเว็บ Streamlit ข้อมูลบัญชีจะถูกประมวลผลในหน่วยความจำชั่วคราวและล้างข้อมูลออกทันทีเมื่อประมวลผลเสร็จ

---

---

## 🤖 ระบบเลขาฯ AI ประจำโรงเรียน (School AI Secretary)

ระบบผู้ช่วยอัจฉริยะที่เชื่อมต่อข้อมูลสารสนเทศโรงเรียนเปรมติณสูลานนท์ (`http://ay-software.in.th/ptn/`) เพื่อตอบคำถามคุณครูและผู้บริหารแบบ Real-time:

### 💬 ตัวอย่างคำถามที่ถามได้:
1. **"วันนี้คาบแรกฉันสอนวิชาอะไร ม.ไหน"** -> ดึงตารางสอนครูรายวัน/คาบเรียนจาก `table_teaching.php`
2. **"วันนี้ ห้อง ม.3/1 ใครขาดแถว"** -> ดึงรายชื่อนักเรียนที่ขาด ลา มาสาย ในกิจกรรมหน้าเสาธงจาก `re_act.php`
3. **"วันนี้ มีนักเรียนมาโรงเรียนกี่คน"** -> ดึงสรุปสถิตินักเรียนมาเรียนทั้งโรงเรียน (จำนวน, %, ขาด, ลา, สาย, รายห้อง) จาก `re_all_act.php`
4. **"มีนักเรียนคนไหนที่เสี่ยง มส. บ้าง"** -> สรุปนักเรียนที่มีเวลาเรียนต่ำกว่าเกณฑ์ 80% และ 60%
5. **"ตารางเรียนห้อง ม.3/1 วันนี้"** -> ดึงตารางเรียนของห้องจาก `table_class.php`

### 📱 2 ช่องทางการใช้งาน:

#### ช่องทางที่ 1: แชทบนหน้าเว็บ Streamlit (แท็บ '🤖 เลขาฯ AI ประจำโรงเรียน')
- เปิดหน้าเว็บแอป `run_web.bat` แล้วเลือกแท็บ **"🤖 เลขาฯ AI ประจำโรงเรียน"**
- รองรับการเชื่อมต่อกับ **Google Gemini API** (มี Function Calling ดึงข้อมูลจริงอัตโนมัติ)
- มี **โหมดถามตอบด่วน (Fast Engine)**: แม้ยังไม่ได้ใส่ Gemini API Key ก็สามารถคลิกปุ่มคำถามด่วน หรือพิมพ์ถามคำถามทั่วไป ระบบจะเข้าใจและดึงข้อมูลสดมาตอบได้ทันที

#### ช่องทางที่ 2: คุยผ่านแอป ChatGPT บนมือถือ (Custom GPT / Actions)
1. ดับเบิ้ลคลิกไฟล์ `run_api.bat` เพื่อเปิด REST API Service ที่พอร์ต `8000`
2. เปิด Public URL ผ่าน **Cloudflare Tunnel** (ฟรี):
   ```bash
   cloudflared tunnel --url http://localhost:8000
   ```
3. ไปที่ [chatgpt.com](https://chatgpt.com) -> **Explore GPTs** -> **Create a GPT**
4. ไปที่แท็บ **Configure** -> เลื่อนลงมากด **Create new action**
5. นำเนื้อหาในไฟล์ [`openapi.yaml`](file:///d:/--%20SAND%20BOX%20--/ตรวจปถ.05%20ครู/openapi.yaml) ไปวางในช่อง **Schema** แล้วเปลี่ยน URL เป็น Tunnel URL ของคุณ
6. บันทึกแล้วเปิดแอป ChatGPT ในโทรศัพท์มือถือ สามารถพิมพ์คุยหรือกดปุ่มหูฟังเพื่อ **คุยด้วยเสียง (Voice Mode)** ถามข้อมูลโรงเรียนได้ทุกที่ทุกเวลา!

---

## 📁 โครงสร้างโปรเจกต์ (Project Structure)

```text
├── app.py                      # เว็บแอปพลิเคชันหลัก (มี 3 แท็บ: ตรวจ ปถ.05, เลขาฯ AI, คู่มือ API)
├── api.py                      # REST API Service สำหรับเชื่อมต่อ ChatGPT Custom GPT & External
├── openapi.yaml                # OpenAPI 3.1.0 Specification สำหรับ ChatGPT Actions
├── run_api.bat / run_api.ps1   # สคริปต์เปิดรัน REST API Server
├── run_web.bat / run_web.ps1   # สคริปต์เปิดรันหน้าเว็บในเครื่อง
├── run_pt05.bat / run_pt05.ps1 # สคริปต์รันตรวจ ปถ.05 แบบ CLI
├── analyze_attendance_risk.bat # สคริปต์วิเคราะห์เวลาเรียนแบบ CLI
├── requirements.txt            # ไลบรารีที่จำเป็น (streamlit, fastapi, uvicorn, pandas, etc.)
├── pt05.docx                   # เทมเพลตมาตรฐานสำหรับบันทึกการตรวจ ปถ.05
├── PT05_Online_Colab.ipynb     # สมุดงานสำหรับเปิดรันบน Google Colab
├── .github/
│   └── workflows/
│       └── run-pt05.yml        # สคริปต์รันบน GitHub Actions
├── tools/
│   ├── school_assistant_engine.py # เอนจินผู้ช่วยอัจฉริยะ ดึงข้อมูลสดสำหรับ AI
│   ├── pt05_tool.py            # เอนจินหลักดึงข้อมูล ปถ.05 และสร้าง Word/Excel
│   ├── attendance_risk_tool.py # เอนจินวิเคราะห์เวลาเรียนและสร้าง Dashboard
│   └── teachers.sample.csv     # ตัวอย่างโครงสร้างไฟล์รายชื่อครู
└── README.md                   # เอกสารคู่มือโปรเจกต์ฉบับสมบูรณ์
```
