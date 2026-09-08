# เครื่องมือดึงข้อมูล ปถ.05 จากเว็บ SSS

เครื่องมือนี้ล็อกอินเว็บ `http://ay-software.in.th/ptn/` ทีละครู ดึงข้อมูลรายวิชา แล้วสร้างไฟล์:

- Excel สรุปข้อมูลทั้งหมด
- Word `.docx` บันทึกการตรวจ ปถ.05 แยกตามครู

## เตรียมไฟล์รายชื่อครู

สร้างไฟล์ CSV เช่น `teachers.csv`

```csv
username,password
ptn101,101
ptn102,102
```

## วิธีรัน

ใช้ Python runtime ที่มาพร้อม Codex:

```powershell
C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\pt05_tool.py --teachers teachers.csv --template pt05.docx --out output-pt05
```

ถ้าต้องการลองครูคนเดียว:

```powershell
C:\Users\USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe tools\pt05_tool.py --teachers tools\teachers.sample.csv --template pt05.docx --out output-pt05
```

## ไฟล์ผลลัพธ์

- `output-pt05/pt05_summary.xlsx` รวมข้อมูลทุกครู
- `output-pt05/docx/*.docx` ไฟล์ ปถ.05 แยกตามครู
- `output-pt05/raw/*.html` HTML ที่ดึงมาไว้ตรวจสอบย้อนหลัง ถ้าใส่ `--save-raw`

## แหล่งข้อมูลที่ดึง

- `re_list_teaching.php`: รายวิชา ระดับชั้น ห้อง รหัสวิชา
- `sco_confix2.php`: คำอธิบายรายวิชา และตัวชี้วัด/ผลการเรียนรู้
- `sco_confix.php`: คะแนนก่อนกลางภาค กลางภาค หลังกลางภาค ปลายภาค
- `re_teaching.php`: จำนวนคาบ/ครั้งที่เช็คเวลาเรียน
- `del_test.php`: แบบฝึกหัด/รายการคะแนนที่สร้างไว้

หมายเหตุ: template ต้องเป็น `.docx` ถ้ามีแต่ `.doc` ให้เปิดใน Word แล้ว Save As เป็น `.docx` ก่อน หรือใช้ไฟล์ `pt05.docx` ที่แปลงไว้ใน workspace นี้
