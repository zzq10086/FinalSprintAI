"""本地 JSON 存储测试。"""

from __future__ import annotations

import json
from datetime import date

import pytest

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


def test_load_courses_returns_empty_when_file_missing(tmp_path):
    assert load_courses(tmp_path) == []


def test_add_and_load_course(tmp_path):
    course = add_course(
        "计算机网络",
        date(2026, 12, 20),
        daily_minutes=90,
        data_dir=tmp_path,
    )

    assert len(course["id"]) == 32
    assert course["name"] == "计算机网络"
    assert course["exam_date"] == "2026-12-20"
    assert course["daily_minutes"] == 90

    courses = load_courses(tmp_path)
    assert courses == [course]

    stored = json.loads((tmp_path / "courses.json").read_text(encoding="utf-8"))
    assert stored[0]["id"] == course["id"]


def test_course_name_is_trimmed(tmp_path):
    course = add_course("  高等数学  ", "2026-12-20", 60, data_dir=tmp_path)

    assert course["name"] == "高等数学"


@pytest.mark.parametrize("name", ["", "   ", "\n\t"])
def test_empty_course_name_rejected(tmp_path, name):
    with pytest.raises(StorageError, match="课程名称不能为空"):
        add_course(name, "2026-12-20", 60, data_dir=tmp_path)


def test_invalid_exam_date_rejected(tmp_path):
    with pytest.raises(StorageError, match="YYYY-MM-DD"):
        add_course("线性代数", "2026/12/20", 60, data_dir=tmp_path)


@pytest.mark.parametrize("minutes", [0, -30, 1441, "abc", True])
def test_invalid_daily_minutes_rejected(tmp_path, minutes):
    with pytest.raises(StorageError, match="每日复习时间"):
        add_course("线性代数", "2026-12-20", minutes, data_dir=tmp_path)


def test_get_course_by_id(tmp_path):
    course = add_course("概率论", "2026-12-20", 60, data_dir=tmp_path)

    assert get_course(course["id"], tmp_path) == course


def test_get_unknown_course_rejected(tmp_path):
    add_course("概率论", "2026-12-20", 60, data_dir=tmp_path)

    with pytest.raises(StorageError, match="没有找到"):
        get_course("abc123", tmp_path)


@pytest.mark.parametrize("course_id", ["", "../courses", "NOT-HEX", None])
def test_invalid_course_id_rejected(tmp_path, course_id):
    with pytest.raises(StorageError, match="课程 ID 无效"):
        get_course(course_id, tmp_path)


def test_update_course(tmp_path):
    course = add_course("数据结构", "2026-12-20", 60, data_dir=tmp_path)

    updated = update_course(
        course["id"],
        data_dir=tmp_path,
        exam_date="2026-12-22",
        daily_minutes=120,
    )

    assert updated["exam_date"] == "2026-12-22"
    assert updated["daily_minutes"] == 120
    assert get_course(course["id"], tmp_path) == updated


def test_update_rejects_unknown_field(tmp_path):
    course = add_course("数据结构", "2026-12-20", 60, data_dir=tmp_path)

    with pytest.raises(StorageError, match="不能修改"):
        update_course(course["id"], data_dir=tmp_path, score=100)


def test_save_and_load_material(tmp_path):
    course = add_course("操作系统", "2026-12-20", 60, data_dir=tmp_path)
    pages = [
        {"page": 1, "text": "进程与线程"},
        {"page": 2, "text": "内存管理"},
    ]

    material = save_material(course["id"], "chapter1.pdf", pages, data_dir=tmp_path)

    assert material["page_count"] == 2
    assert material["char_count"] == len("进程与线程") + len("内存管理")
    assert material["filename"] == "chapter1.pdf"

    materials = load_materials(course["id"], tmp_path)
    assert len(materials) == 1
    assert materials[0]["pages"] == pages


