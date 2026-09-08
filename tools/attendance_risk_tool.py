from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value, flags=re.MULTILINE).strip()
    return value


def extract_clean_room(level: str, class_codes: list[str]) -> str:
    candidates = []
    for c in class_codes:
        c = c.strip()
        if not c:
            continue
        # Check for e.g. "ม.5/1" or "5/1"
        m1 = re.search(r"(?:ม\.)?(\d+/\d+)", c)
        if m1:
            room = m1.group(1)
            candidates.append(f"ม.{room}" if not room.startswith("ม.") else room)
            continue
        # Check for single digit room e.g. "1", "2", "3"
        m2 = re.match(r"^(\d+)$", c)
        if m2:
            room = m2.group(1)
            lvl = level if level.startswith("ม.") else (f"ม.{level}" if level else "")
            if lvl:
                candidates.append(f"{lvl}/{room}")
            else:
                candidates.append(f"ห้อง {room}")
            continue

    if candidates:
        return Counter(candidates).most_common(1)[0][0]

    # Fallback to level if present
    lvl = level if level.startswith("ม.") else (f"ม.{level}" if level else "")
    for c in class_codes:
        if c and not any(ch in c for ch in ["(", ")", "_"]):
            return f"{lvl}/{c}" if lvl else c
    return lvl or "-"


@dataclass
class StudentSubjectAttendance:
    student_id: str
    student_name: str
    level: str
    class_code: str
    subject_code: str
    subject_name: str
    teacher_name: str
    teaching_id: str
    present: int
    pct: float
    absent: int
    leave: int
    late: int
    skip: int
    status: str  # '<60%' or '60-80%'

    @property
    def class_display(self) -> str:
        return extract_clean_room(self.level, [self.class_code])


@dataclass
class StudentAttendanceProfile:
    student_id: str
    student_name: str
    class_display: str
    level: str
    raw_class_codes: list[str] = field(default_factory=list)
    subjects_under_60: list[StudentSubjectAttendance] = field(default_factory=list)
    subjects_60_80: list[StudentSubjectAttendance] = field(default_factory=list)

    def resolve_class_display(self) -> str:
        return extract_clean_room(self.level, self.raw_class_codes)

    @property
    def total_risk_subjects(self) -> int:
        return len(self.subjects_under_60) + len(self.subjects_60_80)

    @property
    def total_absent(self) -> int:
        return sum(s.absent for s in self.subjects_under_60 + self.subjects_60_80)

    @property
    def total_leave(self) -> int:
        return sum(s.leave for s in self.subjects_under_60 + self.subjects_60_80)

    @property
    def total_late(self) -> int:
        return sum(s.late for s in self.subjects_under_60 + self.subjects_60_80)

    @property
    def total_skip(self) -> int:
        return sum(s.skip for s in self.subjects_under_60 + self.subjects_60_80)

    @property
    def risk_level(self) -> str:
        if len(self.subjects_under_60) >= 1 or self.total_risk_subjects >= 4:
            return "วิกฤต (Critical)"
        elif self.total_risk_subjects >= 2:
            return "เฝ้าระวังสูง (High Warning)"
        else:
            return "เฝ้าระวัง (Moderate Warning)"

    @property
    def ai_synthesis(self) -> str:
        notes = []
        u60 = len(self.subjects_under_60)
        u80 = len(self.subjects_60_80)
        
        if u60 > 0:
            subs_text = ", ".join([f"{s.subject_name} ({s.pct:.1f}%)" for s in self.subjects_under_60])
            notes.append(f"🔴 เวลาเรียนไม่ถึง 60% จำนวน {u60} วิชา ({subs_text}) เสี่ยงหมดสิทธิ์สอบ (มส.) ขั้นวิกฤต")
            
        if u80 > 0:
            subs_text = ", ".join([f"{s.subject_name} ({s.pct:.1f}%)" for s in self.subjects_60_80])
            notes.append(f"🟡 เวลาเรียน 60-80% จำนวน {u80} วิชา ({subs_text}) เข้าข่ายเฝ้าระวัง เสี่ยงติด มส.")

        behaviors = []
        if self.total_skip > 0:
            behaviors.append(f"มีพฤติกรรมหนีเรียน {self.total_skip} คาบ")
        if self.total_absent >= 15:
            behaviors.append(f"ขาดเรียนสะสมสูงมาก ({self.total_absent} คาบ)")
        elif self.total_absent >= 5:
            behaviors.append(f"ขาดเรียนสะสม {self.total_absent} คาบ")
        if self.total_late >= 5:
            behaviors.append(f"มาสายบ่อย ({self.total_late} คาบ)")

        if behaviors:
            notes.append("พฤติกรรมที่พบ: " + ", ".join(behaviors))

        if self.risk_level == "วิกฤต (Critical)":
            notes.append("ข้อเสนอแนะ: ครูที่ปรึกษาควรประสานผู้ปกครองเข้าพบด่วน และส่งต่อฝ่ายวิชาการเพื่อทำแผนฟื้นฟูเวลาเรียนก่อนสิ้นภาคเรียน")
        elif self.risk_level == "เฝ้าระวังสูง (High Warning)":
            notes.append("ข้อเสนอแนะ: ครูประจำวิชาควรแจ้งเตือนนักเรียนและมอบหมายภาระงานชดเชยเวลาเรียนให้ครบ 80% ก่อนสอบปลายภาค")
        else:
            notes.append("ข้อเสนอแนะ: ให้ครูประจำวิชาติดตามอย่างใกล้ชิดและมอบหมายงานเพื่อซ่อมเวลาเรียน")

        return " | ".join(notes)


