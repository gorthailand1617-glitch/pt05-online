"""
โมดูลเอนจินผู้ช่วยอัจฉริยะประจำโรงเรียน (School AI Assistant Engine)
ทำหน้าที่ดึงและประมวลผลข้อมูลจากระบบ SSS โรงเรียนเปรมติณสูลานนท์
สำหรับรองรับการเรียกใช้งานของ AI Agents (Gemini Function Calling, ChatGPT Custom GPT Actions)
"""

from __future__ import annotations

import csv
import datetime
import html
import json
import os
import re
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from pt05_tool import SssClient, parse_forms

BASE_DIR = Path(__file__).resolve().parent.parent
TEACHERS_CSV = BASE_DIR / "teachers.csv"
SAMPLE_TEACHERS_CSV = BASE_DIR / "tools" / "teachers.sample.csv"

THAI_DAYS = {
    0: "จันทร์",
    1: "อังคาร",
    2: "พุธ",
    3: "พฤหัสบดี",
    4: "ศุกร์",
    5: "เสาร์",
    6: "อาทิตย์",
}

STATUS_MAP = {
    "/": "มา",
    "ข": "ขาด",
    "ล": "ลา",
    "ส": "สาย",
    "-": "ไม่ได้บันทึก",
}


def clean_html_text(raw_html: str) -> str:
    cleaned = re.sub(r"<style[\s\S]*?</style>", "", raw_html, flags=re.I)
    cleaned = re.sub(r"<script[\s\S]*?</script>", "", cleaned, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def get_current_thai_date() -> tuple[str, str, str]:
    """คืนค่า (YYYY-MM-DD, DD/MM/YYYY_THAI, ชื่อวันภาษาไทย)"""
    now = datetime.datetime.now()
    # ปี พ.ศ.
    buddhist_year = now.year + 543
    date_iso = now.strftime("%Y-%m-%d")
    date_thai = f"{now.day:02d}/{now.month:02d}/{buddhist_year}"
    day_name = THAI_DAYS.get(now.weekday(), "จันทร์")
    return date_iso, date_thai, day_name


class SchoolAssistantEngine:
    def __init__(self) -> None:
        self.client = SssClient()
        self.teachers_cache: list[dict[str, str]] = []
        self.logged_in_sessions: dict[str, dict[str, str]] = {}
        self._load_teacher_accounts()

    def _load_teacher_accounts(self) -> None:
        file_to_load = TEACHERS_CSV if TEACHERS_CSV.exists() else SAMPLE_TEACHERS_CSV
        if not file_to_load.exists():
            return
        try:
            with file_to_load.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    username = r.get("username", "").strip()
                    password = r.get("password", "").strip()
                    name = r.get("name", "").strip()
                    if username and password:
                        self.teachers_cache.append({
                            "username": username,
                            "password": password,
                            "name": name,
                        })
        except Exception:
            pass

    def get_teacher_info(self, teacher_query: str) -> tuple[dict[str, str], dict[str, str]]:
        """ค้นหาและล็อกอินครูจาก username หรือชื่อครู"""
        target = None
        q = teacher_query.strip().lower()

        # 1. ลองหาจาก cache
        for t in self.teachers_cache:
            if q == t["username"].lower() or (t["name"] and q in t["name"].lower()):
                target = t
                break

        # ถ้าไม่เจอ ลองหา match บางส่วน
        if not target and self.teachers_cache:
            for t in self.teachers_cache:
                if q in t["username"].lower():
                    target = t
                    break

        if not target:
            # Fallback ใช้บัญชีแรกในระบบ
            if self.teachers_cache:
                target = self.teachers_cache[0]
            else:
                target = {"username": "ptn101", "password": "101", "name": "นายสถิตย์ ศรีวัชรกุล"}

        # ล็อกอิน
        user = target["username"]
        if user in self.logged_in_sessions:
            info = self.logged_in_sessions[user]
        else:
            info = self.client.login(target["username"], target["password"])
            self.logged_in_sessions[user] = info

        return target, info

    def get_default_teacher_info(self) -> tuple[dict[str, str], dict[str, str]]:
        """ดึงบัญชีครูหลักสำหรับใช้ค้นหาข้อมูลรวมทั้งโรงเรียน"""
        if self.teachers_cache:
            return self.get_teacher_info(self.teachers_cache[0]["username"])
        return self.get_teacher_info("ptn101")

    # -------------------------------------------------------------
    # ฟังก์ชัน 1: ตารางสอนของครู (get_teacher_schedule)
    # -------------------------------------------------------------
    def get_teacher_schedule(
        self, teacher_query: str = "", day_name: Optional[str] = None, period: Optional[str] = None
    ) -> dict[str, Any]:
        """
        ดึงตารางสอนของครู
        :param teacher_query: ชื่อครู หรือ username เช่น 'สถิตย์', 'ptn101'
        :param day_name: วัน เช่น 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์' (ถ้าไม่ระบุจะใช้วันปัจจุบัน)
        :param period: คาบ เช่น 'ชม.1', '1', 'คาบแรก'
        """
        _, current_thai, current_day = get_current_thai_date()
        target_day = day_name.strip() if day_name else current_day

        target, info = self.get_teacher_info(teacher_query)
        teacher_id = info.get("id_1", "")
        teacher_name = clean_html_text(f"{info.get('name_1', '')} {info.get('lname_1', '')}")

        res = self.client.post("table_teaching.php", {"id_1": teacher_id})

        days = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์"]
        schedule: dict[str, dict[str, str]] = {}

        rows = re.findall(r"<tr[\s\S]*?</tr>", res, re.I)
        for r in rows:
            tds = re.findall(r"<td[\s\S]*?</td>", r, re.I)
            cleaned_tds = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", td)).strip() for td in tds]
            if not cleaned_tds:
                continue
            day_match = next((d for d in days if d in cleaned_tds[0]), None)
            if day_match:
                schedule[day_match] = {}
                for period_idx, val in enumerate(cleaned_tds[1:], start=1):
                    val_cleaned = val.replace("&nbsp;", "").strip()
                    if val_cleaned and val_cleaned != "-":
                        schedule[day_match][f"ชม.{period_idx}"] = val_cleaned

        # กรองตามวัน
        day_schedule = schedule.get(target_day, {})

        # ถ้ามีการระบุคาบ เช่น คาบแรก, ชม.1
        target_period = None
        if period:
            p_str = period.strip().lower()
            if "แรก" in p_str or "1" in p_str:
                target_period = "ชม.1"
            elif "2" in p_str:
                target_period = "ชม.2"
            elif "3" in p_str:
                target_period = "ชม.3"
            elif "4" in p_str:
                target_period = "ชม.4"
            elif "5" in p_str:
                target_period = "ชม.5"
            elif "6" in p_str:
                target_period = "ชม.6"
            elif "7" in p_str:
                target_period = "ชม.7"
            elif "8" in p_str:
                target_period = "ชม.8"

        first_period = day_schedule.get("ชม.1", "ไม่มีสอนในคาบนี้ (ว่าง)")

        return {
            "teacher_username": target["username"],
            "teacher_name": teacher_name,
            "query_day": target_day,
            "current_day": current_day,
            "current_date": current_thai,
            "first_period": first_period,
            "target_period": target_period,
            "target_period_subject": day_schedule.get(target_period) if target_period else None,
            "day_schedule": day_schedule,
            "full_week_schedule": schedule,
        }

    # -------------------------------------------------------------
    # ฟังก์ชัน 2: สถิติการมาเรียนทั้งโรงเรียน (get_daily_attendance_summary)
    # -------------------------------------------------------------
    def get_daily_attendance_summary(self, date_str: Optional[str] = None) -> dict[str, Any]:
        """
        ดึงสรุปสถิตินักเรียนมาเรียนทั้งโรงเรียนประจำวัน
        :param date_str: วันที่ เช่น '2026-09-17' หรือ '17/09/2569' หรือ None (ใช้วันปัจจุบัน)
        """
        cur_iso, cur_thai, _ = get_current_thai_date()
        target_date_iso = date_str if (date_str and "-" in date_str) else cur_iso

        _, info = self.get_default_teacher_info()
        res = self.client.post(
            "re_all_act.php",
            {
                "id_1": info["id_1"],
                "date1": target_date_iso,
                "button2": "  ค้นหา  ",
                "m": "1",
                "m2": "1",
                "room": "all",
            },
        )

        total_stu_match = re.search(r"จำนวนนักเรียนทั้งหมด\s*([0-9,]+)\s*คน", res)
        total_students = int(total_stu_match.group(1).replace(",", "")) if total_stu_match else 0

        date_header_match = re.search(r"ประจำวันที่\s*([0-9/]+)", res)
        display_date = date_header_match.group(1) if date_header_match else cur_thai

        rows = re.findall(r"<tr[\s\S]*?</tr>", res, re.I)
        rooms_data: list[dict[str, Any]] = []

        for r in rows:
            tds = re.findall(r"<td[\s\S]*?</td>", r, re.I)
            vals = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", td)).strip() for td in tds]
            if not vals:
                continue
            if re.match(r"^(ม\.\d+/\d+)", vals[0]):
                room_name = vals[0]
                try:
                    present = int(vals[1])
                    present_pct = vals[2]
                    absent = int(vals[3])
                    absent_pct = vals[4]
                    leave = int(vals[5])
                    late = int(vals[7])
                    total_checked = int(vals[9]) if vals[9].isdigit() else (present + absent + leave + late)
                    status_text = "เช็คแล้ว" if total_checked > 0 else "ยังไม่เช็คชื่อ"
                    advisors = clean_html_text(vals[10]) if len(vals) > 10 else ""
                    rooms_data.append({
                        "room": room_name,
                        "present": present,
                        "present_pct": present_pct,
                        "absent": absent,
                        "absent_pct": absent_pct,
                        "leave": leave,
                        "late": late,
                        "total_checked": total_checked,
                        "status": status_text,
                        "advisors": advisors,
                    })
                except Exception:
                    pass

        total_present = sum(r["present"] for r in rooms_data)
        total_absent = sum(r["absent"] for r in rooms_data)
        total_leave = sum(r["leave"] for r in rooms_data)
        total_late = sum(r["late"] for r in rooms_data)
        total_checked = sum(r["total_checked"] for r in rooms_data)

        present_rate = f"{(total_present / total_checked * 100):.2f}%" if total_checked else "0.00%"
        absent_rate = f"{(total_absent / total_checked * 100):.2f}%" if total_checked else "0.00%"

        unchecked_rooms = [r["room"] for r in rooms_data if r["status"] == "ยังไม่เช็คชื่อ"]

        return {
            "date": display_date,
            "total_students": total_students,
            "total_checked": total_checked,
            "total_present": total_present,
            "present_pct": present_rate,
            "total_absent": total_absent,
            "absent_pct": absent_rate,
            "total_leave": total_leave,
            "total_late": total_late,
            "unchecked_rooms": unchecked_rooms,
            "rooms_count": len(rooms_data),
            "rooms": rooms_data,
        }

    # -------------------------------------------------------------
    # ฟังก์ชัน 3: เช็คคนขาดแถวหน้าเสาธงรายห้อง (get_morning_assembly_absent)
    # -------------------------------------------------------------
    def get_morning_assembly_absent(self, room: str, date_str: Optional[str] = None) -> dict[str, Any]:
        """
        ดึงรายชื่อนักเรียนที่ขาด/ลา/มาสาย ในการเข้าแถวหน้าเสาธง
        :param room: เช่น 'ม.3/1', '3/1', 'ม.4/1'
        :param date_str: วันที่ เช่น '17/09/2569' หรือ '2026-09-17' (ถ้าไม่ระบุใช้วันล่าสุดที่บันทึก)
        """
        clean_room = room.strip()
        if not clean_room.startswith("ม.") and "/" in clean_room:
            clean_room = f"ม.{clean_room}"

        # 1. หาครูที่ปรึกษาประจำห้องนี้จากสรุปโรงเรียน
        daily = self.get_daily_attendance_summary()
        room_info = next((r for r in daily.get("rooms", []) if r["room"] == clean_room), None)
        advisor_name = room_info.get("advisors", "") if room_info else ""

        # หาครูที่เกี่ยวข้องเพื่อเข้าหน้า re_act
        target_teacher = None
        if advisor_name:
            for t in self.teachers_cache:
                if t["name"] and any(part in t["name"] for part in advisor_name.split() if len(part) > 3):
                    target_teacher = t
                    break

        if not target_teacher:
            # ใช้บัญชีที่มีการแมปห้อง
            room_advisor_map = {
                "ม.1/1": "ptn117",
                "ม.1/2": "ptn119",
                "ม.2/1": "ptn118",
                "ม.3/1": "ptn1617",
                "ม.3/2": "ptn102",
                "ม.3/3": "ptn107",
                "ม.4/1": "ptn101",
                "ม.4/2": "ptn116",
                "ม.5/1": "ptn115",
                "ม.5/2": "ptn104",
                "ม.5/3": "ptn114",
                "ม.6/1": "ptn103",
                "ม.6/2": "nuy",
            }
            mapped_user = room_advisor_map.get(clean_room)
            if mapped_user:
                target_teacher = next((t for t in self.teachers_cache if t["username"] == mapped_user), None)

        if not target_teacher:
            # ถ้าไม่พบบัญชีครูประจำชั้น ใช้บัญชีแรก
            target_teacher = self.teachers_cache[0] if self.teachers_cache else {"username": "ptn101", "password": "101"}

        _, info = self.get_teacher_info(target_teacher["username"])
        res = self.client.post("re_act.php", {"id_1": info["id_1"]})

        dates = re.findall(r"<text[^>]*>\s*(\d{2}/\d{2}/25\d{2})", res)
        if not dates:
            dates = re.findall(r"\b(\d{2}/\d{2}/25\d{2})\b", res)

        num_dates = len(dates)
        target_date = date_str if date_str else (dates[-1] if dates else "")

        student_headers = list(re.finditer(
            r"<td[^>]*><span[^>]*class=[\"']style39[\"'][^>]*>&nbsp;(\d+)</span></td>\s*"
            r"<td[^>]*><div[^>]*class=[\"']style39[\"'][^>]*>(\d+)</div></td>\s*"
            r"<td[^>]*><span[^>]*class=[\"']style39[\"'][^>]*>&nbsp;([^<]+)</span></td>",
            res,
            re.I,
        ))

        students_all: list[dict[str, Any]] = []
        absent_students: list[dict[str, Any]] = []
        leave_students: list[dict[str, Any]] = []
        late_students: list[dict[str, Any]] = []

        for i, sh in enumerate(student_headers):
            no, stu_id, name = sh.groups()
            start_pos = sh.end()
            end_pos = student_headers[i + 1].start() if i + 1 < len(student_headers) else res.find("</table>", start_pos)
            chunk = res[start_pos:end_pos]

            tds = re.findall(r"<td[^>]*>([\s\S]*?)</td>", chunk)
            date_tds = tds[:num_dates]
            cleaned_statuses = [re.sub(r"<[^>]+>", "", td).strip() for td in date_tds]

            # หาสถานะวันที่ต้องการ
            status_char = cleaned_statuses[-1] if cleaned_statuses else "-"
            status_text = STATUS_MAP.get(status_char, status_char or "ไม่ระบุ")

            item = {
                "no": int(no),
                "student_id": stu_id,
                "name": clean_html_text(name),
                "status": status_text,
            }
            students_all.append(item)

            if status_text == "ขาด":
                absent_students.append(item)
            elif status_text == "ลา":
                leave_students.append(item)
            elif status_text == "สาย":
                late_students.append(item)

        return {
            "room": clean_room,
            "advisor": advisor_name,
            "date": target_date,
            "total_students": len(students_all),
            "present_count": len(students_all) - len(absent_students) - len(leave_students) - len(late_students),
            "absent_count": len(absent_students),
            "absent_list": absent_students,
            "leave_count": len(leave_students),
            "leave_list": leave_students,
            "late_count": len(late_students),
            "late_list": late_students,
            "all_students": students_all,
        }

    # -------------------------------------------------------------
    # ฟังก์ชัน 4: ตารางเรียนของห้องเรียน (get_class_schedule)
    # -------------------------------------------------------------
    def get_class_schedule(self, room: str, day_name: Optional[str] = None) -> dict[str, Any]:
        """
        ดึงตารางเรียนของห้องเรียน เช่น ม.3/1, ม.4/1
        """
        clean_room = room.strip()
        if not clean_room.startswith("ม.") and "/" in clean_room:
            clean_room = f"ม.{clean_room}"

        _, current_thai, current_day = get_current_thai_date()
        target_day = day_name.strip() if day_name else current_day

        _, info = self.get_default_teacher_info()
        res = self.client.post(
            "table_class.php",
            {
                "id_1": info["id_1"],
                "m": "1",
                "level": clean_room,
            },
        )

        days = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์"]
        schedule: dict[str, dict[str, str]] = {}

        rows = re.findall(r"<tr[\s\S]*?</tr>", res, re.I)
        for r in rows:
            tds = re.findall(r"<td[\s\S]*?</td>", r, re.I)
            cleaned_tds = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", td)).strip() for td in tds]
            if not cleaned_tds:
                continue
            day_match = next((d for d in days if d in cleaned_tds[0]), None)
            if day_match:
                schedule[day_match] = {}
                for period_idx, val in enumerate(cleaned_tds[1:], start=1):
                    val_cleaned = val.replace("&nbsp;", "").strip()
                    if val_cleaned and val_cleaned != "-":
                        schedule[day_match][f"ชม.{period_idx}"] = val_cleaned

        return {
            "room": clean_room,
            "query_day": target_day,
            "day_schedule": schedule.get(target_day, {}),
            "full_week_schedule": schedule,
        }

    # -------------------------------------------------------------
    # ระบบถาม-ตอบอัจฉริยะ (AI Query Handler & Gemini Function Calling)
    # -------------------------------------------------------------
    def get_gemini_tools_schema(self) -> list[dict[str, Any]]:
        """ส่งโครงสร้างเครื่องมือ (Function Declarations) สำหรับ Gemini API"""
        return [
            {
                "name": "get_teacher_schedule",
                "description": "ดึงข้อมูลตารางสอนของครู เช่น วันนี้คาบแรกสอนวิชาอะไร ม.ไหน หรือดูตารางสอนทั้งสัปดาห์",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "teacher_query": {
                            "type": "STRING",
                            "description": "ชื่อครู หรือ username เช่น 'สถิตย์', 'ptn101'",
                        },
                        "day_name": {
                            "type": "STRING",
                            "description": "วัน เช่น 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์'",
                        },
                        "period": {
                            "type": "STRING",
                            "description": "คาบที่ต้องการ เช่น 'ชม.1', 'คาบแรก', '1', '2'",
                        },
                    },
                },
            },
            {
                "name": "get_morning_assembly_absent",
                "description": "ตรวจสอบรายชื่อนักเรียนที่ขาดแถวหน้าเสาธง ลา หรือมาสาย ในห้องเรียนที่ระบุ เช่น ห้อง ม.3/1 ใครขาดแถว",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "room": {
                            "type": "STRING",
                            "description": "ห้องเรียน เช่น 'ม.3/1', 'ม.4/1', '3/1'",
                        },
                        "date_str": {
                            "type": "STRING",
                            "description": "วันที่ เช่น '17/09/2569' หรือ '2026-09-17'",
                        },
                    },
                    "required": ["room"],
                },
            },
            {
                "name": "get_daily_attendance_summary",
                "description": "ดูสรุปภาพรวมสถิตินักเรียนมาโรงเรียนทั้งหมดกี่คน ขาดกี่คน และสถานะรายห้องทั้งโรงเรียนประจำวัน",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "date_str": {
                            "type": "STRING",
                            "description": "วันที่ เช่น '2026-09-17'",
                        },
                    },
                },
            },
            {
                "name": "get_class_schedule",
                "description": "ดูตารางเรียนของห้องเรียน เช่น วันนี้ห้อง ม.3/1 มีเรียนวิชาอะไรบ้างในแต่ละคาบ",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "room": {
                            "type": "STRING",
                            "description": "ห้องเรียน เช่น 'ม.3/1'",
                        },
                        "day_name": {
                            "type": "STRING",
                            "description": "วัน เช่น 'จันทร์', 'อังคาร'",
                        },
                    },
                    "required": ["room"],
                },
            },
            {
                "name": "get_attendance_risk_summary",
                "description": "ดูรายชื่อนักเรียนที่มีความเสี่ยง มส. จากการมีเวลาเรียนไม่ถึง 80% หรือ 60%",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                },
            },
        ]

    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """เรียกทำงานฟังก์ชันตามที่ AI สั่ง"""
        if tool_name == "get_teacher_schedule":
            return self.get_teacher_schedule(
                teacher_query=args.get("teacher_query", ""),
                day_name=args.get("day_name"),
                period=args.get("period"),
            )
        elif tool_name == "get_morning_assembly_absent":
            return self.get_morning_assembly_absent(
                room=args.get("room", "ม.3/1"),
                date_str=args.get("date_str"),
            )
        elif tool_name == "get_daily_attendance_summary":
            return self.get_daily_attendance_summary(
                date_str=args.get("date_str"),
            )
        elif tool_name == "get_class_schedule":
            return self.get_class_schedule(
                room=args.get("room", "ม.3/1"),
                day_name=args.get("day_name"),
            )
        elif tool_name == "get_attendance_risk_summary":
            return self.get_attendance_risk_summary()
        return {"error": f"Unknown tool: {tool_name}"}

    def answer_query(
        self,
        query: str,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
        chat_history: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """
        ตอบคำถามผู้ใช้ผ่าน Gemini Function Calling หรือ Rule-based Fallback
        """
        api_key = (api_key or "").strip()
        if not api_key:
            api_key = os.environ.get("GEMINI_API_KEY", "").strip()

        # ถ้ามี API Key ใช้ Gemini Function Calling
        if api_key:
            try:
                return self._call_gemini_with_tools(query, api_key, model_name, chat_history)
            except Exception as e:
                # ถ้า Gemini API เกิดข้อผิดพลาด ให้ fallback เป็น rule-based ทันที
                fb = self._rule_based_answer(query)
                return f"{fb}\n\n*(หมายเหตุ: Gemini API เกิดข้อขัดข้องชั่วคราว [{e}] จึงแสดงผลลัพธ์ผ่านระบบเอนจินภายใน)*"

        # โหมดไม่มี API Key: ใช้ Rule-based อัจฉริยะ
        return self._rule_based_answer(query)

    def _call_gemini_with_tools(
        self,
        query: str,
        api_key: str,
        model_name: str,
        chat_history: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        import urllib.request

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        system_prompt = (
            "คุณคือ 'เลขาฯ AI ประจำโรงเรียนเปรมติณสูลานนท์' (School AI Secretary) "
            "มีหน้าที่ตอบคำถามของคุณครูและผู้บริหารเกี่ยวกับข้อมูลโรงเรียนอย่างสุภาพ อบอุ่น ถูกต้อง และเป็นมืออาชีพ\n"
            "คุณมีฟังก์ชันสำหรับดึงข้อมูลสดจากระบบ SSS โรงเรียนเปรมติณสูลานนท์ กรุณาเรียกใช้ Tool เพื่อดึงข้อมูลจริงทุกครั้ง\n"
            "เมื่อได้ข้อมูลจาก Tool แล้ว ให้สรุปตอบเป็นภาษาไทยพร้อมจัดรูปแบบ Markdown (เช่น สัญลักษณ์หัวข้อย่อย, ตัวหนา, อีโมจิ) ให้อ่านง่าย สบายตา"
        )

        contents = []
        if chat_history:
            for msg in chat_history[-6:]:
                role = "user" if msg.get("role") == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
        contents.append({"role": "user", "parts": [{"text": query}]})

        tools_spec = [{"function_declarations": self.get_gemini_tools_schema()}]

        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "tools": tools_spec,
            "generation_config": {"temperature": 0.2},
        }

        # 1. First Turn: ให้ Gemini ตัดสินใจเรียก Tool
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        candidate = data.get("candidates", [{}])[0]
        content_obj = candidate.get("content", {})
        parts = content_obj.get("parts", [])

        # ตรวจสอบว่ามีการเรียก Tool หรือไม่
        fn_call = next((p.get("functionCall") for p in parts if "functionCall" in p), None)
        if not fn_call:
            # ตอบกลับเป็นข้อความธรรมดา
            text_resp = "".join(p.get("text", "") for p in parts if "text" in p)
            return text_resp or "ขออภัยครับ ไม่สามารถสร้างคำตอบได้"

        # 2. ทำงานตาม Tool ที่เรียก
        fn_name = fn_call.get("name", "")
        fn_args = fn_call.get("args", {})
        tool_result = self.execute_tool(fn_name, fn_args)

        # 3. Second Turn: ส่งผลลัพธ์ Tool กลับไปให้ Gemini สรุปคำตอบ
        contents.append(content_obj)
        contents.append({
            "role": "function",
            "parts": [{
                "functionResponse": {
                    "name": fn_name,
                    "response": {"result": tool_result},
                }
            }],
        })

        payload2: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "tools": tools_spec,
            "generation_config": {"temperature": 0.3},
        }

        req2 = urllib.request.Request(
            url,
            data=json.dumps(payload2).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req2, timeout=30) as resp2:
            data2 = json.loads(resp2.read().decode("utf-8"))

        candidate2 = data2.get("candidates", [{}])[0]
        parts2 = candidate2.get("content", {}).get("parts", [])
        final_text = "".join(p.get("text", "") for p in parts2 if "text" in p)
        return final_text.strip()

    def _rule_based_answer(self, query: str) -> str:
        """ระบบตอบคำถามอัจฉริยะอัตโนมัติ (Rule-based Fast Mode)"""
        q = query.strip().lower()

        # คำถาม 1: ตารางสอน / คาบแรก / สอนวิชาอะไร
        if any(w in q for w in ["คาบแรก", "ตารางสอน", "สอนวิชาอะไร", "สอนคาบ", "สอน ม.", "สอนห้อง"]):
            # หาชื่อครู
            teacher_name = ""
            for t in self.teachers_cache:
                if t["name"] and any(part in q for part in t["name"].split() if len(part) > 3):
                    teacher_name = t["username"]
                    break
            sch = self.get_teacher_schedule(teacher_query=teacher_name, period="ชม.1")
            
            day = sch["query_day"]
            teacher = sch["teacher_name"]
            first_p = sch["first_period"]
            day_items = sch["day_schedule"]

            res = f"📅 **ข้อมูลตารางสอนของ {teacher}**\n\n"
            res += f"- **ประจำวัน:** วัน{day} (วันที่ {sch['current_date']})\n"
            res += f"- 🔔 **คาบแรก (ชม.1):** **{first_p}**\n\n"
            
            if day_items:
                res += f"**ตารางสอนตลอดทั้งวัน{day}:**\n"
                for p, subj in day_items.items():
                    res += f"- `{p}` : {subj}\n"
            else:
                res += f"- วัน{day} ไม่มีตารางสอน (เป็นวันว่าง)\n"
            return res

        # คำถาม 2: ขาดแถว / กิจกรรมหน้าเสาธง
        if any(w in q for w in ["ขาดแถว", "เข้าแถว", "หน้าเสาธง", "ไม่มาแถว", "เช็คแถว"]):
            # หาห้อง เช่น ม.3/1, 3/1
            room_match = re.search(r"(?:ม\.)?([1-6]/[1-9])", q)
            room = f"ม.{room_match.group(1)}" if room_match else "ม.3/1"
            absent_info = self.get_morning_assembly_absent(room=room)

            res = f"🚩 **ผลการเช็คกิจกรรมหน้าเสาธง ห้อง {absent_info['room']}**\n\n"
            res += f"- **ประจำวันที่:** {absent_info['date']}\n"
            if absent_info.get("advisor"):
                res += f"- **ครูที่ปรึกษา:** {absent_info['advisor']}\n"
            res += f"- **นักเรียนทั้งหมด:** {absent_info['total_students']} คน (มาเข้าแถว {absent_info['present_count']} คน)\n"
            res += f"- ❌ **ขาดแถว:** {absent_info['absent_count']} คน\n"
            res += f"- ⚠️ **ลา:** {absent_info['leave_count']} คน / **มาสาย:** {absent_info['late_count']} คน\n\n"

            if absent_info["absent_list"]:
                res += "**รายชื่อนักเรียนที่ขาดแถว:**\n"
                for s in absent_info["absent_list"]:
                    res += f"- เลขที่ {s['no']} (รหัส {s['student_id']}) **{s['name']}**\n"
            
            if absent_info["leave_list"]:
                res += "\n**รายชื่อนักเรียนที่ลา:**\n"
                for s in absent_info["leave_list"]:
                    res += f"- เลขที่ {s['no']} (รหัส {s['student_id']}) **{s['name']}** (ลา)\n"

            if not absent_info["absent_list"] and not absent_info["leave_list"]:
                res += "✨ **ยอดเยี่ยมมากครับ! นักเรียนห้องนี้มาเข้าแถวครบทุกคน**\n"

            return res

        # คำถาม 3: นักเรียนมาโรงเรียนกี่คน / สถิติมาเรียน
        if any(w in q for w in ["มากี่คน", "มาโรงเรียนกี่คน", "สถิติมาเรียน", "ภาพรวม", "นักเรียนทั้งหมด", "ขาดเรียนกี่คน"]):
            daily = self.get_daily_attendance_summary()
            res = f"🏫 **สรุปภาพรวมการมาเรียนทั้งโรงเรียน (ประจำวันที่ {daily['date']})**\n\n"
            res += f"- **นักเรียนทั้งหมดในระบบ:** {daily['total_students']} คน\n"
            res += f"- **บันทึกเช็คชื่อแล้ว:** {daily['total_checked']} คน\n"
            res += f"- ✅ **มาเรียน:** **{daily['total_present']} คน ({daily['present_pct']})**\n"
            res += f"- ❌ **ขาดเรียน:** **{daily['total_absent']} คน ({daily['absent_pct']})**\n"
            res += f"- 📋 **ลา:** {daily['total_leave']} คน / **มาสาย:** {daily['total_late']} คน\n\n"

            if daily.get("unchecked_rooms"):
                res += f"⚠️ **ห้องที่ยังไม่ได้บันทึกเช็คชื่อ ({len(daily['unchecked_rooms'])} ห้อง):**\n"
                res += f"`{', '.join(daily['unchecked_rooms'])}`\n"

            return res

        # คำถาม 4: นักเรียนเสี่ยง มส.
        if any(w in q for w in ["มส", "เสี่ยง", "เวลาเรียนไม่ถึง", "ขาดบ่อย", "ติด มส."]):
            risk = self.get_attendance_risk_summary()
            if risk.get("status") == "not_found":
                return "⚠️ ยังไม่พบข้อมูลการประมวลผลความเสี่ยงเวลาเรียน กรุณารันการตรวจที่แท็บแรกก่อนครับ"

            res = f"⚠️ **รายงานกลุ่มนักเรียนเสี่ยง มส. (เวลาเรียนต่ำกว่าเกณฑ์)**\n\n"
            res += f"- **จำนวนนักเรียนกลุ่มเสี่ยงทั้งหมด:** **{risk['risk_students_count']} คน**\n"
            res += f"- 🔴 **ความเสี่ยงสูง (เวลาเรียน < 60%):** {risk['high_risk_count']} คน\n"
            res += f"- 🟡 **ความเสี่ยงปานกลาง (เวลาเรียน 60-80%):** {risk['medium_risk_count']} คน\n\n"
            res += "**ตัวอย่างรายชื่อนักเรียนที่มีความเสี่ยง:**\n"
            for s in risk.get("students", [])[:10]:
                res += f"- {s.get('student_name')} ({s.get('class_display')}) -> วิชาเสี่ยง: {s.get('risk_level')}\n"
            return res

        # คำถาม 5: ตารางเรียนของห้อง
        if any(w in q for w in ["ตารางเรียน", "เรียนวิชาอะไร", "ห้องเรียน"]):
            room_match = re.search(r"(?:ม\.)?([1-6]/[1-9])", q)
            room = f"ม.{room_match.group(1)}" if room_match else "ม.3/1"
            cls = self.get_class_schedule(room=room)

            res = f"📖 **ตารางเรียน ชั้น {cls['room']} (วัน{cls['query_day']})**\n\n"
            if cls["day_schedule"]:
                for p, subj in cls["day_schedule"].items():
                    res += f"- `{p}` : {subj}\n"
            else:
                res += f"ไม่พบข้อมูลตารางเรียนในวัน{cls['query_day']}\n"
            return res

        # Default fallback
        return (
            "สวัสดีครับ! ผมคือ **เลขาฯ AI ประจำโรงเรียนเปรมติณสูลานนท์** 👩‍💼\n\n"
            "คุณครูสามารถพิมพ์สอบถามข้อมูลสดของโรงเรียนได้ทันที เช่น:\n"
            "- 📅 *'วันนี้คาบแรกฉันสอนวิชาอะไร ม.ไหน'*\n"
            "- 🚩 *'วันนี้ ห้อง ม.3/1 ใครขาดแถวบ้าง'*\n"
            "- 🏫 *'วันนี้มีนักเรียนมาโรงเรียนกี่คน สรุปภาพรวม'*\n"
            "- ⚠️ *'มีนักเรียนคนไหนที่เสี่ยง มส. บ้าง'*\n"
            "- 📖 *'ตารางเรียนห้อง ม.3/1 วันนี้'*"
        )

