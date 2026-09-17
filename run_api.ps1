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
Write-Host "  ระบบ REST API เลขาฯ AI โรงเรียน (สำหรับ ChatGPT / External)" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

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
        Pause-Script
        exit
    }
}

Write-Host "[ระบบ] กำลังตรวจสอบความพร้อมของไลบรารี..." -ForegroundColor Yellow
& $PYTHON_CMD -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ระบบ] กำลังติดตั้ง fastapi, uvicorn..." -ForegroundColor Yellow
    & $PYTHON_CMD -m pip install fastapi uvicorn
}

Write-Host ""
Write-Host "🚀 กำลังเปิดบริการ REST API ที่พอร์ต 8000..." -ForegroundColor Green
Write-Host "📌 Swagger API Documentation : http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "📌 OpenAPI Spec (สำหรับ ChatGPT): http://localhost:8000/openapi.yaml" -ForegroundColor Cyan
Write-Host ""
Write-Host "กด Ctrl+C เพื่อหยุดการทำงาน" -ForegroundColor Gray
Write-Host ""

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
& $PYTHON_CMD -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload --app-dir "$SCRIPT_DIR"
