"""OpenAI 兼容的大模型调用与考点提炼。

设计要点：
- 不绑定某一家厂商，只需要 AI_BASE_URL 兼容 /chat/completions。
- 所有网络错误都转换成可读的 AIServiceError，页面直接展示。
- 不自动重试，避免在限流或余额不足时产生不可控费用。
- 只发送用户当前选择分析的资料文本。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Callable

import requests

from src.settings import AIConfigError, AISettings
from src.text_chunker import TextChunk, chunk_pages

MAX_KEY_POINTS = 60
ANALYSIS_MAX_TOKENS = 2000
TEST_MAX_TOKENS = 20

ANALYSIS_SYSTEM_PROMPT = (
    "你是一名严谨的大学课程助教，擅长把课件、讲义和笔记整理成期末复习考点。"
    "你只依据用户提供的资料作答，不补充资料以外的知识，不编造页码。"
)


class AIServiceError(Exception):
    """可以安全展示给用户的 AI 服务错误。"""


def request_chat_completion(
    settings: AISettings,
    messages: list[dict],
    *,
    max_tokens: int = ANALYSIS_MAX_TOKENS,
    temperature: float = 0.2,
    http_post: Callable[..., Any] | None = None,
) -> tuple[str, dict]:
    """调用 OpenAI 兼容的 /chat/completions 接口。

    返回 (模型文本, usage 字典)。usage 可能为空字典。
    """

    if not settings.api_key:
        raise AIConfigError("尚未配置 AI_API_KEY。")

    url = f"{settings.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": settings.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    post = http_post or requests.post

    try:
        response = post(
            url,
            headers=headers,
            json=payload,
            timeout=settings.timeout,
        )
    except requests.Timeout as exc:
        raise AIServiceError(
            "请求模型服务超时，请检查网络或稍后重试。"
        ) from exc
    except requests.ConnectionError as exc:
        raise AIServiceError(
            "无法连接模型服务，请检查网络、代理或 AI_BASE_URL。"
        ) from exc
    except requests.RequestException as exc:
        raise AIServiceError(f"调用模型服务失败：{exc}") from exc

    _raise_for_status(response)

    try:
        data = response.json()
    except ValueError as exc:
        raise AIServiceError(
            "模型接口返回的内容不是 JSON，请检查接口地址或模型兼容性。"
        ) from exc

    content = _extract_content(data)
    return content, _extract_usage(data)


def _raise_for_status(response: Any) -> None:
    status = getattr(response, "status_code", 0)

    if status < 400:
        return

    if status == 400:
        message = "模型服务拒绝了请求（HTTP 400），请检查模型名称、上下文长度或参数设置。"
    elif status == 401:
        message = "API Key 无效或已过期，请检查 .env 中的 AI_API_KEY。"
    elif status == 402:
        message = "账户余额不足或额度已用完，请充值或更换模型服务。"
    elif status == 403:
        message = "没有访问该模型的权限，请检查账号权限、实名认证或模型名称。"
    elif status == 404:
        message = "接口地址或模型名称不正确，请检查 AI_BASE_URL 和 AI_MODEL。"
    elif status == 429:
        message = "请求过于频繁或超出配额，请稍后再试。"
    elif status >= 500:
        message = f"模型服务暂时不可用（HTTP {status}），请稍后重试。"
    else:
        message = f"模型接口返回错误（HTTP {status}），请检查配置后重试。"

    raise AIServiceError(message)


def _extract_content(data: Any) -> str:
    if not isinstance(data, dict):
        raise AIServiceError("模型接口返回格式不正确。")

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AIServiceError("模型接口没有返回 choices，请检查接口兼容性。")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise AIServiceError("模型接口返回格式不正确。")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise AIServiceError("模型接口返回格式不正确。")

    content = message.get("content")

    # 部分兼容接口会把 content 返回成多段文本列表。
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        content = "".join(parts)

    if not isinstance(content, str) or not content.strip():
        raise AIServiceError("模型返回了空内容，请稍后重试或更换模型。")

    return content.strip()


def _extract_usage(data: Any) -> dict:
    if not isinstance(data, dict):
        return {}

    usage = data.get("usage")
    if not isinstance(usage, dict):
        return {}

    allowed = ("prompt_tokens", "completion_tokens", "total_tokens")
    result = {}
    for key in allowed:
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            result[key] = value
    return result


def build_analysis_messages(
    chunk: TextChunk,
    total_chunks: int,
) -> list[dict]:
    page_text = "、".join(str(page) for page in chunk.pages)
    user_prompt = f"""这是同一份课程资料的第 {chunk.index}/{total_chunks} 段，涉及页码：{page_text}。

