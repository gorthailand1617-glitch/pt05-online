"""
REST API Service สำหรับระบบเลขาฯ AI ประจำโรงเรียนเปรมติณสูลานนท์
รองรับการเชื่อมต่อกับ ChatGPT Custom GPT (Actions), Gemini Spark และแอปพลิเคชันภายนอก
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = BASE_DIR / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from school_assistant_engine import SchoolAssistantEngine

try:
    from fastapi import FastAPI, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import PlainTextResponse
except ImportError:
    FastAPI = None

app = FastAPI(
    title="School AI Assistant API (ระบบเลขาฯ AI โรงเรียนเปรมติณสูลานนท์)",
    description=(
        "API เชื่อมต่อข้อมูลสารสนเทศโรงเรียนเปรมติณสูลานนท์ (AY-Software) "
        "สำหรับ ChatGPT Custom GPTs, Gemini Extensions และระบบแชทอัตโนมัติ"
    ),
    version="1.0.0",
    servers=[
        {"url": "http://localhost:8000", "description": "Local Development Server"}
    ],
) if FastAPI else None

if app:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

engine = SchoolAssistantEngine()


if app:
    @app.get("/", summary="ตรวจสอบสถานะระบบ")
    def root() -> dict[str, Any]:
        return {
            "status": "online",
            "school": "โรงเรียนเปรมติณสูลานนท์ องค์การบริหารส่วนจังหวัดขอนแก่น",
            "system": "School AI Secretary API",
            "documentation": "/docs",
            "openapi_yaml": "/openapi.yaml",
        }

    @app.get("/api/teacher/schedule", summary="ดึงตารางสอนของครู")
    def teacher_schedule(
        teacher: str = Query("ptn101", description="ชื่อครู หรือ username เช่น 'สถิตย์', 'ptn101'"),
        day: Optional[str] = Query(None, description="วัน เช่น 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์' (ถ้าไม่ระบุใช้วันปัจจุบัน)"),
        period: Optional[str] = Query(None, description="คาบ เช่น 'ชม.1', '1', 'คาบแรก'"),
    ) -> dict[str, Any]:
        """สอบถามตารางสอนของคุณครู เช่น วันนี้คาบแรกสอนวิชาอะไร ม.ไหน"""
        return engine.get_teacher_schedule(teacher_query=teacher, day_name=day, period=period)

    @app.get("/api/attendance/daily", summary="สรุปสถิตินักเรียนมาเรียนทั้งโรงเรียนประจำวัน")
    def daily_attendance(
        date: Optional[str] = Query(None, description="วันที่ เช่น '2026-09-17' หรือ '17/09/2569' (ถ้าไม่ระบุใช้วันปัจจุบัน)"),
    ) -> dict[str, Any]:
        """ดูสถิตินักเรียนมาโรงเรียนกี่คน ขาดกี่คน และสถานะรายห้องทั้งโรงเรียน"""
        return engine.get_daily_attendance_summary(date_str=date)

    @app.get("/api/attendance/assembly-absent", summary="ตรวจสอบรายชื่อนักเรียนที่ขาดแถวหน้าเสาธงรายห้อง")
    def assembly_absent(
        room: str = Query(..., description="ห้องเรียน เช่น 'ม.3/1', 'ม.4/1', '3/1'"),
        date: Optional[str] = Query(None, description="วันที่ เช่น '17/09/2569' (ถ้าไม่ระบุใช้วันล่าสุด)"),
    ) -> dict[str, Any]:
        """ตรวจสอบว่าวันนี้นักเรียนในห้องที่ระบุใครขาดแถว ลา หรือมาสายบ้าง"""
        return engine.get_morning_assembly_absent(room=room, date_str=date)

    @app.get("/api/class/schedule", summary="ดึงตารางเรียนของห้องเรียน")
    def class_schedule(
        room: str = Query(..., description="ห้องเรียน เช่น 'ม.3/1', 'ม.4/1'"),
        day: Optional[str] = Query(None, description="วัน เช่น 'จันทร์', 'อังคาร' (ถ้าไม่ระบุใช้วันปัจจุบัน)"),
    ) -> dict[str, Any]:
        """ตรวจสอบตารางเรียนของนักเรียนแต่ละห้องประจำวัน"""
        return engine.get_class_schedule(room=room, day_name=day)

    @app.get("/api/attendance/risk", summary="สรุปนักเรียนกลุ่มเสี่ยง มส. (เวลาเรียนไม่ถึงเกณฑ์)")
    def attendance_risk() -> dict[str, Any]:
        """ดึงรายชื่อนักเรียนที่มีความเสี่ยง มส. จากเวลาเรียนต่ำกว่า 80% หรือ 60%"""
        return engine.get_attendance_risk_summary()

    @app.get("/openapi.yaml", response_class=PlainTextResponse, summary="ดาวน์โหลด OpenAPI Spec สำหรับ ChatGPT Custom GPTs")
    def get_openapi_yaml() -> str:
        yaml_content = """openapi: 3.1.0