def extract_attendance_records_from_html(
    html_content: str,
    default_sub_code: str = "",
    default_sub_name: str = "",
    default_teacher: str = "",
    default_level: str = "",
    default_class: str = "",
    teaching_id: str = "",
) -> list[StudentSubjectAttendance]:
    records = []
    
    sub_name = default_sub_name
    sub_code = default_sub_code
    teacher = default_teacher
    class_name = default_class
    level_name = default_level

    if not sub_name or not sub_code:
        m = re.search(r"วิชา\s*([^\r\n<]+?)\s*รหัส(?:วิชา)?\s*([^\r\n<]+?)(?:\s*จำนวน|$)", html_content)
        if m:
            if not sub_name:
                sub_name = clean_text(m.group(1))
            if not sub_code:
                sub_code = clean_text(m.group(2))

    if not teacher:
        m = re.search(r"ครูประจำวิชา\s*([^\r\n<]+)", html_content)
        if m:
            teacher = clean_text(m.group(1))

    if not class_name:
        m = re.search(r"รายงานเช็คชื่อเวลาเรียนนักเรียนชั้น\s*([^\r\n<]+)", html_content)
        if m:
            class_name = clean_text(m.group(1))

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html_content, re.DOTALL)
    for r in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.DOTALL)
        if len(tds) < 8:
            continue
            
        clean_tds = [clean_text(re.sub(r"<[^>]+>", "", c)) for c in tds]
        
        sid_raw = clean_tds[1]
        if not re.match(r"^\d{3,6}$", sid_raw):
            continue
            
        student_id = sid_raw
        student_name = clean_tds[2]
        
        try:
            present_val = int(float(clean_tds[-7]))
            pct_val = float(clean_tds[-6])
            absent_val = int(float(clean_tds[-4]))
            leave_val = int(float(clean_tds[-3]))
            late_val = int(float(clean_tds[-2]))
            skip_val = int(float(clean_tds[-1]))
        except (ValueError, IndexError):
            continue

        if present_val == 0 and pct_val == 0.0 and absent_val == 0 and leave_val == 0:
            continue

        status = ""
        if pct_val < 60.0:
            status = "<60%"
        elif pct_val < 80.0:
            status = "60-80%"

        if status:
            records.append(
                StudentSubjectAttendance(
                    student_id=student_id,
                    student_name=student_name,
                    level=level_name,
                    class_code=class_name,
                    subject_code=sub_code,
                    subject_name=sub_name,
                    teacher_name=teacher,
                    teaching_id=teaching_id,
                    present=present_val,
                    pct=pct_val,
                    absent=absent_val,
                    leave=leave_val,
                    late=late_val,
                    skip=skip_val,
                    status=status,
                )
            )

    return records


