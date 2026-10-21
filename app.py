"""FinalSprint AI 入口。

当前版本（v0.2）完成：
- 创建课程/复习任务并保存到本地
- 上传 TXT / PDF 并提取文字（保留 PDF 页码）
- 使用 OpenAI 兼容接口提炼考点、关键词和解释
- 保留来源页码，展示考点重要度和难度
- 本地保存分析结果，避免重复调用 API
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.ai_service import (
    AIServiceError,
    analyze_material,
    check_ai_connection,
)
from src.document_parser import extract_text
from src.settings import AIConfigError, load_ai_settings
from src.storage import (
    StorageError,
    add_course,
    get_course,
    load_analysis,
    load_courses,
    load_materials,
    save_analysis,
    save_material,
    update_course,
)

st.set_page_config(
    page_title="FinalSprint AI",
    page_icon="📚",
    layout="wide",
)

st.title("📚 FinalSprint AI")
st.caption("大学生期末冲刺 AI 学习平台 · 第二阶段：AI 考点提炼")


def safe_score(value: object, default: int = 3) -> int:
    if isinstance(value, bool):
        return default
    try:
        score = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(5, score))


def render_analysis(analysis: dict, material: dict) -> None:
    """展示一份资料的 AI 考点分析。"""

    st.markdown("#### 🤖 AI 考点提炼")
    st.warning(
        "AI 生成内容可能存在错误或遗漏，请结合原始课件和教材核对后再用于复习。"
    )

    if analysis.get("truncated"):
        st.warning(
            f"资料较长，本次只分析了前 "
            f"{analysis.get('analyzed_chunks', 0)} / "
            f"{analysis.get('chunk_count', 0)} 段。"
            "可以在 .env 中调大 AI_MAX_CHUNKS 后重新分析。"
        )

    points = analysis.get("key_points") or []
    st.caption(
        f"模型：{analysis.get('model', '未知')} · "
        f"分析时间：{analysis.get('analyzed_at', '未知')} · "
        f"考点：{len(points)} 个"
    )

    if not points:
        st.info("没有可显示的考点。")
        return

    for index, point in enumerate(points, start=1):
        importance = safe_score(point.get("importance"))
        difficulty = safe_score(point.get("difficulty"))
        stars = "★" * importance + "☆" * (5 - importance)
        keywords = "、".join(point.get("keywords") or []) or "未标注"
        pages = point.get("source_pages") or []

        with st.container(border=True):
            st.markdown(f"**{index}. {point.get('title', '未命名考点')}**")
            st.caption(
                f"重要度：{stars}（{importance}/5） · "
                f"难度：{difficulty}/5 · 关键词：{keywords}"
            )
            st.write(point.get("explanation", ""))

            if pages:
                estimated = (
                    "（按分段推断）"
                    if point.get("source_pages_estimated")
                    else ""
                )
                page_text = "、".join(str(page) for page in pages)
                st.caption(f"来源页码：第 {page_text} 页{estimated}")

                with st.expander(f"查看来源页原文（考点 {index}）"):
                    for page_number in pages:
                        original = next(
                            (
                                page.get("text", "")
                                for page in material.get("pages", [])
                                if page.get("page") == page_number
                            ),
                            "",
                        )
                        st.markdown(f"**第 {page_number} 页**")
                        if original:
                            st.text(original[:800])
                            if len(original) > 800:
                                st.caption("仅显示前 800 个字符。")
                        else:
                            st.text("（本页没有提取到文字）")
            else:
                st.caption("来源页码：模型未标注")

    usage = analysis.get("usage") or {}
    if usage.get("total_tokens"):
        st.caption(
            f"本次消耗 tokens：{usage.get('total_tokens')}"
            f"（输入 {usage.get('prompt_tokens', '-')} / "
            f"输出 {usage.get('completion_tokens', '-')}）"
        )


try:
    ai_settings = load_ai_settings()
    ai_config_error = None
except AIConfigError as exc:
    ai_settings = None
    ai_config_error = str(exc)

with st.sidebar:
    st.header("🤖 AI 状态")

    if ai_config_error:
        st.error(ai_config_error)
    elif ai_settings:
        st.success(f"已配置：{ai_settings.provider}")
        st.caption(f"模型：{ai_settings.model}")
        st.caption(
            f"分段：约 {ai_settings.chunk_size} 字/段，"
            f"最多 {ai_settings.max_chunks} 段"
        )

        if st.button("测试 AI 连接", key="test_ai_connection"):
            with st.spinner("正在测试连接..."):
                try:
                    reply = check_ai_connection(ai_settings)
                except (AIServiceError, AIConfigError) as exc:
                    st.error(str(exc))
                else:
                    st.success(f"连接成功：{reply[:60]}")

        st.caption("密钥只从本地 .env 或系统环境变量读取，不会显示或上传。")
    else:
        st.warning("AI 尚未配置")
        st.caption(
            "复制 .env.example 为 .env，填写 AI_API_KEY 后刷新页面。"
            "未配置时，资料上传、提取和查看仍可正常使用。"
        )

    st.divider()
    st.caption(
        "隐私提示：点击 AI 分析后，当前资料文本会发送给上述模型服务；"
        "不会发送其他课程、账号信息或本地文件路径。"
    )

try:
    courses = load_courses()
except StorageError as exc:
    st.error(f"读取本地数据失败：{exc}")
    st.stop()

# ---------------------------------------------------------------------------
# 1. 创建复习任务
# ---------------------------------------------------------------------------
# 注意：不要把 date_input 放进 st.form。
# Streamlit 的表单会缓存组件值，日期跨月选择时可能提交旧日期。
if st.session_state.pop("reset_create_course_form", False):
    st.session_state["new_course_name"] = ""
    st.session_state["new_exam_date"] = date.today()
    st.session_state["new_daily_minutes"] = 60

with st.expander("➕ 创建新的复习任务", expanded=not courses):
    course_name = st.text_input(
        "课程名称",
        placeholder="例如：计算机网络",
        max_chars=60,
        key="new_course_name",
    )
    col_date, col_minutes = st.columns(2)
    exam_date = col_date.date_input(
        "考试日期",
        value=date.today(),
        min_value=date.today(),
        key="new_exam_date",
    )
    daily_minutes = col_minutes.select_slider(
        "每天可用于复习的时间",
        options=[30, 60, 90, 120, 180, 240],
        value=60,
        format_func=lambda minutes: f"{minutes} 分钟",
        key="new_daily_minutes",
    )

    if st.button("创建复习任务", type="primary", key="create_course_button"):
        try:
            course = add_course(course_name, exam_date, daily_minutes)
        except StorageError as exc:
            st.error(str(exc))
        else:
            st.session_state["active_course_id"] = course["id"]
            st.session_state["reset_create_course_form"] = True
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

with st.expander("✏️ 修改当前课程的考试日期 / 每日复习时间"):
    edit_date = st.date_input(
        "新的考试日期",
        value=exam_date,
        min_value=min(exam_date, date.today()),
        key=f"edit_exam_date_{active_id}",
    )
    minute_options = sorted(
        {30, 60, 90, 120, 180, 240, active_course["daily_minutes"]}
    )
    edit_minutes = st.selectbox(
        "新的每日复习时间",
        options=minute_options,
        index=minute_options.index(active_course["daily_minutes"]),
        format_func=lambda minutes: f"{minutes} 分钟",
        key=f"edit_daily_minutes_{active_id}",
    )

    if st.button("保存修改", key=f"save_course_{active_id}"):
        try:
            update_course(
                active_id,
                exam_date=edit_date,
                daily_minutes=edit_minutes,
            )
        except StorageError as exc:
            st.error(str(exc))
        else:
            st.success("已更新考试日期和每日复习时间。")
            st.rerun()

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
# 4. 查看资料并提炼考点
# ---------------------------------------------------------------------------
st.subheader("🗂️ 资料与 AI 考点")

if not materials:
    st.info("这门课程还没有资料，请先上传 TXT 或 PDF。")
else:
    for material in materials:
        try:
            existing_analysis = load_analysis(active_id, material["id"])
        except StorageError as exc:
            st.error(f"读取分析结果失败：{exc}")
            existing_analysis = None

        analysis_to_show = existing_analysis

        with st.container(border=True):
            st.markdown(f"**{material['filename']}**")
            st.caption(
                f"上传时间：{material['uploaded_at']} · "
                f"{material['page_count']} 页 · "
                f"{material['char_count']} 字符"
            )

            empty_pages = [
                page["page"] for page in material["pages"] if not page["text"]
            ]
            if empty_pages:
                page_list = "、".join(str(number) for number in empty_pages)
                st.warning(f"第 {page_list} 页没有提取到文字。")

            if ai_settings:
                if existing_analysis:
                    st.caption(
                        f"已有分析：{existing_analysis.get('analyzed_at', '未知')} · "
                        f"模型 {existing_analysis.get('model', '未知')} · "
                        f"{len(existing_analysis.get('key_points') or [])} 个考点"
                    )
                    analyze_label = "重新分析（会再次调用 API）"
                else:
                    analyze_label = "AI 提炼考点"

                if st.button(
                    analyze_label,
                    key=f"analyze_{material['id']}",
                ):
                    progress = st.progress(0.0, text="准备分析...")

                    def on_progress(
                        completed: int,
                        total: int,
                        pages: tuple[int, ...],
                    ) -> None:
                        page_text = "、".join(str(page) for page in pages)
                        progress.progress(
                            completed / total,
                            text=(
                                f"正在分析第 {completed + 1}/{total} 段"
                                f"（第 {page_text} 页）..."
                            ),
                        )

                    try:
                        analysis_to_show = analyze_material(
                            material["pages"],
                            ai_settings,
                            progress_callback=on_progress,
                        )
                    except AIServiceError as exc:
                        progress.empty()
                        st.error(str(exc))
                        analysis_to_show = existing_analysis
                    else:
                        progress.progress(1.0, text="分析完成")
                        try:
                            save_analysis(
                                active_id,
                                material["id"],
                                analysis_to_show,
                            )
                        except StorageError as exc:
                            st.warning(f"分析完成，但保存失败：{exc}")
                        else:
                            st.success(
                                f"已提炼 {len(analysis_to_show['key_points'])} "
                                "个考点并保存到本地。"
                            )

                st.caption(
                    f"将按约 {ai_settings.chunk_size} 字分段，"
                    f"最多分析 {ai_settings.max_chunks} 段；"
                    "超出部分会明确提示。"
                )
            else:
                st.caption(
                    "配置 AI 后可在这里提炼考点；"
                    "当前资料上传、提取和查看功能仍可正常使用。"
                )

            if analysis_to_show:
                render_analysis(analysis_to_show, material)

            with st.expander(
                f"查看提取原文（{material['page_count']} 页）"
            ):
                for page in material["pages"]:
                    st.markdown(f"**第 {page['page']} 页**")
                    if page["text"]:
                        preview = page["text"][:2000]
                        st.text(preview)
                        if len(page["text"]) > len(preview):
                            st.caption(
                                f"本页共 {len(page['text'])} 个字符，"
                                "仅显示前 2000 个字符。"
                            )
                    else:
                        st.text("（本页没有提取到文字）")

st.divider()
st.caption(
    "当前版本 v0.2.1：课程任务、资料提取、AI 考点提炼与本地保存。"
    "复习计划、练习题和错题本将在后续阶段加入。"
)
