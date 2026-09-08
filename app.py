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

# -------------------------------------------------------------
# หน้าหลัก: แท็บป้อนข้อมูลครูและเทมเพลต
# -------------------------------------------------------------
col1, col2 = st.columns([3, 2])

with col1:
    st.subheader("1️⃣ กำหนดรายชื่อครูที่ต้องการตรวจ")
    tab_upload, tab_paste, tab_sample = st.tabs(["📁 อัปโหลดไฟล์ CSV", "✍️ พิมพ์หรือวางข้อความ", "🧪 ใช้ข้อมูลตัวอย่าง"])

    teachers_to_process: list[dict[str, str]] = []

    with tab_upload:
        uploaded_csv = st.file_uploader("เลือกไฟล์ teachers.csv", type=["csv"], key="csv_upload")
        if uploaded_csv is not None:
            content = uploaded_csv.getvalue().decode("utf-8-sig", errors="replace")
            teachers_to_process = parse_teachers_csv(content)
            if not teachers_to_process:
                teachers_to_process = parse_teachers_raw_text(content)
            st.success(f"ตรวจพบข้อมูลครูทั้งหมด {len(teachers_to_process)} บัญชี")

    with tab_paste:
        st.caption("รูปแบบ: `username,password` บรรทัดละ 1 บัญชี (เช่น `ptn101,101`)")
        pasted_text = st.text_area(
            "วางข้อมูลบัญชีครูที่นี่",
            height=130,
            placeholder="ptn101,101\nptn102,102\nptn103,103",
        )
        if pasted_text.strip():
            parsed = parse_teachers_raw_text(pasted_text)
            if parsed:
                teachers_to_process = parsed
                st.info(f"ตรวจพบบัญชีครูจากข้อความ {len(teachers_to_process)} บัญชี")

    with tab_sample:
        st.write("กดปุ่มเพื่อโหลดบัญชีครูตัวอย่าง (Sample) สำหรับทดสอบระบบ")
        if st.button("โหลดบัญชีตัวอย่าง (Sample Teachers)"):
            sample_file = TOOLS_DIR / "teachers.sample.csv"
            if sample_file.exists():
                teachers_to_process = parse_teachers_csv(sample_file.read_text(encoding="utf-8-sig", errors="replace"))
                st.success(f"โหลดข้อมูลตัวอย่างแล้ว {len(teachers_to_process)} บัญชี")
            else:
                st.warning("ไม่พบไฟล์ teachers.sample.csv")

    if teachers_to_process:
        df_preview = pd.DataFrame(teachers_to_process)
        with st.expander(f"👁️ ดูรายชื่อครูที่จะประมวลผล ({len(teachers_to_process)} คน)", expanded=False):
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
start_btn = st.button("🚀 เริ่มประมวลผลดึงข้อมูล (Start Processing)", type="primary", use_container_width=True)

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

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #94a3b8; font-size: 13px;'>"
    "ระบบดึงข้อมูลและตรวจ ปถ.05 อัตโนมัติ • พร้อม Deploy บน Streamlit Cloud & GitHub • พัฒนาโดย DeepMind Antigravity"
    "</div>",
    unsafe_allow_html=True,
)
