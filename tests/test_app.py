"""Streamlit 页面级冒烟测试。

AppTest 会在当前进程中真正执行 app.py，
因此可以发现导入错误、页面逻辑错误和会话状态问题。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.ai_service as ai_service
import src.settings as settings
import src.storage as storage

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"

AI_ENV_NAMES = (
    "AI_PROVIDER",
    "AI_BASE_URL",
    "AI_MODEL",
    "AI_API_KEY",
    "AI_TIMEOUT",
    "AI_MAX_CHUNKS",
    "AI_CHUNK_SIZE",
)


@pytest.fixture
def app(tmp_path, monkeypatch):
    # 把页面使用的默认数据目录指向临时目录，避免污染真实 data/。
    monkeypatch.setattr(storage, "DEFAULT_DATA_DIR", tmp_path)
    # 隔离真实 .env，测试不会读取或调用真实 API。
    monkeypatch.setattr(settings, "ENV_PATH", tmp_path / "missing.env")
    for name in AI_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    return AppTest.from_file(APP_PATH, default_timeout=30)


def click_button(app, label: str):
    button = next(item for item in app.button if label in item.label)
    button.click().run()


def enable_fake_ai(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "测试服务")
    monkeypatch.setenv("AI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("AI_MODEL", "test-model")
    monkeypatch.setenv("AI_API_KEY", "test-key")


def fake_chat_response(title: str = "进程与线程") -> dict:
    content = json.dumps(
        {
            "key_points": [
                {
                    "title": title,
                    "explanation": "这是测试生成的考点解释。",
                    "importance": 5,
                    "difficulty": 3,
                    "keywords": ["调度", "并发"],
                    "source_pages": [1],
                }
            ]
        },
        ensure_ascii=False,
    )
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
        },
    }


def test_app_starts_without_exception(app):
    app.run()

    assert not app.exception
    assert any("FinalSprint AI" in title.value for title in app.title)


def test_app_creates_course(app):
    app.run()

    app.text_input[0].input("计算机网络")
    click_button(app, "创建复习任务")

    assert not app.exception
    courses = storage.load_courses()
    assert len(courses) == 1
    assert courses[0]["name"] == "计算机网络"
    assert courses[0]["daily_minutes"] == 60

    # 创建成功后，页面应出现课程标题和资料上传区域。
    assert any("计算机网络" in header.value for header in app.subheader)
    assert any("上传课程资料" in header.value for header in app.subheader)


def test_app_rejects_empty_course_name(app):
    app.run()

    click_button(app, "创建复习任务")

    assert not app.exception
    assert storage.load_courses() == []
    assert any("课程名称不能为空" in error.value for error in app.error)


def test_app_creates_course_with_selected_future_date(app):
    target = date.today() + timedelta(days=60)

    app.run()
    app.text_input[0].input("线性代数")
    app.date_input[0].set_value(target).run()
    click_button(app, "创建复习任务")

    assert not app.exception
    course = storage.load_courses()[0]
    assert course["exam_date"] == target.isoformat()


def test_app_updates_existing_course_date(app):
    target = date.today() + timedelta(days=90)

    app.run()
    app.text_input[0].input("线性代数")
    click_button(app, "创建复习任务")

    edit_date = next(
        item for item in app.date_input if "新的考试日期" in item.label
    )
    edit_date.set_value(target).run()
    click_button(app, "保存修改")

    assert not app.exception
    course = storage.load_courses()[0]
    assert course["exam_date"] == target.isoformat()


def test_app_uploads_and_saves_txt_material(app):
    app.run()

    app.text_input[0].input("操作系统")
    click_button(app, "创建复习任务")

    app.file_uploader[0].upload(
        "chapter1.txt",
        "进程与线程\n内存管理".encode("utf-8"),
        "text/plain",
    )
    app.run()

    click_button(app, "提取并保存资料")

    assert not app.exception
    course = storage.load_courses()[0]
    materials = storage.load_materials(course["id"])
    assert len(materials) == 1
    assert materials[0]["filename"] == "chapter1.txt"
    assert materials[0]["pages"] == [{"page": 1, "text": "进程与线程\n内存管理"}]
    assert any("提取成功" in message.value for message in app.success)


def test_app_shows_ai_not_configured(app):
    app.run()

    assert any("AI 尚未配置" in warning.value for warning in app.warning)


def test_app_shows_ai_configured_without_calling_api(app, monkeypatch):
    enable_fake_ai(monkeypatch)

    app.run()

    assert not app.exception
    assert any("已配置：测试服务" in message.value for message in app.success)


def test_app_analyzes_material_with_fake_api(app, monkeypatch):
    enable_fake_ai(monkeypatch)
    monkeypatch.setattr(
        ai_service.requests,
        "post",
        lambda *args, **kwargs: type(
            "FakeResponse",
            (),
            {
                "status_code": 200,
                "text": "",
                "json": lambda self: fake_chat_response(),
            },
        )(),
    )

    app.run()
    app.text_input[0].input("操作系统")
    click_button(app, "创建复习任务")

    app.file_uploader[0].upload(
        "chapter1.txt",
        "进程与线程\n内存管理".encode("utf-8"),
        "text/plain",
    )
    app.run()
    click_button(app, "提取并保存资料")
    click_button(app, "AI 提炼考点")

    assert not app.exception
    course = storage.load_courses()[0]
    material = storage.load_materials(course["id"])[0]
    analysis = storage.load_analysis(course["id"], material["id"])

    assert analysis is not None
    assert analysis["key_points"][0]["title"] == "进程与线程"
    assert analysis["usage"]["total_tokens"] == 30
    assert any("已提炼" in message.value for message in app.success)
    assert any("进程与线程" in item.value for item in app.markdown)
