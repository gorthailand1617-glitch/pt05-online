$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Pause-Script {
    try {
        [void][Console]::ReadKey($true)
    } catch {
        [void][Console]::Read()
    }
}

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  ระบบดึงข้อมูล ปถ.05 อัตโนมัติ (Auto Run)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# 1. ค้นหา Python Runtime
$PYTHON_CMD = "python"
$USER_PROFILE = $env:USERPROFILE
$CODEX_PYTHON = "$USER_PROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (Test-Path $CODEX_PYTHON) {
    $PYTHON_CMD = $CODEX_PYTHON
    Write-Host "[ระบบ] ตรวจพบ Python จาก Codex Runtime" -ForegroundColor Green
} else {
    $has_python = Get-Command python -ErrorAction SilentlyContinue
    if ($has_python) {
        Write-Host "[ระบบ] ตรวจพบ Python ในระบบหลัก (System Path)" -ForegroundColor Green
    } else {
        Write-Host "[ข้อผิดพลาด] ไม่พบ Python ในเครื่องของคุณ!" -ForegroundColor Red
        Write-Host "กรุณาติดตั้ง Python ก่อนใช้งาน หรือตรวจสอบระบบ" -ForegroundColor Red
        Write-Host ""
        Write-Host "กดปุ่มใดก็ได้เพื่อปิดหน้าต่างนี้..."
        Pause-Script
        exit
    }
}

# 2. ตรวจสอบและติดตั้งไลบรารีที่จำเป็น
Write-Host "[ระบบ] กำลังตรวจสอบความพร้อมของไลบรารี..." -ForegroundColor Yellow
& $PYTHON_CMD -c "import docx, openpyxl" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ระบบ] ไม่พบไลบรารี docx หรือ openpyxl กำลังทำการติดตั้งอัตโนมัติ..." -ForegroundColor Yellow
    & $PYTHON_CMD -m pip install python-docx openpyxl
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ข้อผิดพลาด] ไม่สามารถติดตั้งไลบรารีได้สำเร็จ" -ForegroundColor Red
        Write-Host ""
        Write-Host "กดปุ่มใดก็ได้เพื่อปิดหน้าต่างนี้..."
        Pause-Script
        exit
    }
    Write-Host "[ระบบ] ติดตั้งไลบรารีเรียบร้อยแล้ว" -ForegroundColor Green
} else {
    Write-Host "[ระบบ] ไลบรารีพร้อมใช้งาน" -ForegroundColor Green
}
Write-Host ""

# 3. ตรวจสอบไฟล์เทมเพลต (Template)
$TEMPLATE_FILE = "pt05.docx"
if (-not (Test-Path $TEMPLATE_FILE)) {
    if (Test-Path "บันทึกการตรวจ ปถ.05 (1-2569).docx") {
        $TEMPLATE_FILE = "บันทึกการตรวจ ปถ.05 (1-2569).docx"
    } else {
        Write-Host "[คำแนะนำ] ไม่พบไฟล์เทมเพลต pt05.docx" -ForegroundColor Yellow
        Write-Host "กรุณาแปลงไฟล์ \"บันทึกการตรวจ ปถ.05 (1-2569).doc\" ให้เป็น \".docx\" ก่อน" -ForegroundColor Yellow
        Write-Host "(เปิดไฟล์ใน Word -> บันทึกเป็น (Save As) -> เลือกนามสกุล .docx -> ตั้งชื่อ pt05.docx)" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "หากแปลงไฟล์เสร็จและนำมาวางในโฟลเดอร์นี้แล้ว กดปุ่มใดๆ เพื่อไปต่อ..."
        Pause-Script
        if (-not (Test-Path "pt05.docx")) {
            Write-Host "[ข้อผิดพลาด] ยังไม่พบไฟล์ pt05.docx ระบบจะยกเลิกการทำงาน" -ForegroundColor Red
            Write-Host ""
            Write-Host "กดปุ่มใดก็ได้เพื่อปิดหน้าต่างนี้..."
            Pause-Script
            exit
        }
        $TEMPLATE_FILE = "pt05.docx"
    }
}
Write-Host "[ระบบ] ใช้เทมเพลต: $TEMPLATE_FILE" -ForegroundColor Green