def test_material_filename_is_sanitized(tmp_path):
    course = add_course("操作系统", "2026-12-20", 60, data_dir=tmp_path)

    material = save_material(
        course["id"],
        r"..\..\secret.txt",
        [{"page": 1, "text": "content"}],
        data_dir=tmp_path,
    )

    assert material["filename"] == "secret.txt"


def test_material_for_unknown_course_rejected(tmp_path):
    with pytest.raises(StorageError, match="没有找到"):
        save_material("abc123", "notes.txt", [{"page": 1, "text": "x"}], tmp_path)


def test_corrupted_courses_file_raises_storage_error(tmp_path):
    (tmp_path / "courses.json").write_text("{broken json", encoding="utf-8")

    with pytest.raises(StorageError, match="格式损坏"):
        load_courses(tmp_path)


def test_save_and_load_analysis(tmp_path):
    course = add_course("操作系统", "2026-12-20", 60, data_dir=tmp_path)
    material = save_material(
        course["id"],
        "chapter1.txt",
        [{"page": 1, "text": "进程与线程"}],
        data_dir=tmp_path,
    )
    analysis = {
        "provider": "测试服务",
        "model": "test-model",
        "analyzed_at": "2026-10-21T10:00:00",
        "chunk_count": 1,
        "analyzed_chunks": 1,
        "truncated": False,
        "key_points": [
            {
                "title": "进程与线程",
                "explanation": "解释",
                "importance": 5,
                "difficulty": 3,
                "keywords": ["调度"],
                "source_pages": [1],
                "source_pages_estimated": False,
            }
        ],
        "usage": {"total_tokens": 100},
    }

    saved = save_analysis(
        course["id"], material["id"], analysis, data_dir=tmp_path
    )

    assert saved["course_id"] == course["id"]
    assert saved["material_id"] == material["id"]

    loaded = load_analysis(course["id"], material["id"], tmp_path)
    assert loaded is not None
    assert loaded["key_points"] == analysis["key_points"]
    assert loaded["model"] == "test-model"


def test_save_analysis_overwrites_previous_result(tmp_path):
    course = add_course("操作系统", "2026-12-20", 60, data_dir=tmp_path)
    material = save_material(
        course["id"],
        "chapter1.txt",
        [{"page": 1, "text": "内容"}],
        data_dir=tmp_path,
    )

    save_analysis(
        course["id"],
        material["id"],
        {"key_points": [{"title": "旧考点"}]},
        data_dir=tmp_path,
    )
    save_analysis(
        course["id"],
        material["id"],
        {"key_points": [{"title": "新考点"}]},
        data_dir=tmp_path,
    )

    loaded = load_analysis(course["id"], material["id"], tmp_path)
    assert loaded is not None
    assert loaded["key_points"] == [{"title": "新考点"}]


def test_load_analysis_returns_none_when_missing(tmp_path):
    course = add_course("操作系统", "2026-12-20", 60, data_dir=tmp_path)
    material = save_material(
        course["id"],
        "chapter1.txt",
        [{"page": 1, "text": "内容"}],
        data_dir=tmp_path,
    )

    assert load_analysis(course["id"], material["id"], tmp_path) is None


def test_save_analysis_for_unknown_material_rejected(tmp_path):
    course = add_course("操作系统", "2026-12-20", 60, data_dir=tmp_path)

    with pytest.raises(StorageError, match="没有找到对应的资料"):
        save_analysis(
            course["id"],
            "abc123",
            {"key_points": [{"title": "考点"}]},
            data_dir=tmp_path,
        )


def test_save_analysis_requires_key_points(tmp_path):
    course = add_course("操作系统", "2026-12-20", 60, data_dir=tmp_path)
    material = save_material(
        course["id"],
        "chapter1.txt",
        [{"page": 1, "text": "内容"}],
        data_dir=tmp_path,
    )

    with pytest.raises(StorageError, match="没有可保存的考点"):
        save_analysis(
            course["id"],
            material["id"],
            {"key_points": []},
            data_dir=tmp_path,
        )
