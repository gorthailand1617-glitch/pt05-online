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
TEACHERS_MAP_JSON = BASE_DIR / "tools" / "teachers_map.json"
TEACHERS_SCHEDULES_CACHE_JSON = BASE_DIR / "tools" / "teachers_schedules_cache.json"

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


def clean_thai_name(name: str) -> str:
    cleaned = clean_html_text(name)
    cleaned = re.sub(r"^(นาย|นางสาว|นาง)\1+", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_name_query(text: str) -> str:
    s = (text or "").replace("ฏ", "ฎ")
    prefixes = [
        "ฉันคือครู", "ฉันชื่อครู", "ฉันคือคุณครู", "ฉันชื่อคุณครู",
        "ฉันคืออาจารย์", "ฉันชื่ออาจารย์", "ฉันคือ", "ฉันชื่อ",
        "คุณครู", "ครู", "อาจารย์", "อ.", "นาย", "นางสาว", "นาง"
    ]
    for p in prefixes:
        s = s.replace(p, " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def parse_thai_day_and_date(query: str) -> tuple[str, str, str, bool, str]:
    """คืนค่า (ชื่อวัน เช่น 'ศุกร์', YYYY-MM-DD, DD/MM/YYYY_THAI, เป็นวันหยุดหรือไม่, คำระบุสัมพัทธ์ เช่น 'พรุ่งนี้')"""
    now = datetime.datetime.now()
    q = (query or "").strip()
    rel_label = "วันนี้"
    if "พรุ่งนี้" in q or "วันพรุ่งนี้" in q:
        target_date = now + datetime.timedelta(days=1)
        rel_label = "พรุ่งนี้"
    elif "มะรืน" in q or "มะรืนนี้" in q:
        target_date = now + datetime.timedelta(days=2)
        rel_label = "มะรืนนี้"
    elif "เมื่อวาน" in q or "เมื่อวานนี้" in q:
        target_date = now - datetime.timedelta(days=1)
        rel_label = "เมื่อวานนี้"
    else:
        day_matched = None
        for thai_d in ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]:
            if thai_d in q:
                day_matched = "พฤหัสบดี" if thai_d == "พฤหัส" else thai_d
                break
        if day_matched:
            days_order = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
            delta_days = days_order.index(day_matched) - now.weekday()
            target_date = now + datetime.timedelta(days=delta_days)
            rel_label = f"วัน{day_matched}"
        else:
            target_date = now

    b_yr = target_date.year + 543
    date_iso = target_date.strftime("%Y-%m-%d")
    date_thai = f"{target_date.day:02d}/{target_date.month:02d}/{b_yr}"
    raw_day_name = THAI_DAYS.get(target_date.weekday(), "จันทร์")
    day_name = "พฤหัสบดี" if raw_day_name == "พฤหัส" else raw_day_name
    is_weekend = target_date.weekday() in (5, 6)
    return day_name, date_iso, date_thai, is_weekend, rel_label


def get_current_thai_date() -> tuple[str, str, str]:
    """คืนค่า (YYYY-MM-DD, DD/MM/YYYY_THAI, ชื่อวันภาษาไทย)"""
    day_name, date_iso, date_thai, _, _ = parse_thai_day_and_date("วันนี้")
    return date_iso, date_thai, day_name


class SchoolAssistantEngine:
    def __init__(self, default_teacher_user: str = "ptn1617") -> None:
        self.client = SssClient()
        self.teachers_cache: list[dict[str, str]] = []
        self.teachers_name_map: dict[str, str] = {}
        self.schedules_cache: dict[str, Any] = {}
        self.logged_in_sessions: dict[str, dict[str, str]] = {}
        self.default_teacher_user = default_teacher_user
        self._load_teacher_accounts()
        self._load_schedules_cache()

    def _load_schedules_cache(self) -> None:
        """โหลดตารางสอนที่แคชไว้ของครูทุกคน เพื่อการตอบสนองทันที (Instant Response < 0.001s)"""
        if TEACHERS_SCHEDULES_CACHE_JSON.exists():
            try:
                with TEACHERS_SCHEDULES_CACHE_JSON.open("r", encoding="utf-8") as f:
                    self.schedules_cache = json.load(f)
            except Exception:
                self.schedules_cache = {}

    def _save_schedules_cache(self) -> None:
        try:
            with TEACHERS_SCHEDULES_CACHE_JSON.open("w", encoding="utf-8") as f:
                json.dump(self.schedules_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_teacher_accounts(self) -> None:
        # 1. โหลดข้อมูลแมปชื่อครูจาก JSON
        if TEACHERS_MAP_JSON.exists():
            try:
                with TEACHERS_MAP_JSON.open("r", encoding="utf-8") as f:
                    self.teachers_name_map = json.load(f)
            except Exception:
                pass

        file_to_load = TEACHERS_CSV if TEACHERS_CSV.exists() else SAMPLE_TEACHERS_CSV
        if not file_to_load.exists():
            return
        try:
            with file_to_load.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    username = r.get("username", "").strip()
                    password = r.get("password", "").strip()
                    name = r.get("name", "").strip() or self.teachers_name_map.get(username, "")
                    if username == "ptn1617" and not name:
                        name = "กรกฎ รัตนะโช"
                    if username and password:
                        cleaned_n = clean_thai_name(name)
                        self.teachers_cache.append({
                            "username": username,
                            "password": password,
                            "name": cleaned_n,
                        })
                        if cleaned_n:
                            self.teachers_name_map[username] = cleaned_n
        except Exception:
            pass

    def get_teacher_display_name(self, username: str) -> str:
        return self.teachers_name_map.get(username, username)

    def get_teacher_info(self, teacher_query: str = "", default_user: Optional[str] = None) -> tuple[dict[str, str], dict[str, str]]:
        """ค้นหาและล็อกอินครูจาก username หรือชื่อครู (รองรับคำว่า 'ฉัน' โดยใช้ default_user)"""
        target = None
        q = (teacher_query or "").strip()
        q_norm = normalize_name_query(q)
        def_user = default_user or self.default_teacher_user

        # ถ้า query เป็นคำแทนตัวเอง หรือว่างเปล่า
        if not q or q in ["ฉัน", "ผม", "เรา", "หนู", "ครู", "ตัวฉัน", "ครูเอง"]:
            q = def_user
            q_norm = def_user.lower()

        # 1. ลองหาจาก username ตรงตัว
        for t in self.teachers_cache:
            if q.lower() == t["username"].lower() or t["username"].lower() in q.lower():
                target = t
                break

        # 2. ค้นหาจากชื่อครู (รองรับ ฏ/ฎ และการตัดคำ)
        if not target and q_norm:
            best_len = 0
            for t in self.teachers_cache:
                t_name = t.get("name", "")
                if not t_name:
                    continue
                t_norm = normalize_name_query(t_name)
                parts = [p for p in t_norm.split() if len(p) >= 3]
                for p in parts:
                    if p in q_norm or q_norm in p:
                        if len(p) > best_len:
                            best_len = len(p)
                            target = t

        # 3. Fallback: ถ้ายังไม่พบ ให้ใช้ def_user (ptn1617 ครูกรกฎ)
        if not target:
            for t in self.teachers_cache:
                if t["username"].lower() == def_user.lower():
                    target = t
                    break
            if not target and self.teachers_cache:
                target = self.teachers_cache[0]
            elif not target:
                target = {"username": "ptn1617", "password": "1617", "name": "กรกฎ รัตนะโช"}

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
        raw_target_day = day_name.strip() if day_name else current_day
        target_day = raw_target_day.replace("วัน", "").strip()
        if target_day == "พฤหัส":
            target_day = "พฤหัสบดี"

        target, info = self.get_teacher_info(teacher_query)
        u = target["username"]
        teacher_id = info.get("id_1", "")
        teacher_name = clean_thai_name(f"{info.get('name_1', '')} {info.get('lname_1', '')}")
        if not teacher_name or teacher_name.isspace():
            teacher_name = target.get("name", target["username"])

        # 1. ตรวจสอบจากแคชก่อน เพื่อความเร็วระดับมิลลิวินาที (Instant Speed < 0.001s)
        cached_entry = self.schedules_cache.get(u)
        if cached_entry and cached_entry.get("full_week_schedule"):
            schedule = cached_entry["full_week_schedule"]
            teacher_name = cached_entry.get("name") or teacher_name
        else:
            res = self.client.post("table_teaching.php", {"id_1": teacher_id})
            days = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์"]
            schedule = {}
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

            self.schedules_cache[u] = {
                "username": u,
                "name": teacher_name,
                "full_week_schedule": schedule,
                "updated_at": datetime.datetime.now().isoformat(),
            }
            self._save_schedules_cache()

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
        model_name: str = "gemini-3.7-flash",
        chat_history: Optional[list[dict[str, Any]]] = None,
        current_user: Optional[str] = None,
    ) -> str:
        """
        ตอบคำถามผู้ใช้ผ่าน Gemini Function Calling หรือ Rule-based Fallback
        """
        api_key = (api_key or "").strip()
        if not api_key:
            api_key = os.environ.get("GEMINI_API_KEY", "").strip()

        # ตรวจจับคุณครูจากคำถาม หรือจากประวัติการสนทนาย้อนหลัง (Conversational Session Memory)
        detected_user = None
        q_norm = normalize_name_query(query)
        has_name_in_q = False
        for t in self.teachers_cache:
            t_name = t.get("name", "")
            if not t_name:
                continue
            parts = [p for p in normalize_name_query(t_name).split() if len(p) >= 3]
            if any(p in q_norm for p in parts) or (t["username"].lower() in query.lower()):
                has_name_in_q = True
                detected_user = t["username"]
                break

        # ถ้าในคำถามปัจจุบันไม่มีการเอ่ยชื่อครู ให้ดูจากข้อความก่อนหน้าใน session
        if not has_name_in_q and chat_history:
            for msg in reversed(chat_history[-6:]):
                if msg.get("role") == "user":
                    m_norm = normalize_name_query(msg.get("content", ""))
                    for t in self.teachers_cache:
                        t_name = t.get("name", "")
                        if not t_name:
                            continue
                        parts = [p for p in normalize_name_query(t_name).split() if len(p) >= 3]
                        if any(p in m_norm for p in parts) or (t["username"].lower() in msg.get("content", "").lower()):
                            detected_user = t["username"]
                            break
                    if detected_user:
                        break

        active_user = detected_user or current_user or self.default_teacher_user

        # ถ้ามี API Key ใช้ Gemini Function Calling
        if api_key:
            try:
                return self._call_gemini_with_tools(query, api_key, model_name, chat_history, active_user)
            except Exception as e:
                # ถ้า Gemini API เกิดข้อผิดพลาด ให้ fallback เป็น rule-based ทันที
                fb = self._rule_based_answer(query, active_user)
                return f"{fb}\n\n*(หมายเหตุ: Gemini API เกิดข้อขัดข้องชั่วคราว [{e}] จึงแสดงผลลัพธ์ผ่านระบบเอนจินภายใน)*"

        # โหมดไม่มี API Key: ใช้ Rule-based อัจฉริยะ
        return self._rule_based_answer(query, active_user)

    def _call_gemini_with_tools(
        self,
        query: str,
        api_key: str,
        model_name: str,
        chat_history: Optional[list[dict[str, Any]]] = None,
        current_user: str = "ptn1617",
    ) -> str:
        import urllib.request
        import time

        def _post_with_retry(request_obj: urllib.request.Request, max_retries: int = 2) -> dict[str, Any]:
            for attempt in range(max_retries):
                try:
                    with urllib.request.urlopen(request_obj, timeout=30) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as he:
                    if he.code in (503, 429) and attempt < max_retries - 1:
                        time.sleep(1.5)
                        continue
                    raise he

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        cur_iso, cur_thai, cur_day = get_current_thai_date()
        tom_day, tom_iso, tom_thai, _, _ = parse_thai_day_and_date("พรุ่งนี้")
        curr_teacher_name = self.get_teacher_display_name(current_user)

        system_prompt = (
            "คุณคือ 'เลขาฯ AI ประจำโรงเรียนเปรมติณสูลานนท์' (School AI Secretary) "
            "มีหน้าที่ตอบคำถามของคุณครูและผู้บริหารเกี่ยวกับข้อมูลโรงเรียนอย่างสุภาพ อบอุ่น ถูกต้อง และเป็นมืออาชีพ\n"
            f"- วันนี้คือ: วัน{cur_day} ที่ {cur_thai}\n"
            f"- พรุ่งนี้คือ: วัน{tom_day} ที่ {tom_thai}\n"
            f"- คุณครูผู้ใช้งานปัจจุบัน (หากผู้ใช้กล่าวถึง 'ฉัน' หรือ 'ผม'): '{current_user}' ({curr_teacher_name})\n"
            "- ตัวอย่างรายชื่อคุณครูในระบบ:\n"
            "  * 'ptn1617' คือ ครูกรกฎ รัตนะโช\n"
            "  * 'ptn101' คือ ครูสถิตย์ ศรีวัชรกุล\n"
            "  * 'ptn122' คือ ครูวัฒนา มีศิลป์\n"
            "  * 'ptn115' คือ ครูปิยะทัศน์ แสงสว่าง\n"
            "  * 'ptn116' คือ ครูกัลญา สมประสงค์\n"
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
        data = _post_with_retry(req)

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
        data2 = _post_with_retry(req2)

        candidate2 = data2.get("candidates", [{}])[0]
        parts2 = candidate2.get("content", {}).get("parts", [])
        final_text = "".join(p.get("text", "") for p in parts2 if "text" in p)
        return final_text.strip()

    def _rule_based_answer(self, query: str, current_user: str = "ptn1617") -> str:
        """ระบบตอบคำถามอัจฉริยะอัตโนมัติ (Rule-based Fast Mode)"""
        q = (query or "").strip()
        q_lower = q.lower()

        day_name, date_iso, date_thai, is_weekend, rel_label = parse_thai_day_and_date(q)

        # คำถาม 1: ตารางสอน / คาบแรก / สอนวิชาอะไร / ถามต่อเรื่องวัน
        schedule_keywords = [
            "คาบแรก", "ตารางสอน", "สอนวิชาอะไร", "สอนคาบ", "สอน ม.", "สอนห้อง",
            "มีสอนไหม", "สอนอะไร", "สอนอะไรบ้าง", "ตาราง", "สอน", "คาบไหน", "มีสอน", "สอนกี่คาบ"
        ]
        day_tokens = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "พรุ่งนี้", "มะรืน", "เมื่อวาน"]
        is_sched_intent = any(w in q_lower for w in schedule_keywords) or (
            any(d in q for d in day_tokens) and any(x in q for x in ["ล่ะ", "ละ", "วัน", "คาบ", "ตาราง"])
        )

        if is_sched_intent:
            if is_weekend:
                return f"🏖️ **วัน{day_name} (วันที่ {date_thai})** เป็นวันหยุดสุดสัปดาห์ ไม่มีตารางเรียนตารางสอนครับ"

            # ตรวจสอบว่าใน q มีชื่อครูระบุไว้ชัดเจนหรือไม่ ถ้าไม่มี ให้ใช้ current_user จากโปรไฟล์หรือประวัติแชท
            t_target = q
            has_explicit_teacher = False
            for t in self.teachers_cache:
                t_name = t.get("name", "")
                if not t_name:
                    continue
                parts = [p for p in normalize_name_query(t_name).split() if len(p) >= 3]
                if any(p in normalize_name_query(q) for p in parts) or t["username"].lower() in q.lower():
                    has_explicit_teacher = True
                    t_target = t["username"]
                    break
            if not has_explicit_teacher:
                t_target = current_user

            sch = self.get_teacher_schedule(teacher_query=t_target, day_name=day_name)
            
            day = sch["query_day"]
            teacher = sch["teacher_name"]
            first_p = sch["first_period"]
            day_items = sch["day_schedule"]

            res = f"📅 **ข้อมูลตารางสอนของ {teacher}**\n\n"
            rel_str = f" ({rel_label} - วันที่ {date_thai})" if rel_label != f"วัน{day}" else f" (วันที่ {date_thai})"
            res += f"- **ประจำวัน:** วัน{day}{rel_str}\n"

            if "คาบแรก" in q_lower:
                res += f"- 🔔 **คาบแรก (ชม.1):** **{first_p}**\n\n"
            
            if day_items:
                res += f"**ตารางสอนตลอดทั้งวัน{day} (มีสอนทั้งหมด {len(day_items)} คาบ):**\n"
                for p, subj in day_items.items():
                    res += f"- `{p}` : {subj}\n"
            else:
                res += f"- วัน{day} ไม่มีตารางสอน (เป็นวันว่างของ{teacher})\n"
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