def analyze_attendance(
    raw_dir: Path,
    summary_json_path: Path | None = None
) -> tuple[list[StudentAttendanceProfile], list[StudentSubjectAttendance]]:
    summary_map: dict[str, dict[str, Any]] = {}
    if summary_json_path and summary_json_path.exists():
        try:
            items = json.loads(summary_json_path.read_text(encoding="utf-8"))
            for it in items:
                tid = str(it.get("teaching_id", ""))
                summary_map[tid] = it
        except Exception:
            pass

    files = list(raw_dir.glob("*/*_re_teaching.html"))
    all_subject_records: list[StudentSubjectAttendance] = []

    for p in files:
        tid_match = re.match(r"^(\d+)_re_teaching\.html$", p.name)
        tid = tid_match.group(1) if tid_match else ""
        meta = summary_map.get(tid, {})
        
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        records = extract_attendance_records_from_html(
            html_content=content,
            default_sub_code=meta.get("subject_code", ""),
            default_sub_name=meta.get("subject_name", ""),
            default_teacher=meta.get("teacher_name", ""),
            default_level=meta.get("level", ""),
            default_class=meta.get("class_code", ""),
            teaching_id=tid,
        )
        all_subject_records.extend(records)

    # Group by student
    student_dict: dict[str, StudentAttendanceProfile] = {}
    for r in all_subject_records:
        sid = r.student_id
        if sid not in student_dict:
            student_dict[sid] = StudentAttendanceProfile(
                student_id=sid,
                student_name=r.student_name,
                class_display=r.class_display,
                level=r.level,
                raw_class_codes=[r.class_code],
            )
        else:
            if len(r.student_name) > len(student_dict[sid].student_name):
                student_dict[sid].student_name = r.student_name
            student_dict[sid].raw_class_codes.append(r.class_code)
            if not student_dict[sid].level and r.level:
                student_dict[sid].level = r.level

        if r.status == "<60%":
            student_dict[sid].subjects_under_60.append(r)
        else:
            student_dict[sid].subjects_60_80.append(r)

    # Resolve optimal clean class_display for every student
    for p in student_dict.values():
        p.class_display = p.resolve_class_display()

    profiles = list(student_dict.values())
    profiles.sort(
        key=lambda p: (
            0 if "วิกฤต" in p.risk_level else (1 if "เฝ้าระวังสูง" in p.risk_level else 2),
            -p.total_risk_subjects,
            -len(p.subjects_under_60),
            p.class_display,
            p.student_id,
        )
    )

    return profiles, all_subject_records


