"""把带页码的资料切分成适合大模型处理的文本段。

切分目标：
- 每段不超过 max_chars 个字符。
- 相邻段保留少量重叠，避免考点被切断。
- 每段记录来源页码，方便 AI 结果标注出处。
- 在段内保留【第 N 页】标记，帮助模型理解页码。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    pages: tuple[int, ...]
    char_count: int


def chunk_pages(
    pages: list[dict],
    max_chars: int = 6000,
    overlap_chars: int = 300,
) -> list[TextChunk]:
    """把 [{"page": 1, "text": "..."}] 切分成文本段。"""

    if not isinstance(max_chars, int) or max_chars < 100:
        raise ValueError("每段字符数不能小于 100。")
    if not isinstance(overlap_chars, int) or overlap_chars < 0:
        raise ValueError("重叠字符数不能为负数。")
    if overlap_chars >= max_chars:
        raise ValueError("重叠字符数必须小于每段字符数。")
    if not isinstance(pages, list):
        raise ValueError("资料页码数据格式不正确。")

    parts: list[str] = []
    page_spans: list[tuple[int, int, int]] = []
    cursor = 0

    for item in pages:
        if not isinstance(item, dict):
            raise ValueError("资料页码数据格式不正确。")

        try:
            page_number = int(item["page"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("资料页码格式不正确。") from exc
        if page_number <= 0:
            raise ValueError("资料页码必须大于 0。")

        text = str(item.get("text") or "").strip()
        if not text:
            continue

        if parts:
            parts.append("\n")
            cursor += 1

        marker = f"【第 {page_number} 页】\n"
        parts.append(marker)
        cursor += len(marker)

        content_start = cursor
        parts.append(text)
        cursor += len(text)
        page_spans.append((content_start, cursor, page_number))

    full_text = "".join(parts)
    if not full_text.strip() or not page_spans:
        return []

    chunks: list[TextChunk] = []
    start = 0
    text_length = len(full_text)

    while start < text_length:
        end = min(start + max_chars, text_length)

        # 尽量在换行处断开，避免把一句话从中间截断。
        if end < text_length:
            search_from = start + int(max_chars * 0.6)
            newline_position = full_text.rfind("\n", search_from, end)
            if newline_position > start:
                end = newline_position

        text = full_text[start:end].strip()
        chunk_pages = tuple(
            sorted(
                {
                    page_number
                    for span_start, span_end, page_number in page_spans
                    if span_start < end and span_end > start
                }
            )
        )

        if text and chunk_pages:
            chunks.append(
                TextChunk(
                    index=len(chunks) + 1,
                    text=text,
                    pages=chunk_pages,
                    char_count=len(text),
                )
            )

        if end >= text_length:
            break

        start = max(end - overlap_chars, start + 1)

    return chunks
