"""Streamlit 页面级冒烟测试。

AppTest 会在当前进程中真正执行 app.py，
因此可以发现导入错误、页面逻辑错误和会话状态问题。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.storage as storage

APP_PATH = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture
def app(tmp_path, monkeypatch):
    # 把页面使用的默认数据目录指向临时目录，避免污染真实 data/。
    monkeypatch.setattr(storage, "DEFAULT_DATA_DIR", tmp_path)
    return AppTest.from_file(APP_PATH, default_timeout=15)


def test_app_starts_without_exception(app):
    app.run()

    assert not app.exception
    assert any("FinalSprint AI" in title.value for title in app.title)


def test_app_creates_course(app):
    app.run()

    app.text_input[0].input("计算机网络")
    app.button[0].click().run()

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

    app.button[0].click().run()

    assert not app.exception
    assert storage.load_courses() == []
    assert any("课程名称不能为空" in error.value for error in app.error)


def test_app_uploads_and_saves_txt_material(app):
    app.run()

    app.text_input[0].input("操作系统")
    app.button[0].click().run()

    app.file_uploader[0].upload(
        "chapter1.txt",
        "进程与线程\n内存管理".encode("utf-8"),
        "text/plain",
    )
    app.run()

    extract_button = next(
        button for button in app.button if "提取并保存资料" in button.label
    )
    extract_button.click().run()

    assert not app.exception
    course = storage.load_courses()[0]
    materials = storage.load_materials(course["id"])
    assert len(materials) == 1
    assert materials[0]["filename"] == "chapter1.txt"
    assert materials[0]["pages"] == [{"page": 1, "text": "进程与线程\n内存管理"}]
    assert any("提取成功" in message.value for message in app.success)