def export_excel(
    profiles: list[StudentAttendanceProfile],
    subject_records: list[StudentSubjectAttendance],
    output_path: Path
) -> None:
    wb = Workbook()
    
    # -------------------------------------------------------------
    # 1. Sheet 1: สรุปสังเคราะห์รายบุคคล (AI Student Summary)
    # -------------------------------------------------------------
    ws1 = wb.active
    ws1.title = "สรุปสังเคราะห์รายบุคคล"
    ws1.views.sheetView[0].showGridLines = True

    font_header = Font(name="TH Sarabun New", size=15, bold=True, color="FFFFFF")
    fill_header = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    border_thin = Border(
        left=Side(style="thin", color="CCCCCC"),
        right=Side(style="thin", color="CCCCCC"),
        top=Side(style="thin", color="CCCCCC"),
        bottom=Side(style="thin", color="CCCCCC"),
    )
    font_body = Font(name="TH Sarabun New", size=13)
    
    fill_critical = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    font_critical = Font(name="TH Sarabun New", size=13, bold=True, color="C00000")
    fill_high_warning = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
    font_high_warning = Font(name="TH Sarabun New", size=13, bold=True, color="B25900")
    fill_warning = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    font_warning = Font(name="TH Sarabun New", size=13, bold=True, color="375623")

    headers1 = [
        "ลำดับ",
        "รหัสนักเรียน",
        "ชื่อ - สกุล",
        "ชั้น/ห้อง",
        "ระดับความเสี่ยง",
        "จำนวนวิชา <60%",
        "จำนวนวิชา 60-80%",
        "รวมวิชาที่มีปัญหา",
        "รายชื่อวิชาที่ไม่ถึง 60% (มส. วิกฤต)",
        "รายชื่อวิชาที่ 60-80% (มส. เฝ้าระวัง)",
        "ขาดรวม",
        "ลารวม",
        "สายรวม",
        "หนีรวม",
        "AI สังเคราะห์พฤติกรรม & ข้อเสนอแนะ",
    ]
    ws1.append(headers1)
    for col_idx in range(1, len(headers1) + 1):
        cell = ws1.cell(row=1, column=col_idx)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for idx, p in enumerate(profiles, start=1):
        subs_u60_str = "\n".join([f"• {s.subject_code} {s.subject_name} ({s.pct:.1f}%)" for s in p.subjects_under_60]) or "-"
        subs_60_80_str = "\n".join([f"• {s.subject_code} {s.subject_name} ({s.pct:.1f}%)" for s in p.subjects_60_80]) or "-"
        
        row_vals = [
            idx,
            p.student_id,
            p.student_name,
            p.class_display,
            p.risk_level,
            len(p.subjects_under_60),
            len(p.subjects_60_80),
            p.total_risk_subjects,
            subs_u60_str,
            subs_60_80_str,
            p.total_absent,
            p.total_leave,
            p.total_late,
            p.total_skip,
            p.ai_synthesis,
        ]
        ws1.append(row_vals)
        current_row = ws1.max_row
        
        for c_idx in range(1, len(headers1) + 1):
            cell = ws1.cell(row=current_row, column=c_idx)
            cell.font = font_body
            cell.border = border_thin
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if c_idx in (1, 2, 4, 6, 7, 8, 11, 12, 13, 14):
                cell.alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)

        risk_cell = ws1.cell(row=current_row, column=5)
        if "วิกฤต" in p.risk_level:
            risk_cell.fill = fill_critical
            risk_cell.font = font_critical
        elif "เฝ้าระวังสูง" in p.risk_level:
            risk_cell.fill = fill_high_warning
            risk_cell.font = font_high_warning
        else:
            risk_cell.fill = fill_warning
            risk_cell.font = font_warning

    ws1.auto_filter.ref = f"A1:{get_column_letter(len(headers1))}{ws1.max_row}"
    ws1.freeze_panes = "E2"

    col_widths1 = [6, 12, 24, 12, 18, 12, 14, 14, 35, 35, 8, 8, 8, 8, 55]
    for i, w in enumerate(col_widths1, start=1):
        ws1.column_dimensions[get_column_letter(i)].width = w

    # -------------------------------------------------------------
    # 2. Sheet 2: รายละเอียดแยกตามรายวิชา (Subject Detail Breakdown)
    # -------------------------------------------------------------
    ws2 = wb.create_sheet(title="รายละเอียดแยกรายวิชา")
    ws2.views.sheetView[0].showGridLines = True
    fill_header2 = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")

    headers2 = [
        "ลำดับ",
        "รหัสนักเรียน",
        "ชื่อ - สกุล",
        "ชั้น/ห้อง",
        "รหัสวิชา",
        "ชื่อวิชา",
        "ครูประจำวิชา",
        "สถานะเวลาเรียน",
        "% เวลาเรียน",
        "มา (ครั้ง)",
        "ขาด (ครั้ง)",
        "ลา (ครั้ง)",
        "สาย (ครั้ง)",
        "หนีเรียน (ครั้ง)",
        "Teaching ID",
    ]
    ws2.append(headers2)
    for col_idx in range(1, len(headers2) + 1):
        cell = ws2.cell(row=1, column=col_idx)
        cell.font = font_header
        cell.fill = fill_header2
        cell.alignment = Alignment(horizontal="center", vertical="center")

    sorted_sub_records = sorted(subject_records, key=lambda s: (s.class_display, s.subject_code, s.pct))
    for idx, s in enumerate(sorted_sub_records, start=1):
        row_vals = [
            idx,
            s.student_id,
            s.student_name,
            s.class_display,
            s.subject_code,
            s.subject_name,
            s.teacher_name,
            s.status,
            f"{s.pct:.2f}%",
            s.present,
            s.absent,
            s.leave,
            s.late,
            s.skip,
            s.teaching_id,
        ]
        ws2.append(row_vals)
        current_row = ws2.max_row
        for c_idx in range(1, len(headers2) + 1):
            cell = ws2.cell(row=current_row, column=c_idx)
            cell.font = font_body
            cell.border = border_thin
            cell.alignment = Alignment(vertical="center")
            if c_idx in (1, 2, 4, 5, 8, 9, 10, 11, 12, 13, 14, 15):
                cell.alignment = Alignment(horizontal="center", vertical="center")

        st_cell = ws2.cell(row=current_row, column=8)
        pct_cell = ws2.cell(row=current_row, column=9)
        if s.status == "<60%":
            st_cell.fill = fill_critical
            st_cell.font = font_critical
            pct_cell.font = font_critical
        else:
            st_cell.fill = fill_high_warning
            st_cell.font = font_high_warning
            pct_cell.font = font_high_warning

    ws2.auto_filter.ref = f"A1:{get_column_letter(len(headers2))}{ws2.max_row}"
    ws2.freeze_panes = "E2"

    col_widths2 = [6, 12, 24, 12, 12, 28, 22, 14, 12, 10, 10, 10, 10, 12, 12]
    for i, w in enumerate(col_widths2, start=1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    # -------------------------------------------------------------
    # 3. Sheet 3: สรุปภาพรวมสถิติรายห้อง (Classroom Overview)
    # -------------------------------------------------------------
    ws3 = wb.create_sheet(title="สรุปสถิติรายห้อง")
    ws3.views.sheetView[0].showGridLines = True
    fill_header3 = PatternFill(start_color="333F48", end_color="333F48", fill_type="solid")

    headers3 = [
        "ชั้น/ห้อง",
        "จำนวนนักเรียนกลุ่มเสี่ยง (คน)",
        "นักเรียนกลุ่มวิกฤต (<60%)",
        "นักเรียนกลุ่มเฝ้าระวัง (60-80%)",
        "รวมจำนวนวิชาที่เกิดปัญหา",
        "รายชื่อนักเรียนในกลุ่มเสี่ยง",
    ]
    ws3.append(headers3)
    for col_idx in range(1, len(headers3) + 1):
        cell = ws3.cell(row=1, column=col_idx)
        cell.font = font_header
        cell.fill = fill_header3
        cell.alignment = Alignment(horizontal="center", vertical="center")

    class_groups: dict[str, list[StudentAttendanceProfile]] = {}
    for p in profiles:
        cls = p.class_display or "ไม่ระบุ"
        class_groups.setdefault(cls, []).append(p)

    for cls_name in sorted(class_groups.keys()):
        studs = class_groups[cls_name]
        crit_count = sum(1 for s in studs if len(s.subjects_under_60) > 0)
        warn_count = sum(1 for s in studs if len(s.subjects_under_60) == 0 and len(s.subjects_60_80) > 0)
        total_risk_subs = sum(s.total_risk_subjects for s in studs)
        names_str = ", ".join([f"{s.student_name} ({s.student_id})" for s in studs])

        ws3.append([
            cls_name,
            len(studs),
            crit_count,
            warn_count,
            total_risk_subs,
            names_str,
        ])
        current_row = ws3.max_row
        for c_idx in range(1, len(headers3) + 1):
            cell = ws3.cell(row=current_row, column=c_idx)
            cell.font = font_body
            cell.border = border_thin
            if c_idx in (1, 2, 3, 4, 5):
                cell.alignment = Alignment(horizontal="center", vertical="top")
            else:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    col_widths3 = [14, 22, 22, 22, 22, 60]
    for i, w in enumerate(col_widths3, start=1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)


def export_json(
    profiles: list[StudentAttendanceProfile],
    subject_records: list[StudentSubjectAttendance],
    output_path: Path
) -> None:
    data = {
        "summary": {
            "total_at_risk_students": len(profiles),
            "critical_risk_students": sum(1 for p in profiles if "วิกฤต" in p.risk_level),
            "warning_students": sum(1 for p in profiles if "เฝ้าระวัง" in p.risk_level),
            "total_subject_records": len(subject_records),
            "records_under_60": sum(1 for s in subject_records if s.status == "<60%"),
            "records_60_80": sum(1 for s in subject_records if s.status == "60-80%"),
        },
        "students": [
            {
                "student_id": p.student_id,
                "student_name": p.student_name,
                "class": p.class_display,
                "level": p.level,
                "risk_level": p.risk_level,
                "total_risk_subjects": p.total_risk_subjects,
                "total_absent": p.total_absent,
                "total_leave": p.total_leave,
                "total_late": p.total_late,
                "total_skip": p.total_skip,
                "ai_synthesis": p.ai_synthesis,
                "subjects_under_60": [s.__dict__ for s in p.subjects_under_60],
                "subjects_60_80": [s.__dict__ for s in p.subjects_60_80],
            }
            for p in profiles
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def export_html_dashboard(
    profiles: list[StudentAttendanceProfile],
    subject_records: list[StudentSubjectAttendance],
    output_path: Path
) -> None:
    crit_count = sum(1 for p in profiles if "วิกฤต" in p.risk_level)
    high_warn_count = sum(1 for p in profiles if "เฝ้าระวังสูง" in p.risk_level)
    mod_warn_count = sum(1 for p in profiles if "เฝ้าระวัง (" in p.risk_level)
    total_records_60 = sum(1 for s in subject_records if s.status == "<60%")
    total_records_80 = sum(1 for s in subject_records if s.status == "60-80%")

    all_classes = sorted(list(set(p.class_display for p in profiles if p.class_display and p.class_display != "-")))

    html_content = f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>แดชบอร์ด AI สังเคราะห์นักเรียนเวลาเรียนไม่ถึง 60% และ 80%</title>
  <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --primary: #1e3a8a;
      --primary-light: #3b82f6;
      --danger: #dc2626;
      --danger-bg: #fee2e2;
      --warning: #d97706;
      --warning-bg: #fef3c7;
      --success: #16a34a;
      --success-bg: #dcfce7;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #1e293b;
      --text-muted: #64748b;
      --border: #e2e8f0;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Sarabun', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 24px;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; }}
    header {{
      background: linear-gradient(135deg, #1e3a8a 0%, #0284c7 100%);
      color: white;
      padding: 32px 28px;
      border-radius: 16px;
      box-shadow: 0 10px 25px -5px rgba(30, 58, 138, 0.25);
      margin-bottom: 28px;
    }}
    header h1 {{ font-size: 26px; font-weight: 700; margin-bottom: 8px; }}
    header p {{ opacity: 0.9; font-size: 15px; }}
    
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}
    .stat-card {{
      background: var(--card-bg);
      padding: 20px;
      border-radius: 14px;
      border: 1px solid var(--border);
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
      display: flex;
      flex-direction: column;
    }}
    .stat-card .label {{ font-size: 13px; color: var(--text-muted); font-weight: 500; margin-bottom: 6px; }}
    .stat-card .val {{ font-size: 28px; font-weight: 700; color: var(--text); }}
    .stat-card.danger .val {{ color: var(--danger); }}
    .stat-card.warning .val {{ color: var(--warning); }}
    .stat-card.primary .val {{ color: var(--primary-light); }}
    
    .controls {{
      background: var(--card-bg);
      padding: 18px 24px;
      border-radius: 14px;
      border: 1px solid var(--border);
      margin-bottom: 24px;
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
    }}
    .search-box {{
      flex: 1;
      min-width: 250px;
      position: relative;
    }}
    .search-box input {{
      width: 100%;
      padding: 10px 16px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 14px;
      font-family: inherit;
    }}
    .filter-group {{
      display: flex;
      gap: 12px;
      align-items: center;
    }}
    .filter-group select {{
      padding: 10px 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 14px;
      background: white;
      font-family: inherit;
      cursor: pointer;
    }}
    
    .table-card {{
      background: var(--card-bg);
      border-radius: 14px;
      border: 1px solid var(--border);
      box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
      overflow: hidden;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 14px;
    }}
    th {{
      background: #f1f5f9;
      color: #334155;
      font-weight: 600;
      padding: 14px 16px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}
    td {{
      padding: 14px 16px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    tr:hover td {{ background: #f8fafc; }}
    
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
    }}
    .badge-critical {{ background: var(--danger-bg); color: var(--danger); border: 1px solid #fca5a5; }}
    .badge-high-warning {{ background: var(--warning-bg); color: var(--warning); border: 1px solid #fde68a; }}
    .badge-warning {{ background: var(--success-bg); color: var(--success); border: 1px solid #86efac; }}
    
    .subject-tag {{
      display: inline-flex;
      align-items: center;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 12px;
      margin: 2px 4px 2px 0;
    }}
    .tag-u60 {{ background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }}
    .tag-60-80 {{ background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }}

    .ai-insight {{
      background: #eff6ff;
      border-left: 3px solid #3b82f6;
      padding: 10px 14px;
      border-radius: 0 8px 8px 0;
      font-size: 13px;
      color: #1e40af;
      margin-top: 6px;
      line-height: 1.5;
    }}

    @media (max-width: 900px) {{
      .controls {{ flex-direction: column; align-items: stretch; }}
      .table-card {{ overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>รายงาน AI สังเคราะห์นักเรียนเวลาเรียนไม่ถึง 60% และ 80%</h1>
      <p>ระบบตรวจสอบเวลาเรียนรายวิชา โรงเรียนเปรมติณสูลานนท์ | สังเคราะห์เพื่อเฝ้าระวังและป้องกันการติด มส.</p>
    </header>

    <div class="stats-grid">
      <div class="stat-card danger">
        <span class="label">นักเรียนกลุ่มวิกฤต (มีวิชา < 60%)</span>
        <span class="val">{crit_count} คน</span>
      </div>
      <div class="stat-card warning">
        <span class="label">นักเรียนกลุ่มเฝ้าระวังสูง (2+ วิชา)</span>
        <span class="val">{high_warn_count} คน</span>
      </div>
      <div class="stat-card primary">
        <span class="label">รวมนักเรียนกลุ่มเสี่ยงทั้งหมด</span>
        <span class="val">{len(profiles)} คน</span>
      </div>
      <div class="stat-card danger">
        <span class="label">จำนวนวิชาที่เวลาเรียน < 60%</span>
        <span class="val">{total_records_60} รายการ</span>
      </div>
      <div class="stat-card warning">
        <span class="label">จำนวนวิชาที่เวลาเรียน 60-80%</span>
        <span class="val">{total_records_80} รายการ</span>
      </div>
    </div>

    <div class="controls">
      <div class="search-box">
        <input type="text" id="searchInput" placeholder="🔍 ค้นหาด้วยชื่อ หรือ รหัสนักเรียน..." onkeyup="filterTable()">
      </div>
      <div class="filter-group">
        <select id="classFilter" onchange="filterTable()">
          <option value="">ทุกระดับชั้น/ห้อง</option>
          {"".join(f'<option value="{c}">{c}</option>' for c in all_classes)}
        </select>
        <select id="riskFilter" onchange="filterTable()">
          <option value="">ทุกระดับความเสี่ยง</option>
          <option value="วิกฤต">กลุ่มวิกฤต (Critical)</option>
          <option value="เฝ้าระวังสูง">เฝ้าระวังสูง (High Warning)</option>
          <option value="เฝ้าระวัง">เฝ้าระวังทั่วไป</option>
        </select>
      </div>
    </div>

    <div class="table-card">
      <table id="studentsTable">
        <thead>
          <tr>
            <th width="4%">ลำดับ</th>
            <th width="8%">รหัส</th>
            <th width="16%">ชื่อ - สกุล</th>
            <th width="8%">ชั้น/ห้อง</th>
            <th width="12%">ระดับความเสี่ยง</th>
            <th width="24%">รายวิชาที่มีปัญหา</th>
            <th width="10%">สถิติรวม</th>
            <th width="18%">AI สังเคราะห์ & ข้อเสนอแนะ</th>
          </tr>
        </thead>
        <tbody>
"""

    for idx, p in enumerate(profiles, start=1):
        if "วิกฤต" in p.risk_level:
            badge_class = "badge-critical"
        elif "เฝ้าระวังสูง" in p.risk_level:
            badge_class = "badge-high-warning"
        else:
            badge_class = "badge-warning"

        u60_html = "".join(
            f'<div class="subject-tag tag-u60" title="ครูผู้สอน: {s.teacher_name}">🔴 {s.subject_code} {s.subject_name} <strong>{s.pct:.1f}%</strong></div>'
            for s in p.subjects_under_60
        )
        u80_html = "".join(
            f'<div class="subject-tag tag-60-80" title="ครูผู้สอน: {s.teacher_name}">🟡 {s.subject_code} {s.subject_name} <strong>{s.pct:.1f}%</strong></div>'
            for s in p.subjects_60_80
        )

        stat_summary = f"""
          <div style="font-size: 12px; line-height: 1.5;">
            <div>ขาด: <strong>{p.total_absent}</strong> ครั้ง</div>
            <div>ลา: <strong>{p.total_leave}</strong> ครั้ง</div>
            <div>สาย: <strong>{p.total_late}</strong> ครั้ง</div>
            <div>หนีเรียน: <strong style="color:red;">{p.total_skip}</strong> ครั้ง</div>
          </div>
        """

        html_content += f"""
          <tr data-name="{p.student_name}" data-id="{p.student_id}" data-class="{p.class_display}" data-risk="{p.risk_level}">
            <td>{idx}</td>
            <td><strong>{p.student_id}</strong></td>
            <td>{p.student_name}</td>
            <td><span class="badge" style="background:#e2e8f0; color:#334155;">{p.class_display}</span></td>
            <td><span class="badge {badge_class}">{p.risk_level}</span></td>
            <td>
              {f'<div style="margin-bottom:6px;"><strong style="font-size:12px; color:#b91c1c;">ไม่ถึง 60% ({len(p.subjects_under_60)} วิชา):</strong><br>{u60_html}</div>' if p.subjects_under_60 else ''}
              {f'<div><strong style="font-size:12px; color:#b45309;">60 - 80% ({len(p.subjects_60_80)} วิชา):</strong><br>{u80_html}</div>' if p.subjects_60_80 else ''}
            </td>
            <td>{stat_summary}</td>
            <td><div class="ai-insight">{p.ai_synthesis}</div></td>
          </tr>
        """

    html_content += """
        </tbody>
      </table>
    </div>
  </div>

  <script>
    function filterTable() {
      const search = document.getElementById('searchInput').value.toLowerCase().trim();
      const cls = document.getElementById('classFilter').value;
      const risk = document.getElementById('riskFilter').value;
      
      const rows = document.querySelectorAll('#studentsTable tbody tr');
      rows.forEach(row => {
        const name = row.getAttribute('data-name').toLowerCase();
        const id = row.getAttribute('data-id').toLowerCase();
        const rowCls = row.getAttribute('data-class');
        const rowRisk = row.getAttribute('data-risk');
        
        const matchSearch = !search || name.includes(search) || id.includes(search);
        const matchCls = !cls || rowCls === cls;
        const matchRisk = !risk || rowRisk.includes(risk);
        
        if (matchSearch && matchCls && matchRisk) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
      });
    }
  </script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="ดึงและวิเคราะห์นักเรียนเวลาเรียนไม่ถึง 60% และ 80% พร้อม AI สังเคราะห์")
    parser.add_argument("--raw-dir", default=Path("output-pt05/raw"), type=Path, help="โฟลเดอร์ไฟล์ raw HTML")
    parser.add_argument("--summary", default=Path("output-pt05/pt05_summary.json"), type=Path, help="ไฟล์ pt05_summary.json")
    parser.add_argument("--out-dir", default=Path("output-pt05"), type=Path, help="โฟลเดอร์สำหรับเซฟผลลัพธ์")
    args = parser.parse_args()

    if not args.raw_dir.exists():
        print(f"ไม่พบโฟลเดอร์: {args.raw_dir}", file=sys.stderr)
        return 1

    print(f"กำลังประมวลผลข้อมูลเวลาเรียนจาก {args.raw_dir} ...")
    profiles, subject_records = analyze_attendance(args.raw_dir, args.summary)

    print(f"  พบนักเรียนกลุ่มเสี่ยงทั้งหมด: {len(profiles)} คน")
    print(f"  พบรายการวิชาที่มีปัญหาเวลาเรียน: {len(subject_records)} รายการ")
    crit = sum(1 for p in profiles if "วิกฤต" in p.risk_level)
    print(f"  - นักเรียนกลุ่มวิกฤต (<60%): {crit} คน")
    print(f"  - นักเรียนกลุ่มเฝ้าระวัง (60-80%): {len(profiles) - crit} คน")

    excel_path = args.out_dir / "student_attendance_risk_summary.xlsx"
    print(f"กำลังสร้างไฟล์ Excel: {excel_path} ...")
    export_excel(profiles, subject_records, excel_path)

    html_path = args.out_dir / "attendance_risk_dashboard.html"
    print(f"กำลังสร้างไฟล์ HTML Dashboard: {html_path} ...")
    export_html_dashboard(profiles, subject_records, html_path)

    json_path = args.out_dir / "student_attendance_risk_summary.json"
    print(f"กำลังสร้างไฟล์ JSON: {json_path} ...")
    export_json(profiles, subject_records, json_path)

    print("ประมวลผลและสร้างรายงานสรุปเรียบร้อยแล้ว!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
