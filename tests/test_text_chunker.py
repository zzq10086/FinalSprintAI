"""文本分段测试。"""

from __future__ import annotations

import pytest

from src.text_chunker import chunk_pages


def test_short_text_returns_single_chunk():
    pages = [{"page": 1, "text": "第一章 计算机网络概述"}]

    chunks = chunk_pages(pages, max_chars=1000)

    assert len(chunks) == 1
    assert chunks[0].index == 1
    assert chunks[0].pages == (1,)
    assert "第一章 计算机网络概述" in chunks[0].text
    assert "【第 1 页】" in chunks[0].text


def test_multiple_pages_are_combined_when_short():
    pages = [
        {"page": 1, "text": "进程与线程"},
        {"page": 2, "text": "内存管理"},
    ]

    chunks = chunk_pages(pages, max_chars=1000)

    assert len(chunks) == 1
    assert chunks[0].pages == (1, 2)
    assert "进程与线程" in chunks[0].text
    assert "内存管理" in chunks[0].text


def test_long_text_is_split_with_overlap():
    pages = [{"page": 1, "text": "甲" * 2500}]

    chunks = chunk_pages(pages, max_chars=1000, overlap_chars=100)

    assert len(chunks) >= 3
    assert all(chunk.pages == (1,) for chunk in chunks)
    assert all(chunk.char_count <= 1000 for chunk in chunks)
    assert "【第 1 页】" in chunks[0].text
    assert all(chunk.text for chunk in chunks)


def test_pages_are_preserved_across_chunks():
    pages = [
        {"page": 1, "text": "A" * 800},
        {"page": 2, "text": "B" * 800},
    ]

    chunks = chunk_pages(pages, max_chars=600, overlap_chars=50)

    assert len(chunks) >= 2
    assert chunks[0].pages[0] == 1
    assert chunks[-1].pages[-1] == 2
    assert all(chunk.pages for chunk in chunks)


def test_empty_pages_are_skipped():
    pages = [
        {"page": 1, "text": "第一页内容"},
        {"page": 2, "text": "   "},
        {"page": 3, "text": "第三页内容"},
    ]

    chunks = chunk_pages(pages, max_chars=1000)

    assert len(chunks) == 1
    assert chunks[0].pages == (1, 3)


def test_empty_material_returns_empty_list():
    assert chunk_pages([]) == []
    assert chunk_pages([{"page": 1, "text": ""}]) == []


@pytest.mark.parametrize(
    "max_chars,overlap_chars",
    [(99, 10), (1000, -1), (1000, 1000)],
)
def test_invalid_chunk_settings_rejected(max_chars, overlap_chars):
    with pytest.raises(ValueError):
        chunk_pages(
            [{"page": 1, "text": "内容"}],
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )


def test_invalid_page_rejected():
    with pytest.raises(ValueError, match="页码"):
        chunk_pages([{"page": 0, "text": "内容"}])