info:
  title: School AI Assistant API (โรงเรียนเปรมติณสูลานนท์)
  description: ระบบเชื่อมต่อข้อมูลสารสนเทศโรงเรียนเปรมติณสูลานนท์ สำหรับ ChatGPT Custom GPTs
  version: 1.0.0
servers:
  - url: http://localhost:8000
    description: Local or Cloudflare Tunnel Server
paths:
  /api/teacher/schedule:
    get:
      operationId: getTeacherSchedule
      summary: ดึงข้อมูลตารางสอนของครู
      description: สอบถามว่าครูสอนวิชาอะไร คาบไหน ห้องไหน ในวันใดวันหนึ่ง
      parameters:
        - name: teacher
          in: query
          required: false
          schema:
            type: string
            default: ptn101
          description: ชื่อครู หรือ username เช่น 'สถิตย์', 'ptn101'
        - name: day
          in: query
          required: false
          schema:
            type: string
          description: วัน เช่น 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์' (ถ้าไม่ใส่จะใช้วันปัจจุบัน)
        - name: period
          in: query
          required: false
          schema:
            type: string
          description: คาบที่ต้องการ เช่น 'ชม.1', '1', 'คาบแรก'
      responses:
        '200':
          description: ข้อมูลตารางสอนสำเร็จ
  /api/attendance/daily:
    get:
      operationId: getDailyAttendanceSummary
      summary: สรุปภาพรวมสถิตินักเรียนมาเรียนทั้งโรงเรียน
      description: ตรวจสอบจำนวนนักเรียนมาเรียน ขาดเรียน ลา มาสาย และสรุปรายห้องของทั้งโรงเรียน
      parameters:
        - name: date
          in: query
          required: false
          schema:
            type: string
          description: วันที่ เช่น '2026-09-17' (ถ้าไม่ระบุใช้วันปัจจุบัน)
      responses:
        '200':
          description: สรุปการมาเรียนสำเร็จ
  /api/attendance/assembly-absent:
    get:
      operationId: getMorningAssemblyAbsent
      summary: ดูรายชื่อนักเรียนที่ขาดแถวหน้าเสาธงรายห้อง
      description: ตรวจสอบว่าในห้องเรียนที่ระบุ มีนักเรียนคนใดขาดแถว ลา หรือมาสาย
      parameters:
        - name: room
          in: query
          required: true
          schema:
            type: string
          description: ห้องเรียน เช่น 'ม.3/1', 'ม.4/1'
        - name: date
          in: query
          required: false
          schema:
            type: string
          description: วันที่ เช่น '17/09/2569'
      responses:
        '200':
          description: รายชื่อนักเรียนที่ไม่มาแถว
  /api/class/schedule:
    get:
      operationId: getClassSchedule
      summary: ดูตารางเรียนของห้องเรียน
      description: ตรวจสอบว่าห้องเรียนนั้นๆ มีเรียนวิชาอะไรในแต่ละคาบ
      parameters:
        - name: room
          in: query
          required: true
          schema:
            type: string
          description: ห้องเรียน เช่น 'ม.3/1'
        - name: day
          in: query
          required: false
          schema:
            type: string
          description: วัน เช่น 'จันทร์'
      responses:
        '200':
          description: ตารางเรียนของห้อง
  /api/attendance/risk:
    get:
      operationId: getAttendanceRiskStudents
      summary: ดูรายชื่อนักเรียนที่เสี่ยง มส.
      description: สรุปนักเรียนที่มีเวลาเรียนต่ำกว่า 80% และ 60%
      responses:
        '200':
          description: รายชื่อนักเรียนกลุ่มเสี่ยง
"""
        return yaml_content


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
