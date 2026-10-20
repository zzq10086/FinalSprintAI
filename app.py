"""FinalSprint AI 第一阶段入口。

当前版本完成：
- 创建课程/复习任务并保存到本地
- 选择当前复习任务
- 上传 TXT / PDF 并提取文字（保留 PDF 页码）
- 查看已保存资料和空页面提示
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.document_parser import extract_text
from src.storage import (
    StorageError,
    add_course,
    get_course,
    load_courses,
    load_materials,
    save_material,
)

st.set_page_config(
    page_title="FinalSprint AI",
    page_icon="📚",
    layout="wide",
)

st.title("📚 FinalSprint AI")
st.caption("大学生期末冲刺 AI 学习平台 · 第一阶段：课程任务与资料提取")

try:
    courses = load_courses()
except StorageError as exc:
    st.error(f"读取本地数据失败：{exc}")
    st.stop()

# ---------------------------------------------------------------------------
# 1. 创建复习任务
# ---------------------------------------------------------------------------
with st.expander("➕ 创建新的复习任务", expanded=not courses):
    with st.form("create_course_form", clear_on_submit=True):
        course_name = st.text_input(
            "课程名称",
            placeholder="例如：计算机网络",
            max_chars=60,
        )
        col_date, col_minutes = st.columns(2)
        exam_date = col_date.date_input(
            "考试日期",
            value=date.today(),
            min_value=date.today(),
        )
        daily_minutes = col_minutes.select_slider(
            "每天可用于复习的时间",
            options=[30, 60, 90, 120, 180, 240],
            value=60,
            format_func=lambda minutes: f"{minutes} 分钟",
        )
        submitted = st.form_submit_button("创建复习任务", type="primary")

    if submitted:
        try:
            course = add_course(course_name, exam_date, daily_minutes)
        except StorageError as exc:
            st.error(str(exc))
        else:
            st.session_state["active_course_id"] = course["id"]
            st.success(f"已创建课程：{course['name']}")
            st.rerun()

if not courses:
    st.info("还没有复习任务。请先在上方填写课程名称并创建任务。")
    st.stop()

# ---------------------------------------------------------------------------
# 2. 选择当前复习任务
# ---------------------------------------------------------------------------
courses_by_id = {course["id"]: course for course in courses}
course_ids = [course["id"] for course in courses]

if st.session_state.get("active_course_id") not in course_ids:
    st.session_state["active_course_id"] = course_ids[0]


def format_course(course_id: str) -> str:
    course = courses_by_id[course_id]
    return f"{course['name']}（考试：{course['exam_date']}）"


active_id = st.selectbox(
    "当前复习任务",
    options=course_ids,
    format_func=format_course,
    key="active_course_id",
)

try:
    active_course = get_course(active_id)
    materials = load_materials(active_id)
except StorageError as exc:
    st.error(f"读取课程资料失败：{exc}")
    st.stop()

exam_date = date.fromisoformat(active_course["exam_date"])
days_left = (exam_date - date.today()).days

st.subheader(f"📘 {active_course['name']}")

metric_exam, metric_minutes, metric_materials = st.columns(3)
metric_exam.metric("考试日期", active_course["exam_date"])
metric_minutes.metric("每日复习", f"{active_course['daily_minutes']} 分钟")
metric_materials.metric("已保存资料", f"{len(materials)} 份")

if days_left < 0:
    st.error(f"考试日期已过去 {abs(days_left)} 天，请检查日期是否正确。")
elif days_left == 0:
    st.warning("今天就是考试日，建议只做轻度回顾，保证休息。")
elif days_left <= 7:
    st.info(f"距离考试还有 {days_left} 天，进入冲刺阶段。")
else:
    st.info(f"距离考试还有 {days_left} 天，可以按计划稳步复习。")

st.divider()

# ---------------------------------------------------------------------------
# 3. 上传并提取资料
# ---------------------------------------------------------------------------
st.subheader("📄 上传课程资料")
st.caption("支持 TXT 和可选中文字的 PDF，单个文件不超过 20 MB。扫描版 PDF 需要 OCR。")

uploaded_file = st.file_uploader(
    "选择课件、讲义或笔记",
    type=["txt", "pdf"],
    key=f"uploader_{active_id}",
)

if uploaded_file is not None:
    st.caption(f"已选择：{uploaded_file.name}（{uploaded_file.size / 1024:.1f} KB）")

    if st.button("提取并保存资料", type="primary", key=f"extract_{active_id}"):
        try:
            pages = extract_text(uploaded_file.name, uploaded_file.getvalue())
            material = save_material(active_id, uploaded_file.name, pages)
        except (ValueError, StorageError) as exc:
            st.error(str(exc))
        else:
            empty_pages = [page["page"] for page in pages if not page["text"]]
            st.success(
                f"提取成功：{material['page_count']} 页，"
                f"{material['char_count']} 个字符，已保存到本地。"
            )
            if empty_pages:
                page_list = "、".join(str(number) for number in empty_pages)
                st.warning(
                    f"第 {page_list} 页没有提取到文字，"
                    "可能是图片页或扫描页，建议结合原始资料核对。"
                )
            # 重新读取，让下方资料列表立即包含刚保存的内容。
            materials = load_materials(active_id)

st.divider()

# ---------------------------------------------------------------------------
# 4. 查看已保存资料
# ---------------------------------------------------------------------------
st.subheader("🗂️ 已保存资料")

if not materials:
    st.info("这门课程还没有资料，请先上传 TXT 或 PDF。")
else:
    for material in materials:
        title = (
            f"{material['filename']} · "
            f"{material['page_count']} 页 · "
            f"{material['char_count']} 字符"
        )
        with st.expander(title):
            st.caption(f"上传时间：{material['uploaded_at']}")

            empty_pages = [
                page["page"] for page in material["pages"] if not page["text"]
            ]
            if empty_pages:
                page_list = "、".join(str(number) for number in empty_pages)
                st.warning(f"第 {page_list} 页没有提取到文字。")

            for page in material["pages"]:
                st.markdown(f"**第 {page['page']} 页**")
                if page["text"]:
                    preview = page["text"][:2000]
                    st.text(preview)
                    if len(page["text"]) > len(preview):
                        st.caption(
                            f"本页共 {len(page['text'])} 个字符，仅显示前 2000 个字符。"
                        )
                else:
                    st.text("（本页没有提取到文字）")

st.divider()
st.caption(
    "当前版本 v0.1：课程任务、TXT/PDF 文本提取与本地保存。"
    "AI 考点提炼、复习计划、练习题将在后续阶段加入。"
)
