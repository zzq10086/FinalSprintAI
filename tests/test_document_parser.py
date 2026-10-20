"""资料文本提取测试。"""

from __future__ import annotations

import pymupdf
import pytest

from src.document_parser import MAX_FILE_SIZE, extract_text


def make_pdf(page_texts: list[str]) -> bytes:
    """生成用于测试的 PDF 字节内容。"""

    document = pymupdf.open()
    try:
        for text in page_texts:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        return document.tobytes()
    finally:
        document.close()


def test_extract_utf8_txt():
    content = "第一章 计算机网络概述\n重点：OSI 七层模型".encode("utf-8")

    pages = extract_text("notes.txt", content)

    assert len(pages) == 1
    assert pages[0]["page"] == 1
    assert "OSI 七层模型" in pages[0]["text"]


def test_extract_gb18030_txt():
    content = "中文讲义：操作系统进程管理".encode("gb18030")

    pages = extract_text("讲义.txt", content)

    assert pages[0]["text"] == "中文讲义：操作系统进程管理"


def test_extract_txt_with_bom():
    content = "带 BOM 的笔记".encode("utf-8-sig")

    pages = extract_text("bom.txt", content)

    assert pages[0]["text"] == "带 BOM 的笔记"


def test_empty_file_rejected():
    with pytest.raises(ValueError, match="文件内容为空"):
        extract_text("empty.txt", b"")


def test_whitespace_only_txt_rejected():
    with pytest.raises(ValueError, match="没有可提取的文字"):
        extract_text("blank.txt", b"  \n\t  ")


def test_unsupported_extension_rejected():
    with pytest.raises(ValueError, match="只支持 TXT 和 PDF"):
        extract_text("slides.pptx", b"pretend content")


def test_oversized_file_rejected():
    oversized = b"a" * (MAX_FILE_SIZE + 1)

    with pytest.raises(ValueError, match="超过 20 MB"):
        extract_text("huge.txt", oversized)


def test_extract_pdf_keeps_page_numbers():
    content = make_pdf(["Page one content", "Page two content", "Page three content"])

    pages = extract_text("slides.pdf", content)

    assert [page["page"] for page in pages] == [1, 2, 3]
    assert "Page two content" in pages[1]["text"]


def test_pdf_with_empty_page_keeps_page_entry():
    content = make_pdf(["First page", "", "Third page"])

    pages = extract_text("with-blank.pdf", content)

    assert len(pages) == 3
    assert pages[1]["text"] == ""


def test_scanned_pdf_without_text_rejected():
    content = make_pdf(["", ""])

    with pytest.raises(ValueError, match="扫描版 PDF"):
        extract_text("scanned.pdf", content)


def test_corrupt_pdf_rejected():
    with pytest.raises(ValueError, match="PDF 无法读取"):
        extract_text("broken.pdf", b"this is not a real pdf")