请提炼 3-8 个期末复习核心考点，按重要性从高到低排列。

要求：
1. 只使用本段资料中的信息，不要编造资料中没有的内容。
2. source_pages 只能填写本段涉及页码中的数字，不要填写其他页码。
3. explanation 用中文说明：这个知识点是什么、为什么重要、可能怎么考。
4. importance 和 difficulty 必须是 1-5 的整数。
5. keywords 提供 2-5 个关键词。
6. 只输出 JSON，不要 Markdown 代码块，不要输出额外说明。

JSON 格式：
{{
  "key_points": [
    {{
      "title": "考点名称",
      "explanation": "知识点解释",
      "importance": 5,
      "difficulty": 3,
      "keywords": ["关键词1", "关键词2"],
      "source_pages": [1, 2]
    }}
  ]
}}

资料内容：
{chunk.text}
"""
    return [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def parse_key_points(
    content: str,
    allowed_pages: set[int],
    fallback_pages: tuple[int, ...] = (),
) -> list[dict]:
    """解析模型返回的 JSON，并校验页码和字段。"""

    data = _extract_json_object(content)
    raw_points = data.get("key_points")
    if not isinstance(raw_points, list) or not raw_points:
        raise AIServiceError("模型返回的 JSON 中没有 key_points 列表，请重试。")

    points = []
    for item in raw_points:
        if not isinstance(item, dict):
            continue

        title = _clean_title(item.get("title"))
        explanation = _clean_explanation(item.get("explanation"))
        if not title or not explanation:
            continue

        keywords = _clean_keywords(item.get("keywords"))
        source_pages, estimated = _clean_source_pages(
            item.get("source_pages"),
            allowed_pages=allowed_pages,
            fallback_pages=fallback_pages,
        )

        points.append(
            {
                "title": title,
                "explanation": explanation,
                "importance": _to_score(item.get("importance")),
                "difficulty": _to_score(item.get("difficulty")),
                "keywords": keywords,
                "source_pages": source_pages,
                "source_pages_estimated": estimated,
            }
        )

    if not points:
        raise AIServiceError(
            "模型没有返回有效的考点，请重试或更换模型。"
        )

    return points


def _extract_json_object(content: str) -> dict:
    text = content.strip()

    # 去掉模型偶尔添加的 Markdown 代码块。
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AIServiceError(
            "模型返回的内容不是有效 JSON，请重试或更换模型。"
        )

    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIServiceError(
            "模型返回的 JSON 格式错误，请重试或更换模型。"
        ) from exc

    if not isinstance(data, dict):
        raise AIServiceError("模型返回的 JSON 结构不正确。")
    return data


def _clean_title(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def _clean_explanation(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _clean_keywords(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    keywords = []
    for item in value:
        if not isinstance(item, str):
            continue
        keyword = " ".join(item.split()).strip()
        if keyword and keyword not in keywords:
            keywords.append(keyword)
        if len(keywords) >= 8:
            break
    return keywords


def _to_score(value: Any) -> int:
    if isinstance(value, bool):
        return 3
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, min(5, score))


def _clean_source_pages(
    value: Any,
    allowed_pages: set[int],
    fallback_pages: tuple[int, ...],
) -> tuple[list[int], bool]:
    if isinstance(value, (int, str)):
        value = [value]

    pages = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, bool):
                continue
            try:
                page = int(item)
            except (TypeError, ValueError):
                continue
            if page in allowed_pages and page not in pages:
                pages.append(page)

    if pages:
        return sorted(pages), False

    # 模型没有给出有效页码时，使用该文本段自身页码，并明确标记为推断。
    fallback = sorted(set(fallback_pages))
    if fallback:
        return fallback, True
    return [], False


def merge_key_points(points: list[dict]) -> list[dict]:
    """合并多个文本段的结果，并按标题去重。"""

    merged: dict[str, dict] = {}
    order: list[str] = []

    for point in points:
        title = point["title"]
        key = re.sub(r"\s+", "", title).lower()
        if not key:
            continue

        if key not in merged:
            merged[key] = {
                "title": title,
                "explanation": point["explanation"],
                "importance": point["importance"],
                "difficulty": point["difficulty"],
                "keywords": list(point["keywords"]),
                "source_pages": list(point["source_pages"]),
                "source_pages_estimated": point.get(
                    "source_pages_estimated", False
                ),
            }
            order.append(key)
            continue

        existing = merged[key]
        if len(point["explanation"]) > len(existing["explanation"]):
            existing["explanation"] = point["explanation"]
        existing["importance"] = max(
            existing["importance"], point["importance"]
        )
        existing["difficulty"] = max(
            existing["difficulty"], point["difficulty"]
        )

        for keyword in point["keywords"]:
            if keyword not in existing["keywords"]:
                existing["keywords"].append(keyword)
        existing["keywords"] = existing["keywords"][:8]

        existing["source_pages"] = sorted(
            set(existing["source_pages"]) | set(point["source_pages"])
        )
        existing["source_pages_estimated"] = (
            existing["source_pages_estimated"]
            and point.get("source_pages_estimated", False)
        )

    result = [merged[key] for key in order]
    result.sort(
        key=lambda item: (
            -item["importance"],
            -item["difficulty"],
            item["title"],
        )
    )
    return result[:MAX_KEY_POINTS]


def analyze_material(
    pages: list[dict],
    settings: AISettings,
    *,
    progress_callback: (
        Callable[[int, int, tuple[int, ...]], None] | None
    ) = None,
    http_post: Callable[..., Any] | None = None,
) -> dict:
    """分段分析整份资料，返回可保存的考点结果。"""

    chunks = chunk_pages(
        pages,
        max_chars=settings.chunk_size,
        overlap_chars=settings.overlap_chars,
    )
    if not chunks:
        raise AIServiceError("资料中没有可分析的文字。")

    selected_chunks = chunks[: settings.max_chunks]
    if not selected_chunks:
        raise AIServiceError("没有可分析的文本段。")

    all_points: list[dict] = []
    total_usage: dict[str, int] = {}
    total_chunks = len(selected_chunks)

    for position, chunk in enumerate(selected_chunks):
        if progress_callback is not None:
            progress_callback(position, total_chunks, chunk.pages)

        messages = build_analysis_messages(chunk, total_chunks)
        try:
            content, usage = request_chat_completion(
                settings,
                messages,
                http_post=http_post,
            )
            points = parse_key_points(
                content,
                allowed_pages=set(chunk.pages),
                fallback_pages=chunk.pages,
            )
        except AIServiceError as exc:
            page_text = "、".join(str(page) for page in chunk.pages)
            raise AIServiceError(
                f"分析第 {chunk.index}/{len(chunks)} 段"
                f"（第 {page_text} 页）时失败：{exc}"
            ) from exc

        all_points.extend(points)
        _add_usage(total_usage, usage)

    merged_points = merge_key_points(all_points)
    if not merged_points:
        raise AIServiceError("模型没有返回有效考点，请重试。")

    return {
        "provider": settings.provider,
        "model": settings.model,
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "chunk_count": len(chunks),
        "analyzed_chunks": len(selected_chunks),
        "truncated": len(chunks) > len(selected_chunks),
        "key_points": merged_points,
        "usage": total_usage,
    }


def _add_usage(total: dict[str, int], usage: dict) -> None:
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            total[key] = total.get(key, 0) + value


def check_ai_connection(
    settings: AISettings,
    *,
    http_post: Callable[..., Any] | None = None,
) -> str:
    """发送一个最小请求，验证密钥、地址和模型是否可用。"""

    messages = [
        {"role": "system", "content": "你是连接测试助手。"},
        {"role": "user", "content": "请只回复四个字：连接成功"},
    ]
    content, _ = request_chat_completion(
        settings,
        messages,
        max_tokens=TEST_MAX_TOKENS,
        temperature=0,
        http_post=http_post,
    )
    if not content.strip():
        raise AIServiceError("模型返回了空内容。")
    return content.strip()
