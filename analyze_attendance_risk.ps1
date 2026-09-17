#!/usr/bin/env pwsh
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
Write-Host "  ระบบ AI สังเคราะห์นักเรียนเวลาเรียนไม่ถึง 60% และ 80%" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$PYTHON_CMD = "python"
$CODEX_PYTHON = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $CODEX_PYTHON) {
    $PYTHON_CMD = $CODEX_PYTHON
}

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$TOOL_PATH = Join-Path $SCRIPT_DIR "tools\attendance_risk_tool.py"
$RAW_DIR = Join-Path $SCRIPT_DIR "output-pt05\raw"
$SUMMARY_PATH = Join-Path $SCRIPT_DIR "output-pt05\pt05_summary.json"
$OUT_DIR = Join-Path $SCRIPT_DIR "output-pt05"

if (-not (Test-Path $RAW_DIR)) {
    Write-Host "[ข้อผิดพลาด] ไม่พบโฟลเดอร์ $RAW_DIR" -ForegroundColor Red
    Write-Host "กรุณารันโปรแกรมดึงข้อมูล ปถ.05 (run_pt05.bat) ก่อนใช้งาน" -ForegroundColor Yellow
    Write-Host ""
    Pause-Script
    exit
}

& $PYTHON_CMD $TOOL_PATH --raw-dir $RAW_DIR --summary $SUMMARY_PATH --out-dir $OUT_DIR

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "===================================================" -ForegroundColor Green
    Write-Host "[สำเร็จ] สร้างรายงานสังเคราะห์เวลาเรียนเรียบร้อยแล้ว!" -ForegroundColor Green
    Write-Host "- Excel สรุป: output-pt05\student_attendance_risk_summary.xlsx" -ForegroundColor Cyan
    Write-Host "- แดชบอร์ด HTML: output-pt05\attendance_risk_dashboard.html" -ForegroundColor Cyan
    Write-Host "===================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[ข้อผิดพลาด] การประมวลผลล้มเหลว" -ForegroundColor Red
}

Write-Host ""
Write-Host "กดปุ่มใดก็ได้เพื่อปิดหน้าต่างนี้..."
Pause-Script
