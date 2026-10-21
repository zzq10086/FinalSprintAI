"""AI 适配器和考点解析测试（不发起真实网络请求）。"""

from __future__ import annotations

import json

import pytest
import requests

from src.ai_service import (
    AIServiceError,
    analyze_material,
    build_analysis_messages,
    check_ai_connection,
    merge_key_points,
    parse_key_points,
    request_chat_completion,
)
from src.settings import AISettings
from src.text_chunker import TextChunk


def make_settings(**overrides) -> AISettings:
    values = {
        "provider": "测试服务",
        "base_url": "https://example.com/v1",
        "model": "test-model",
        "api_key": "secret-test-key",
        "timeout": 5,
        "max_chunks": 20,
        "chunk_size": 700,
        "overlap_chars": 50,
    }
    values.update(overrides)
    return AISettings(**values)


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: dict | None = None,
        json_error: bool = False,
    ):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error
        self.text = json.dumps(payload) if payload is not None else ""

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload


def make_post(response, captured: dict | None = None):
    def post(url, headers=None, json=None, timeout=None):
        if captured is not None:
            captured.update(
                {
                    "url": url,
                    "headers": headers,
                    "payload": json,
                    "timeout": timeout,
                }
            )
        if isinstance(response, Exception):
            raise response
        return response

    return post


def chat_payload(content: str, usage: dict | None = None) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": usage
        or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def point_payload(title: str, pages: list[int]) -> str:
    return json.dumps(
        {
            "key_points": [
                {
                    "title": title,
                    "explanation": f"{title}的解释",
                    "importance": 4,
                    "difficulty": 3,
                    "keywords": ["关键词"],
                    "source_pages": pages,
                }
            ]
        },
        ensure_ascii=False,
    )


def test_successful_request_returns_content_and_usage():
    captured = {}
    response = FakeResponse(payload=chat_payload("连接成功"))

    content, usage = request_chat_completion(
        make_settings(),
        [{"role": "user", "content": "你好"}],
        http_post=make_post(response, captured),
    )

    assert content == "连接成功"
    assert usage["total_tokens"] == 15
    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["payload"]["model"] == "test-model"
    assert captured["headers"]["Authorization"] == "Bearer secret-test-key"
    assert captured["timeout"] == 5


@pytest.mark.parametrize(
    "status,pattern",
    [
        (400, "HTTP 400"),
        (401, "API Key"),
        (402, "余额"),
        (403, "权限"),
        (404, "接口地址"),
        (429, "频繁"),
        (500, "暂时不可用"),
    ],
)
def test_http_errors_are_readable(status, pattern):
    response = FakeResponse(status_code=status)

    with pytest.raises(AIServiceError, match=pattern):
        request_chat_completion(
            make_settings(),
            [{"role": "user", "content": "hi"}],
            http_post=make_post(response),
        )


def test_timeout_is_readable():
    with pytest.raises(AIServiceError, match="超时"):
        request_chat_completion(
            make_settings(),
            [{"role": "user", "content": "hi"}],
            http_post=make_post(requests.Timeout("slow")),
        )


def test_connection_error_is_readable():
    with pytest.raises(AIServiceError, match="无法连接"):
        request_chat_completion(
            make_settings(),
            [{"role": "user", "content": "hi"}],
            http_post=make_post(requests.ConnectionError("offline")),
        )


def test_non_json_response_is_readable():
    with pytest.raises(AIServiceError, match="不是 JSON"):
        request_chat_completion(
            make_settings(),
            [{"role": "user", "content": "hi"}],
            http_post=make_post(FakeResponse(json_error=True)),
        )


def test_empty_content_is_readable():
    with pytest.raises(AIServiceError, match="空内容"):
        request_chat_completion(
            make_settings(),
            [{"role": "user", "content": "hi"}],
            http_post=make_post(FakeResponse(payload=chat_payload(""))),
        )


