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
Write-Host "  ระบบตรวจ ปถ.05 และวิเคราะห์เวลาเรียน (Web App Mode)" -ForegroundColor Cyan
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
        Write-Host "กรุณาติดตั้ง Python ก่อนใช้งาน" -ForegroundColor Red
        Pause-Script
        exit
    }
}

# 2. ตรวจสอบและติดตั้งไลบรารี
Write-Host "[ระบบ] กำลังตรวจสอบความพร้อมของไลบรารี Web App..." -ForegroundColor Yellow
& $PYTHON_CMD -c "import streamlit, docx, openpyxl, pandas" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ระบบ] กำลังติดตั้งไลบรารีที่จำเป็น (streamlit, pandas, python-docx, openpyxl)..." -ForegroundColor Yellow
    & $PYTHON_CMD -m pip install streamlit pandas python-docx openpyxl
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ข้อผิดพลาด] ติดตั้งไลบรารีไม่สำเร็จ" -ForegroundColor Red
        Pause-Script
        exit
    }
    Write-Host "[ระบบ] ติดตั้งไลบรารีเรียบร้อยแล้ว" -ForegroundColor Green
} else {
    Write-Host "[ระบบ] ไลบรารีพร้อมใช้งาน" -ForegroundColor Green
}

Write-Host ""
Write-Host "[ระบบ] กำลังเปิดเว็บแอปพลิเคชัน..." -ForegroundColor Cyan
Write-Host "หากเบราว์เซอร์ไม่เปิดอัตโนมัติ ให้เข้าไปที่: http://localhost:8501" -ForegroundColor Yellow
Write-Host ""

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$APP_PATH = Join-Path $SCRIPT_DIR "app.py"

& $PYTHON_CMD -m streamlit run $APP_PATH