# 4. ตรวจสอบไฟล์รายชื่อครู
$TEACHERS_FILE = "teachers.csv"
if (-not (Test-Path $TEACHERS_FILE)) {
    if (Test-Path "tools\teachers.sample.csv") {
        $TEACHERS_FILE = "tools\teachers.sample.csv"
        Write-Host "[ระบบ] ไม่พบไฟล์ teachers.csv ระบบจะทดสอบรันด้วยบัญชีครูตัวอย่าง (teachers.sample.csv)" -ForegroundColor Yellow
    } else {
        Write-Host "[ข้อผิดพลาด] ไม่พบไฟล์รายชื่อครู (teachers.csv หรือ tools\teachers.sample.csv)" -ForegroundColor Red
        Write-Host ""
        Write-Host "กดปุ่มใดก็ได้เพื่อปิดหน้าต่างนี้..."
        Pause-Script
        exit
    }
}
Write-Host "[ระบบ] ใช้รายชื่อครูจาก: $TEACHERS_FILE" -ForegroundColor Green
Write-Host ""

# 5. สอบถามวันที่ตรวจสอบ
Write-Host "กรุณากรอกวันที่ตรวจสอบ (เช่น 4 กรกฎาคม 2569) หรือกด Enter เพื่อใช้วันที่ปัจจุบัน:" -ForegroundColor Yellow
$CHECK_DATE = Read-Host
Write-Host ""

# 6. เริ่มรันโปรแกรม
Write-Host "[ระบบ] กำลังดึงข้อมูลและบันทึก ปถ.05 กรุณารอสักครู่..." -ForegroundColor Yellow
Write-Host ""

$PARAMS = @("--teachers", "$TEACHERS_FILE", "--template", "$TEMPLATE_FILE", "--out", "output-pt05", "--save-raw")
if ($CHECK_DATE) {
    $PARAMS += @("--date", "$CHECK_DATE")
}

& $PYTHON_CMD tools\pt05_tool.py $PARAMS

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "===================================================" -ForegroundColor Green
    Write-Host "[สำเร็จ] ดึงข้อมูล ปถ.05 และวิเคราะห์เวลาเรียนเรียบร้อยแล้ว!" -ForegroundColor Green
    Write-Host "ตรวจสอบผลลัพธ์ได้ที่โฟลเดอร์: output-pt05" -ForegroundColor Green
    Write-Host "- Excel สรุป ปถ.05: output-pt05\pt05_summary.xlsx" -ForegroundColor Green
    Write-Host "- Excel สังเคราะห์เวลาเรียน (<60% & 80%): output-pt05\student_attendance_risk_summary.xlsx" -ForegroundColor Cyan
    Write-Host "- แดชบอร์ดวิเคราะห์เวลาเรียน: output-pt05\attendance_risk_dashboard.html" -ForegroundColor Cyan
    Write-Host "- Word แยกรายครู: output-pt05\docx\" -ForegroundColor Green
    Write-Host "===================================================" -ForegroundColor Green

    # แปลงไฟล์ Word (.docx) ทั้งหมดในโฟลเดอร์ output-pt05/docx เป็น PDF
    $DOCX_DIR = Join-Path "output-pt05" "docx"
    if (Test-Path $DOCX_DIR) {
        $docxFiles = Get-ChildItem -Path $DOCX_DIR -Filter "*.docx"
        if ($docxFiles.Count -gt 0) {
            Write-Host ""
            Write-Host "[ระบบ] กำลังแปลงไฟล์ Word (.docx) เป็น PDF..." -ForegroundColor Yellow
            try {
                $word = New-Object -ComObject Word.Application
                $word.Visible = $false
                foreach ($file in $docxFiles) {
                    $docxPath = $file.FullName
                    $pdfPath = [System.IO.Path]::ChangeExtension($docxPath, ".pdf")
                    Write-Host "- แปลงไฟล์: $($file.Name) -> $(Split-Path $pdfPath -Leaf)" -ForegroundColor Cyan
                    $doc = $word.Documents.Open($docxPath)
                    $doc.SaveAs($pdfPath, 17) # wdFormatPDF = 17
                    $doc.Close()
                }
                $word.Quit()
                Write-Host "[ระบบ] แปลงไฟล์ Word เป็น PDF สำเร็จแล้ว!" -ForegroundColor Green
                Write-Host "- PDF แยกรายครู: output-pt05\docx\" -ForegroundColor Green
            } catch {
                Write-Host "[ข้อผิดพลาด] ไม่สามารถเรียกใช้งาน MS Word สำหรับแปลง PDF ได้: $_" -ForegroundColor Red
            }
        }
    }
} else {
    Write-Host ""
    Write-Host "[ข้อผิดพลาด] การรันสคริปต์ล้มเหลวหรือรันไม่สมบูรณ์" -ForegroundColor Red
}

Write-Host ""
Write-Host "กดปุ่มใดก็ได้เพื่อปิดหน้าต่างนี้..."
Pause-Script