def test_parse_markdown_fenced_json_and_filter_pages():
    content = """```json
{"key_points": [
  {"title": "进程与线程", "explanation": "解释内容", "importance": 5,
   "difficulty": 2, "keywords": ["调度"], "source_pages": [1, 99]}
]}
```"""

    points = parse_key_points(content, allowed_pages={1, 2}, fallback_pages=(1, 2))

    assert len(points) == 1
    assert points[0]["title"] == "进程与线程"
    assert points[0]["source_pages"] == [1]
    assert points[0]["source_pages_estimated"] is False


def test_invalid_pages_fall_back_to_chunk_pages():
    content = """{"key_points": [
      {"title": "内存管理", "explanation": "解释", "importance": 3,
       "difficulty": 4, "keywords": [], "source_pages": [99]}
    ]}"""

    points = parse_key_points(
        content,
        allowed_pages={2},
        fallback_pages=(2, 3),
    )

    assert points[0]["source_pages"] == [2, 3]
    assert points[0]["source_pages_estimated"] is True


def test_invalid_json_rejected():
    with pytest.raises(AIServiceError, match="JSON"):
        parse_key_points("这不是 JSON", allowed_pages={1})


def test_missing_key_points_rejected():
    with pytest.raises(AIServiceError, match="key_points"):
        parse_key_points('{"other": []}', allowed_pages={1})


def test_merge_key_points_deduplicates():
    points = [
        {
            "title": "进程 与 线程",
            "explanation": "短解释",
            "importance": 3,
            "difficulty": 2,
            "keywords": ["A"],
            "source_pages": [1],
            "source_pages_estimated": False,
        },
        {
            "title": "进程与线程",
            "explanation": "更完整的解释",
            "importance": 5,
            "difficulty": 4,
            "keywords": ["B"],
            "source_pages": [2],
            "source_pages_estimated": False,
        },
    ]

    merged = merge_key_points(points)

    assert len(merged) == 1
    assert merged[0]["explanation"] == "更完整的解释"
    assert merged[0]["importance"] == 5
    assert merged[0]["difficulty"] == 4
    assert merged[0]["keywords"] == ["A", "B"]
    assert merged[0]["source_pages"] == [1, 2]


def test_build_analysis_messages_contains_pages_and_schema():
    chunk = TextChunk(
        index=1,
        text="【第 3 页】\n内容",
        pages=(3,),
        char_count=10,
    )

    messages = build_analysis_messages(chunk, total_chunks=2)

    assert messages[0]["role"] == "system"
    assert "第 1/2 段" in messages[1]["content"]
    assert "第 3 页" in messages[1]["content"]
    assert "key_points" in messages[1]["content"]


def test_analyze_material_combines_chunks_and_usage():
    pages = [
        {"page": 1, "text": "A" * 600},
        {"page": 2, "text": "B" * 600},
    ]
    responses = [
        FakeResponse(payload=chat_payload(point_payload("考点一", [1]))),
        FakeResponse(payload=chat_payload(point_payload("考点二", [2]))),
    ]
    calls = {"count": 0}
    progress = []

    def post(url, headers=None, json=None, timeout=None):
        index = calls["count"]
        calls["count"] += 1
        return responses[index]

    result = analyze_material(
        pages,
        make_settings(),
        progress_callback=lambda completed, total, pages: progress.append(
            (completed, total)
        ),
        http_post=post,
    )

    assert result["chunk_count"] == 2
    assert result["analyzed_chunks"] == 2
    assert result["truncated"] is False
    assert len(result["key_points"]) == 2
    assert result["usage"]["total_tokens"] == 30
    assert progress == [(0, 2), (1, 2)]


def test_analyze_material_marks_truncation():
    pages = [
        {"page": 1, "text": "A" * 600},
        {"page": 2, "text": "B" * 600},
    ]
    response = FakeResponse(payload=chat_payload(point_payload("考点一", [1])))

    result = analyze_material(
        pages,
        make_settings(max_chunks=1),
        http_post=make_post(response),
    )

    assert result["truncated"] is True
    assert result["analyzed_chunks"] == 1
    assert result["chunk_count"] == 2


def test_check_ai_connection_returns_reply():
    response = FakeResponse(payload=chat_payload("连接成功"))

    reply = check_ai_connection(
        make_settings(),
        http_post=make_post(response),
    )

    assert reply == "连接成功"
