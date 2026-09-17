"""
ระบบตรวจ ปถ.05 และวิเคราะห์ความเสี่ยงเวลาเรียนออนไลน์
PT05 Online Auditor & Attendance Risk Analyzer
"""

from __future__ import annotations

import csv
import datetime
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import zipfile

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# นำเข้าเครื่องมือจากโฟลเดอร์ tools
BASE_DIR = Path(__file__).resolve().parent
TOOLS_DIR = BASE_DIR / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    from pt05_tool import (
        SubjectRecord,
        fetch_teacher,
        fill_docx,
        normalize_filename,
        write_json,
        write_summary,
    )
    from attendance_risk_tool import (
        analyze_attendance,
        export_excel,
        export_html_dashboard,
        export_json as export_risk_json,
    )
    from school_assistant_engine import SchoolAssistantEngine
except ImportError as err:
    st.error(f"ไม่สามารถโหลดโมดูลระบบได้: {err}")
    st.stop()

# -------------------------------------------------------------
# การตั้งค่าหน้าเว็บ
# -------------------------------------------------------------
st.set_page_config(
    page_title="ระบบตรวจ ปถ.05 & วิเคราะห์เวลาเรียนออนไลน์",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS ตกแต่งสไตล์ให้สวยงาม ทันสมัย
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Sarabun', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #0284c7 100%);
        color: white;
        padding: 24px 28px;
        border-radius: 16px;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(30, 58, 138, 0.2);
    }
    .main-header h1 {
        color: #ffffff !important;
        font-size: 26px;
        font-weight: 700;
        margin: 0 0 6px 0;
    }
    .main-header p {
        color: #e0f2fe;
        font-size: 15px;
        margin: 0;
    }
    
    .stMetric {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 14px 18px;
        border-radius: 12px;
    }
    .stMetric label {
        font-size: 14px !important;
        color: #64748b !important;
    }
    
    .status-card {
        padding: 16px 20px;
        border-radius: 12px;
        margin-bottom: 16px;
        font-size: 15px;
    }
    .status-success {
        background-color: #dcfce7;
        color: #166534;
        border: 1px solid #86efac;
    }
    .status-warning {
        background-color: #fef3c7;
        color: #92400e;
        border: 1px solid #fcd34d;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------------------
# ส่วนหัวโปรแกรม
# -------------------------------------------------------------
st.markdown(
    """
    <div class="main-header">
        <h1>📋 ระบบตรวจ ปถ.05 และวิเคราะห์ความเสี่ยงเวลาเรียนออนไลน์</h1>
        <p>ดึงข้อมูลจากระบบ SSS (ay-software.in.th) อัตโนมัติ • สร้างเอกสารบันทึก ปถ.05 (Word) • สรุป Excel • สังเคราะห์กลุ่มเสี่ยง &lt;60% และ &lt;80%</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------------------
# Session State Initialization
# -------------------------------------------------------------
if "processed_data" not in st.session_state:
    st.session_state.processed_data = None
if "zip_buffer" not in st.session_state:
    st.session_state.zip_buffer = None
if "run_logs" not in st.session_state:
    st.session_state.run_logs = []
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = [
        {
            "role": "assistant",
            "content": (
                "สวัสดีครับคุณครู! ผมคือ **เลขาฯ AI ประจำโรงเรียนเปรมติณสูลานนท์** 👩‍💼\n\n"
                "ผมสามารถช่วยดึงข้อมูลสดจากระบบ SSS ให้คุณครูได้ทันที เช่น:\n"
                "- 📅 *'วันนี้คาบแรกฉันสอนวิชาอะไร ม.ไหน'*\n"
                "- 🚩 *'วันนี้ ห้อง ม.3/1 ใครขาดแถวบ้าง'*\n"
                "- 🏫 *'วันนี้มีนักเรียนมาโรงเรียนกี่คน สรุปภาพรวม'*\n"
                "- ⚠️ *'มีนักเรียนคนไหนที่เสี่ยง มส. บ้าง'*\n"
                "- 📖 *'วันนี้ห้อง ม.3/1 มีเรียนวิชาอะไรบ้าง'*\n\n"
                "พิมพ์คำถามหรือคลิกเลือกคำถามด่วนด้านล่างได้เลยครับ 👇"
            ),
        }
    ]
if "school_engine" not in st.session_state:
    st.session_state.school_engine = SchoolAssistantEngine()
if "quick_prompt" not in st.session_state:
    st.session_state.quick_prompt = None

# -------------------------------------------------------------
# Sidebar: แผงควบคุมและการตั้งค่า
# -------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ การตั้งค่าระบบ")

    term = st.selectbox("ภาคเรียน (Term)", ["1", "2"], index=0)
    year = st.text_input("ปีการศึกษา (Academic Year)", value="2569")

    use_custom_date = st.checkbox("กำหนดวันที่ตรวจสอบเอง", value=False)
    if use_custom_date:
        check_date = st.text_input("วันที่ตรวจสอบ (เช่น 4 กรกฎาคม 2569)", value="")
    else:
        # คำนวณวันที่ปัจจุบันแบบไทย
        today = datetime.date.today()
        thai_months = [
            "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
        ]
        thai_year = today.year + 543
        check_date = f"{today.day} {thai_months[today.month]} {thai_year}"
        st.caption(f"วันที่ตรวจสอบอัตโนมัติ: **{check_date}**")

    st.divider()
    st.subheader("📑 ตัวเลือกการประมวลผล")
    do_pt05 = st.checkbox("ตรวจ ปถ.05 (สร้าง Word + Excel)", value=True)
    do_risk = st.checkbox("วิเคราะห์ความเสี่ยงเวลาเรียน (<60%, <80%)", value=True)

    st.divider()
    st.caption("🌐 ระบบเชื่อมต่อ: `http://ay-software.in.th/ptn/`")
    st.caption("💡 ใช้งานฟรี ไม่มีค่าใช้จ่าย ประมวลผลบน Cloud 100%")

# -------------------------------------------------------------
# ฟังก์ชันอ่านรายชื่อครู
# -------------------------------------------------------------
def parse_teachers_csv(text_content: str) -> list[dict[str, str]]:
    results = []
    reader = csv.DictReader(io.StringIO(text_content))
    for row in reader:
        u = (row.get("username") or row.get("Username") or "").strip()
        p = (row.get("password") or row.get("Password") or "").strip()
        if u and p:
            results.append({"username": u, "password": p})
    return results

def parse_teachers_raw_text(text: str) -> list[dict[str, str]]:
    results = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.replace("\t", ",").split(",") if p.strip()]
        if len(parts) >= 2:
            if parts[0].lower() == "username":
                continue
            results.append({"username": parts[0], "password": parts[1]})
    return results

def get_sample_teachers() -> list[dict[str, str]]:
    sample_file = TOOLS_DIR / "teachers.sample.csv"
    if sample_file.exists():
        return parse_teachers_csv(sample_file.read_text(encoding="utf-8-sig", errors="replace"))
    return [
        {"username": "ptn101", "password": "101"},
        {"username": "ptn102", "password": "102"},
        {"username": "ptn103", "password": "303"},
    ]

# -------------------------------------------------------------
# หน้าหลัก: แบ่งแท็บการทำงาน
# -------------------------------------------------------------
main_tab1, main_tab2, main_tab3 = st.tabs([
    "📋 ตรวจ ปถ.05 และวิเคราะห์เวลาเรียน",
    "🤖 เลขาฯ AI ประจำโรงเรียน",
    "🔌 เชื่อมต่อ ChatGPT Custom GPT & API",
])

with main_tab1:
    col1, col2 = st.columns([3, 2])

teachers_to_process: list[dict[str, str]] = []

with col1:
    st.subheader("1️⃣ กำหนดรายชื่อครูที่ต้องการตรวจ")
    
    input_method = st.radio(
        "เลือกวิธีระบุรายชื่อครู:",
        [
            "🧪 ใช้รายชื่อตัวอย่างในระบบ (พร้อมทดสอบทันที)",
            "📁 อัปโหลดไฟล์ teachers.csv",
            "✍️ พิมพ์หรือวางข้อความ (Username, Password)",
        ],
        index=0,
        horizontal=False,
    )

    if input_method == "🧪 ใช้รายชื่อตัวอย่างในระบบ (พร้อมทดสอบทันที)":
        teachers_to_process = get_sample_teachers()
        st.info(f"💡 โหลดรายชื่อตัวอย่างมาตรฐานแล้ว **{len(teachers_to_process)} บัญชี** (พร้อมกดปุ่มเริ่มทำงานด้านล่างได้ทันที)")

    elif input_method == "📁 อัปโหลดไฟล์ teachers.csv":
        uploaded_csv = st.file_uploader("เลือกไฟล์ teachers.csv", type=["csv"], key="csv_upload")
        if uploaded_csv is not None:
            content = uploaded_csv.getvalue().decode("utf-8-sig", errors="replace")
            teachers_to_process = parse_teachers_csv(content)
            if not teachers_to_process:
                teachers_to_process = parse_teachers_raw_text(content)
            if teachers_to_process:
                st.success(f"✅ ตรวจพบข้อมูลครูในไฟล์ทั้งหมด **{len(teachers_to_process)} บัญชี**")
            else:
                st.warning("⚠️ ไฟล์ CSV ไม่มีข้อมูล หรือรูปแบบไม่ถูกต้อง (ต้องการหัวคอลัมน์ username,password)")
        else:
            st.caption("กรุณาเลือกไฟล์ CSV จากเครื่องของคุณ หรือดาวน์โหลดแบบฟอร์มเปล่าได้ที่คอลัมน์ขวามือ")

    elif input_method == "✍️ พิมพ์หรือวางข้อความ (Username, Password)":
        st.caption("พิมพ์หรือวางข้อมูลรูปแบบ `username,password` บรรทัดละ 1 บัญชี")
        pasted_text = st.text_area(
            "วางข้อมูลบัญชีครูที่นี่",
            value="ptn101,101\nptn102,102\nptn103,303",
            height=120,
        )
        if pasted_text.strip():
            teachers_to_process = parse_teachers_raw_text(pasted_text)
            if teachers_to_process:
                st.info(f"ตรวจพบบัญชีครูจากข้อความ **{len(teachers_to_process)} บัญชี**")

    # ตัวเลือกจำกัดจำนวนบัญชีเพื่อทดสอบรวดเร็ว
    if teachers_to_process:
        limit_run = st.checkbox("⚡ โหมดทดสอบรวดเร็ว (ดึงเฉพาะ 1-2 บัญชีแรก)", value=False)
        if limit_run:
            teachers_to_process = teachers_to_process[:2]

        df_preview = pd.DataFrame(teachers_to_process)
        with st.expander(f"👁️ ตรวจสอบรายชื่อที่จะประมวลผล ({len(teachers_to_process)} บัญชี)", expanded=False):
            st.dataframe(df_preview, use_container_width=True, hide_index=True)


with col2:
    st.subheader("2️⃣ เทมเพลต Word ปถ.05 (.docx)")
    default_template_path = BASE_DIR / "pt05.docx"

    uploaded_docx = st.file_uploader("อัปโหลดไฟล์เทมเพลตใหม่ (.docx) (ถ้ามี)", type=["docx"])
    if uploaded_docx is not None:
        custom_template_bytes = uploaded_docx.getvalue()
        st.success("✅ ใช้ไฟล์เทมเพลตที่อัปโหลดใหม่")
    elif default_template_path.exists():
        custom_template_bytes = default_template_path.read_bytes()
        st.info("ℹ️ ใช้ไฟล์เทมเพลตมาตรฐานในระบบ (`pt05.docx`)")
    else:
        custom_template_bytes = None
        st.error("⚠️ ไม่พบไฟล์เทมเพลต pt05.docx ในระบบ กรุณาอัปโหลดไฟล์ .docx")

    # ปุ่มดาวน์โหลดไฟล์ตัวอย่าง CSV Template
    sample_csv_data = "username,password\nptn101,101\nptn102,102\n"
    st.download_button(
        "📥 ดาวน์โหลดแบบฟอร์ม teachers.csv เปล่า",
        data=sample_csv_data,
        file_name="teachers_template.csv",
        mime="text/csv",
    )

st.divider()

# -------------------------------------------------------------
# 3️⃣ ปุ่มสั่งประมวลผล
# -------------------------------------------------------------
if teachers_to_process and custom_template_bytes:
    st.success(f"🟢 **ระบบพร้อมทำงาน:** มีรายชื่อครู **{len(teachers_to_process)}** บัญชี • เทมเพลต Word พร้อม • ภาคเรียน {term}/{year}")
    button_label = f"🚀 เริ่มประมวลผลดึงข้อมูล ({len(teachers_to_process)} บัญชี)"
    button_disabled = False
else:
    st.warning("🟡 **ยังไม่พร้อมทำงาน:** กรุณาเลือกวิธีระบุรายชื่อครูในข้อ 1 ด้านบนก่อน")
    button_label = "🚀 เริ่มประมวลผลดึงข้อมูล (กรุณาระบุรายชื่อครูก่อน)"
    button_disabled = True

start_btn = st.button(button_label, type="primary", disabled=button_disabled, use_container_width=True)

if start_btn:
    if not teachers_to_process:
        st.error("กรุณาระบุรายชื่อครูก่อนเริ่มประมวลผล (อัปโหลด CSV หรือพิมพ์ข้อมูล)")
        st.stop()
    if not custom_template_bytes:
        st.error("กรุณาระบุไฟล์เทมเพลต pt05.docx")
        st.stop()


    # สร้าง Working Directory ชั่วคราว
    temp_dir = tempfile.mkdtemp(prefix="pt05_online_")
    temp_dir_path = Path(temp_dir)
    out_dir = temp_dir_path / "output-pt05"
    raw_dir = out_dir / "raw" if do_risk else None
    docx_dir = out_dir / "docx"
    docx_dir.mkdir(parents=True, exist_ok=True)
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)

    template_file = temp_dir_path / "template.docx"
    template_file.write_bytes(custom_template_bytes)

    # เตรียม Progress Bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    log_expander = st.expander("📝 บันทึกการทำงานสด (Live Logs)", expanded=True)
    log_placeholder = log_expander.empty()

    logs = []
    all_records: list[SubjectRecord] = []
    failed: list[str] = []

    total_teachers = len(teachers_to_process)
    start_time = time.time()

    for idx, item in enumerate(teachers_to_process):
        username = item["username"]
        password = item["password"]
        current_pct = int((idx / total_teachers) * 100)
        progress_bar.progress(current_pct)
        status_text.write(f"🔄 กำลังประมวลผล ({idx+1}/{total_teachers}): บัญชี **{username}** ...")

        try:
            records = fetch_teacher(username, password, raw_dir)
            all_records.extend(records)
            teacher_name = records[0].teacher_name if records else username
            docx_name = f"ปถ05_{normalize_filename(username)}_{normalize_filename(teacher_name)}.docx"
            fill_docx(template_file, records, docx_dir / docx_name, term, year, check_date)

            msg = f"✅ [{idx+1}/{total_teachers}] {username} ({teacher_name}): ดึงข้อมูลสำเร็จ {len(records)} รายวิชา"
            logs.append(msg)
        except Exception as exc:
            failed_msg = f"❌ [{idx+1}/{total_teachers}] {username}: ล้มเหลว ({exc})"
            failed.append(failed_msg)
            logs.append(failed_msg)

        log_placeholder.text("\n".join(logs[-15:]))

    # สรุป PT05
    progress_bar.progress(90)
    status_text.write("💾 กำลังสร้างไฟล์สรุป Excel และรายงาน ...")

    summary_excel_path = out_dir / "pt05_summary.xlsx"
    summary_json_path = out_dir / "pt05_summary.json"
    write_summary(all_records, summary_excel_path)
    write_json(all_records, summary_json_path)

    risk_profiles = []
    risk_subjects = []
    if do_risk and raw_dir and raw_dir.exists():
        status_text.write("🧠 กำลังวิเคราะห์ AI นักเรียนกลุ่มเสี่ยงเวลาเรียน (<60% และ <80%) ...")
        try:
            risk_profiles, risk_subjects = analyze_attendance(raw_dir, summary_json_path)
            export_excel(risk_profiles, risk_subjects, out_dir / "student_attendance_risk_summary.xlsx")
            export_html_dashboard(risk_profiles, risk_subjects, out_dir / "attendance_risk_dashboard.html")
            export_risk_json(risk_profiles, risk_subjects, out_dir / "student_attendance_risk_summary.json")
            logs.append(f"🎉 วิเคราะห์เวลาเรียนสำเร็จ: พบนักเรียนกลุ่มเสี่ยงทั้งหมด {len(risk_profiles)} คน")
        except Exception as exc:
            logs.append(f"⚠️ การวิเคราะห์เวลาเรียนผิดพลาด: {exc}")

    progress_bar.progress(100)
    status_text.write("📦 กำลังบีบอัดไฟล์ผลลัพธ์เป็น ZIP ...")

    # รวมไฟล์เป็น ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, _, files in os.walk(out_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(out_dir)
                zip_file.write(file_path, arcname)

    zip_buffer.seek(0)
    elapsed = round(time.time() - start_time, 1)

    # บันทึกลง Session State
    st.session_state.zip_buffer = zip_buffer.getvalue()
    st.session_state.processed_data = {
        "records_count": len(all_records),
        "teachers_count": total_teachers - len(failed),
        "failed_count": len(failed),
        "failed_list": failed,
        "elapsed": elapsed,
        "risk_profiles_count": len(risk_profiles),
        "crit_count": sum(1 for p in risk_profiles if "วิกฤต" in p.risk_level),
        "warn_count": sum(1 for p in risk_profiles if "เฝ้าระวัง" in p.risk_level),
        "has_risk": bool(risk_profiles),
        "summary_excel_bytes": summary_excel_path.read_bytes() if summary_excel_path.exists() else None,
        "risk_excel_bytes": (out_dir / "student_attendance_risk_summary.xlsx").read_bytes() if (out_dir / "student_attendance_risk_summary.xlsx").exists() else None,
        "dashboard_html": (out_dir / "attendance_risk_dashboard.html").read_text(encoding="utf-8") if (out_dir / "attendance_risk_dashboard.html").exists() else None,
    }

    # ลบ Temporary directory เพื่อประหยัดพื้นที่
    try:
        shutil.rmtree(temp_dir_path)
    except Exception:
        pass

    status_text.write(f"🎉 ประมวลผลเสร็จสิ้นสมบูรณ์ใน {elapsed} วินาที!")

# -------------------------------------------------------------
# 4️⃣ แสดงผลลัพธ์และดาวน์โหลด
# -------------------------------------------------------------
if st.session_state.processed_data is not None:
    data = st.session_state.processed_data

    st.success(f"✨ ประมวลผลสำเร็จเรียบร้อยแล้ว (ใช้เวลา {data['elapsed']} วินาที)")

    # Cards สรุปตัวเลข
    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    mcol1.metric("👨‍🏫 ครูที่ดึงข้อมูลสำเร็จ", f"{data['teachers_count']} บัญชี")
    mcol2.metric("📚 จำนวนรายวิชาทั้งหมด", f"{data['records_count']} วิชา")
    mcol3.metric("🚨 เสี่ยงวิกฤต (<60% ขร./มส.)", f"{data['crit_count']} คน")
    mcol4.metric("⚠️ กลุ่มเฝ้าระวัง (60-80%)", f"{data['warn_count']} คน")

    if data["failed_count"] > 0:
        with st.expander(f"⚠️ บัญชีที่เข้าสู่ระบบไม่สำเร็จ ({data['failed_count']} บัญชี)"):
            for f in data["failed_list"]:
                st.write(f)

    st.subheader("📥 ดาวน์โหลดไฟล์ผลลัพธ์")
    dcol1, dcol2, dcol3 = st.columns(3)

    with dcol1:
        st.download_button(
            label="📦 ดาวน์โหลดแพ็กเกจผลลัพธ์ทั้งหมด (.ZIP)",
            data=st.session_state.zip_buffer,
            file_name=f"PT05_Results_{datetime.date.today().strftime('%Y%m%d')}.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )
    with dcol2:
        if data["summary_excel_bytes"]:
            st.download_button(
                label="📊 ดาวน์โหลดเฉพาะ Excel สรุป ปถ.05",
                data=data["summary_excel_bytes"],
                file_name="pt05_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    with dcol3:
        if data["risk_excel_bytes"]:
            st.download_button(
                label="👥 ดาวน์โหลด Excel สรุปนักเรียนกลุ่มเสี่ยง",
                data=data["risk_excel_bytes"],
                file_name="student_attendance_risk_summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    # พรีวิว Dashboard
    if data["dashboard_html"]:
        st.divider()
        st.subheader("📊 แดชบอร์ดสรุปนักเรียนกลุ่มเสี่ยงเวลาเรียนแบบ Interactive")
        components.html(data["dashboard_html"], height=800, scrolling=True)

# -------------------------------------------------------------
# แท็บที่ 2: เลขาฯ AI ประจำโรงเรียน (School AI Secretary)
# -------------------------------------------------------------
with main_tab2:
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #0f766e 0%, #06b6d4 100%); color: white; padding: 20px 24px; border-radius: 14px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 6px 0; color: white;">👩‍💼 เลขาฯ AI ประจำโรงเรียนเปรมติณสูลานนท์</h3>
            <p style="margin: 0; font-size: 14px; color: #ccfbf1;">
                ผู้ช่วยอัจฉริยะสอบถามข้อมูลสดแบบ Real-time: ตารางสอนคุณครู, การเข้าแถวหน้าเสาธง, สถิติการมาเรียน, ตารางเรียนห้อง, นักเรียนเสี่ยง มส.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # แผงตั้งค่า AI
    with st.expander("⚙️ ตั้งค่าระบบ AI และโปรไฟล์ครู (Google Gemini API / Fast Engine)", expanded=False):
        c_set1, c_set2, c_set3 = st.columns([3, 2, 3])
        with c_set1:
            gemini_api_key = st.text_input(
                "🔑 Google Gemini API Key (ไม่บังคับ)",
                type="password",
                value=os.environ.get("GEMINI_API_KEY", ""),
                help="ขอรับฟรี API Key ได้ที่ aistudio.google.com หากเว้นว่างไว้ ระบบจะใช้เอนจินภายในดึงข้อมูลสดให้อัตโนมัติ",
            )
        with c_set2:
            model_choice = st.selectbox(
                "🤖 โมเดล AI (Gemini 3.1+ / 3.7)",
                ["gemini-3.7-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview", "กำหนดเอง (Custom)..."],
                index=0,
                help="Gemini 3.1+ / 3.7 เป็นโมเดลเจเนอเรชันปัจจุบัน (gemini-3.7-flash แนะนำเร็วและแม่นยำที่สุด)",
            )
            if model_choice == "กำหนดเอง (Custom)...":
                gemini_model = st.text_input("ระบุชื่อโมเดล", value="gemini-3.7-flash")
            else:
                gemini_model = model_choice
        with c_set3:
            eng = st.session_state.school_engine
            teacher_opts = [
                f"{t['username']} - {t['name'] or t['username']}" for t in eng.teachers_cache
            ] or ["ptn1617 - กรกฎ รัตนะโช"]
            default_idx = 0
            for idx, opt in enumerate(teacher_opts):
                if "ptn1617" in opt:
                    default_idx = idx
                    break
            chosen_teacher = st.selectbox(
                "👤 คุณครูผู้ใช้งาน (สำหรับคำว่า 'ฉัน')",
                teacher_opts,
                index=default_idx,
                help="เลือกบัญชีคุณครูของคุณ เพื่อให้เลขาฯ AI ทราบว่า 'ฉัน' หรือ 'ผม' คือครูท่านใด",
            )
            selected_user = chosen_teacher.split(" - ")[0].strip() if chosen_teacher else "ptn1617"
        st.caption("💡 **หมายเหตุ:** หากไม่มี API Key หรือ Gemini API มีการขัดข้อง ระบบจะใช้ Fast Engine ดึงข้อมูลสดจากระบบ SSS ให้ทันที 100%")

    # แผงคำถามด่วน (Quick Prompts)
    c_bar1, c_bar2 = st.columns([3, 2])
    with c_bar1:
        st.markdown("##### ⚡ คำถามด่วนที่พบบ่อย (คลิกเพื่อถามทันที)")
    with c_bar2:
        st.caption(f"👤 คุณครูผู้ใช้งาน: **{chosen_teacher}** *(เปลี่ยนได้ที่แผงตั้งค่าด้านบน)*")
    qp1, qp2, qp3, qp4, qp5 = st.columns(5)
    
    selected_prompt = None
    if qp1.button("📅 คาบแรกฉันสอนอะไร", use_container_width=True):
        selected_prompt = "วันนี้คาบแรกฉันสอนวิชาอะไร ม.ไหน"
    if qp2.button("🚩 ม.3/1 ใครขาดแถว", use_container_width=True):
        selected_prompt = "วันนี้ ห้อง ม.3/1 ใครขาดแถวบ้าง"
    if qp3.button("🏫 วันนี้มา ร.ร. กี่คน", use_container_width=True):
        selected_prompt = "วันนี้ มีนักเรียนมาโรงเรียนกี่คน สรุปภาพรวม"
    if qp4.button("⚠️ เด็กเสี่ยง มส.", use_container_width=True):
        selected_prompt = "มีนักเรียนคนไหนที่เสี่ยง มส. บ้าง"
    if qp5.button("📖 ตารางเรียน ม.3/1", use_container_width=True):
        selected_prompt = "ตารางเรียนห้อง ม.3/1 วันนี้"

    st.divider()

    # แสดงประวัติการสนทนา
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.chat_messages:
            role = msg["role"]
            avatar = "👩‍💼" if role == "assistant" else "👤"
            with st.chat_message(role, avatar=avatar):
                st.markdown(msg["content"])

    # ช่องรับข้อความ
    chat_input_text = st.chat_input("พิมพ์คำถามของคุณที่นี่ เช่น วันนี้คาบแรกสอนวิชาอะไร, ห้อง ม.3/1 ใครขาดแถว...")

    prompt_to_process = selected_prompt or chat_input_text

    if prompt_to_process:
        # บันทึกคำถามของ user
        st.session_state.chat_messages.append({"role": "user", "content": prompt_to_process})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt_to_process)

        # ตอบคำถาม
        with st.chat_message("assistant", avatar="👩‍💼"):
            with st.spinner("🤖 เลขาฯ AI กำลังค้นหาข้อมูลสดจากระบบโรงเรียน..."):
                reply = st.session_state.school_engine.answer_query(
                    query=prompt_to_process,
                    api_key=gemini_api_key,
                    model_name=gemini_model,
                    chat_history=st.session_state.chat_messages,
                    current_user=selected_user,
                )
                st.markdown(reply)
                st.session_state.chat_messages.append({"role": "assistant", "content": reply})
        st.rerun()

    # ปุ่มล้างแชท
    col_clear, _ = st.columns([1, 5])
    with col_clear:
        if st.button("🗑️ ล้างประวัติแชท", use_container_width=True):
            st.session_state.chat_messages = [
                {
                    "role": "assistant",
                    "content": "สวัสดีครับคุณครู! ยินดีต้อนรับสู่ระบบเลขาฯ AI ประจำโรงเรียนเปรมติณสูลานนท์ สอบถามข้อมูลสดได้ทันทีครับ 👩‍💼",
                }
            ]
            st.rerun()

# -------------------------------------------------------------
# แท็บที่ 3: คู่มือเชื่อมต่อ ChatGPT Custom GPTs & API
# -------------------------------------------------------------
with main_tab3:
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #1e1b4b 0%, #4338ca 100%); color: white; padding: 20px 24px; border-radius: 14px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 6px 0; color: white;">🔌 เชื่อมต่อ ChatGPT Custom GPT & External AI Agents</h3>
            <p style="margin: 0; font-size: 14px; color: #c7d2fe;">
                นำระบบสารสนเทศโรงเรียนเปรมติณสูลานนท์ไปเชื่อมต่อเป็น Custom GPT บนแอป ChatGPT ในมือถือ หรือใช้งานผ่าน REST API
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("🚀 วิธีติดตั้ง Custom GPT ใน ChatGPT (4 ขั้นตอนง่ายๆ)")

    step1, step2 = st.columns(2)
    with step1:
        st.markdown(
            """
            #### ขั้นตอนที่ 1: เปิดรัน API Server
            ดับเบิ้ลคลิกไฟล์ `run_api.bat` ในโฟลเดอร์โปรเจกต์ หรือรันคำสั่ง:
            ```bash
            python -m uvicorn api:app --host 0.0.0.0 --port 8000
            ```
            ระบบจะเปิด REST API Service ที่พอร์ต `8000`
            """
        )
        st.markdown(
            """
            #### ขั้นตอนที่ 2: สร้าง Public URL (Tunnel)
            เพื่อให้ ChatGPT บนเซิร์ฟเวอร์ OpenAI เข้าถึงเครื่องเราได้ แนะนำให้ใช้ **Cloudflare Tunnel** (ฟรี ไม่ต้องลงทะเบียน):
            ```bash
            cloudflared tunnel --url http://localhost:8000
            ```
            จะได้ URL เช่น `https://xxxx-xxxx.trycloudflare.com`
            """
        )

    with step2:
        st.markdown(
            """
            #### ขั้นตอนที่ 3: สร้าง Custom GPT ใน ChatGPT
            1. เข้าเว็บ [chatgpt.com](https://chatgpt.com) -> เลือก **Explore GPTs** -> **Create a GPT**
            2. ไปที่แท็บ **Configure** ตั้งชื่อ เช่น *'เลขาฯ ร.ร.เปรมติณสูลานนท์'*
            3. เลื่อนลงมาด้านล่างสุด กด **Create new action**
            4. ในช่อง **Schema** ให้นำเนื้อหาจากไฟล์ `openapi.yaml` ด้านล่างไปวาง
            5. เปลี่ยน URL ในส่วน `servers:` เป็น URL Cloudflare Tunnel ของคุณ
            """
        )
        st.markdown(
            """
            #### ขั้นตอนที่ 4: เริ่มใช้งานในแอป ChatGPT บนมือถือ!
            กดบันทึก (Save) แล้วเปิดแอป ChatGPT บนโทรศัพท์ สามารถพิมพ์แชท หรือกดปุ่มหูฟังเพื่อคุยด้วยเสียง (Voice Mode) ถามข้อมูลโรงเรียนได้ทันที!
            """
        )

    st.divider()

    st.subheader("📄 ไฟล์ OpenAPI Specification (Schema สำหรับ ChatGPT)")
    st.caption("คัดลอกข้อความ YAML ด้านล่างนี้ไปวางในส่วน Schema ของ ChatGPT Actions:")

    openapi_path = BASE_DIR / "openapi.yaml"
    openapi_content = ""
    if openapi_path.exists():
        openapi_content = openapi_path.read_text(encoding="utf-8")
    else:
        # Fallback สร้าง schema จาก api.py
        try:
            from api import get_openapi_yaml
            openapi_content = get_openapi_yaml()
        except Exception:
            openapi_content = "# กรุณารัน api.py เพื่อดู openapi.yaml"

    st.code(openapi_content, language="yaml")

    st.subheader("💡 ตัวอย่าง Instructions สำหรับใส่ใน Custom GPT")
    instructions_sample = (
        "คุณคือ 'เลขาฯ AI ประจำโรงเรียนเปรมติณสูลานนท์' ตอบคำถามคุณครูและผู้บริหารอย่างสุภาพและเป็นมิตร\n"
        "เมื่อผู้ใช้ถามเกี่ยวกับ:\n"
        "1. ตารางสอน หรือถามว่าคาบแรกสอนวิชาอะไร -> ให้เรียก getTeacherSchedule\n"
        "2. การเข้าแถวหน้าเสาธง หรือถามว่าห้องไหนใครขาดแถว -> ให้เรียก getMorningAssemblyAbsent\n"
        "3. สถิติการมาเรียนรวมทั้งโรงเรียน หรือถามว่าวันนี้มาเรียนกี่คน -> ให้เรียก getDailyAttendanceSummary\n"
        "4. ตารางเรียนห้อง -> ให้เรียก getClassSchedule\n"
        "5. นักเรียนเสี่ยง มส. -> ให้เรียก getAttendanceRiskStudents\n"
        "ตอบกลับเป็นภาษาไทยพร้อมจัดรูปแบบ Markdown สวยงามเสมอ"
    )
    st.text_area("คัดลอกข้อความนี้ไปใส่ในช่อง Instructions ของ ChatGPT:", value=instructions_sample, height=180)

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #94a3b8; font-size: 13px;'>"
    "ระบบดึงข้อมูลและตรวจ ปถ.05 อัตโนมัติ • พร้อมระบบเลขาฯ AI & ChatGPT Assistant • โรงเรียนเปรมติณสูลานนท์"
    "</div>",
    unsafe_allow_html=True,
)

