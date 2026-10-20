"""本地 JSON 存储。

第一阶段只保存两类数据：
- data/courses.json：课程与复习任务信息。
- data/materials/<课程ID>/<资料ID>.json：上传资料提取出的文字和页码。

设计原则：
- 不依赖数据库，方便初学者理解和迁移。
- 写入时先生成临时文件再替换，降低文件写坏的风险。
- data/ 已在 .gitignore 中排除，避免把个人学习资料提交到公开仓库。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

MAX_COURSE_NAME_LENGTH = 60
MAX_DAILY_MINUTES = 24 * 60


class StorageError(Exception):
    """本地存储相关的可预期错误。"""


def _resolve_data_dir(data_dir: str | Path | None) -> Path:
    """确定数据目录并确保它存在。"""

    path = Path(data_dir).expanduser() if data_dir is not None else DEFAULT_DATA_DIR
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageError(f"无法创建数据目录：{path}") from exc
    return path


def _courses_path(data_dir: str | Path | None) -> Path:
    return _resolve_data_dir(data_dir) / "courses.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StorageError(f"数据文件格式损坏：{path.name}") from exc
    except OSError as exc:
        raise StorageError(f"无法读取数据文件：{path.name}") from exc


def _write_json(path: Path, data: Any) -> None:
    """原子写入 JSON，尽量避免中途失败留下半个文件。"""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(path.name + ".tmp")
        temp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    except OSError as exc:
        raise StorageError(f"无法写入数据文件：{path.name}") from exc


def _normalize_course_name(name: Any) -> str:
    if not isinstance(name, str):
        raise StorageError("课程名称必须是文字。")

    normalized = " ".join(name.split())
    if not normalized:
        raise StorageError("课程名称不能为空。")
    if len(normalized) > MAX_COURSE_NAME_LENGTH:
        raise StorageError(f"课程名称不能超过 {MAX_COURSE_NAME_LENGTH} 个字符。")
    return normalized


def _normalize_exam_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise StorageError("考试日期格式应为 YYYY-MM-DD。") from exc
    raise StorageError("考试日期格式无效。")


def _normalize_daily_minutes(value: Any) -> int:
    if isinstance(value, bool):
        raise StorageError("每日复习时间必须是整数分钟。")

    try:
        minutes = int(value)
    except (TypeError, ValueError) as exc:
        raise StorageError("每日复习时间必须是整数分钟。") from exc

    if not 1 <= minutes <= MAX_DAILY_MINUTES:
        raise StorageError("每日复习时间应在 1 到 1440 分钟之间。")
    return minutes


def _validate_course_id(course_id: Any) -> str:
    if not isinstance(course_id, str) or not course_id:
        raise StorageError("课程 ID 无效。")
    # 课程 ID 由 uuid4().hex 生成，只允许十六进制字符，避免路径穿越。
    if any(char not in "0123456789abcdef" for char in course_id):
        raise StorageError("课程 ID 无效。")
    return course_id


def load_courses(data_dir: str | Path | None = None) -> list[dict]:
    """读取全部课程；数据文件不存在时返回空列表。"""

    raw = _read_json(_courses_path(data_dir), [])
    if not isinstance(raw, list):
        raise StorageError("课程数据格式不正确，请检查 data/courses.json。")

    for course in raw:
        if not isinstance(course, dict) or not course.get("id"):
            raise StorageError("课程数据格式不正确，请检查 data/courses.json。")
    return raw


def get_course(course_id: str, data_dir: str | Path | None = None) -> dict:
    """按 ID 读取课程，找不到时抛出 StorageError。"""

    course_id = _validate_course_id(course_id)
    for course in load_courses(data_dir):
        if course.get("id") == course_id:
            return course
    raise StorageError("没有找到对应的课程。")


def add_course(
    name: str,
    exam_date: date | str,
    daily_minutes: int,
    data_dir: str | Path | None = None,
) -> dict:
    """创建课程并立即写入本地文件。"""

    course = {
        "id": uuid.uuid4().hex,
        "name": _normalize_course_name(name),
        "exam_date": _normalize_exam_date(exam_date).isoformat(),
        "daily_minutes": _normalize_daily_minutes(daily_minutes),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    courses = load_courses(data_dir)
    courses.append(course)
    _write_json(_courses_path(data_dir), courses)
    return course


def update_course(
    course_id: str,
    data_dir: str | Path | None = None,
    **changes: Any,
) -> dict:
    """更新课程允许修改的字段，并返回更新后的课程。"""

    allowed_fields = {"name", "exam_date", "daily_minutes"}
    unknown_fields = set(changes) - allowed_fields
    if unknown_fields:
        raise StorageError(f"不能修改这些字段：{', '.join(sorted(unknown_fields))}。")
    if not changes:
        raise StorageError("没有需要更新的内容。")

    course_id = _validate_course_id(course_id)
    courses = load_courses(data_dir)

    for course in courses:
        if course.get("id") != course_id:
            continue

        if "name" in changes:
            course["name"] = _normalize_course_name(changes["name"])
        if "exam_date" in changes:
            course["exam_date"] = _normalize_exam_date(changes["exam_date"]).isoformat()
        if "daily_minutes" in changes:
            course["daily_minutes"] = _normalize_daily_minutes(
                changes["daily_minutes"]
            )

        _write_json(_courses_path(data_dir), courses)
        return course

    raise StorageError("没有找到对应的课程。")


def _materials_dir(
    course_id: str,
    data_dir: str | Path | None,
) -> Path:
    course_id = _validate_course_id(course_id)
    return _resolve_data_dir(data_dir) / "materials" / course_id


def save_material(
    course_id: str,
    filename: str,
    pages: list[dict],
    data_dir: str | Path | None = None,
) -> dict:
    """保存一次资料提取结果，并返回包含页码的完整资料记录。"""

    get_course(course_id, data_dir)  # 确保课程存在

    safe_filename = Path(str(filename)).name.strip()
    if not safe_filename:
        raise StorageError("文件名不能为空。")

    if not isinstance(pages, list) or not pages:
        raise StorageError("没有可保存的提取结果。")

    normalized_pages = []
    for item in pages:
        if not isinstance(item, dict) or "page" not in item:
            raise StorageError("提取结果格式不正确。")
        try:
            page_number = int(item["page"])
        except (TypeError, ValueError) as exc:
            raise StorageError("提取结果中的页码格式不正确。") from exc
        normalized_pages.append(
            {
                "page": page_number,
                "text": str(item.get("text") or ""),
            }
        )

    material = {
        "id": uuid.uuid4().hex,
        "course_id": course_id,
        "filename": safe_filename,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "page_count": len(normalized_pages),
        "char_count": sum(len(page["text"]) for page in normalized_pages),
        "pages": normalized_pages,
    }

    path = _materials_dir(course_id, data_dir) / f"{material['id']}.json"
    _write_json(path, material)
    return material


def load_materials(
    course_id: str,
    data_dir: str | Path | None = None,
) -> list[dict]:
    """读取某门课程已保存的全部资料，按上传时间排序。"""

    directory = _materials_dir(course_id, data_dir)
    if not directory.exists():
        return []

    materials = []
    for path in directory.glob("*.json"):
        material = _read_json(path, None)
        if not isinstance(material, dict) or not material.get("id"):
            raise StorageError(f"资料数据格式损坏：{path.name}")
        materials.append(material)

    materials.sort(key=lambda item: item.get("uploaded_at", ""))
    return materials
