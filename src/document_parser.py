"""课程资料文本提取。

支持：
- TXT：自动尝试常见编码，并保留为第 1 页。
- PDF：提取可选中文字，并保留原始页码。

扫描版 PDF 不包含可选中文字，本模块会明确提示需要 OCR，
不会伪造提取结果。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
SUPPORTED_EXTENSIONS = {".txt", ".pdf"}


def extract_text(filename: str, file_bytes: bytes) -> list[dict]:
    """提取 TXT 或 PDF 中的文字。

    返回：
        [{"page": 1, "text": "..."}, ...]

    没有文字的页面会保留在结果中（text 为空字符串），
    以便界面提示用户具体哪些页面没有提取到内容。
    """

    if not filename or not filename.strip():
        raise ValueError("文件名不能为空。")

    if not isinstance(file_bytes, (bytes, bytearray)) or len(file_bytes) == 0:
        raise ValueError("文件内容为空，请重新上传。")

    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError("文件超过 20 MB，请压缩或拆分后再上传。")

    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError("目前只支持 TXT 和 PDF 文件。")

    if suffix == ".txt":
        return _extract_txt(file_bytes)

    return _extract_pdf(file_bytes)


def _extract_txt(file_bytes: bytes) -> list[dict]:
    """按常见编码依次尝试解码 TXT 文件。"""

    text = _decode_txt(file_bytes)
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()

    if not text:
        raise ValueError("TXT 文件没有可提取的文字。")

    return [{"page": 1, "text": text}]


def _decode_txt(file_bytes: bytes) -> str:
    # 带 BOM 的文件优先按 UTF-16 处理，避免被错误解码。
    if file_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return file_bytes.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise ValueError("TXT 文件编码损坏，请另存为 UTF-8 后重试。") from exc

    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError("无法识别 TXT 文件编码，请另存为 UTF-8 后重试。")


def _extract_pdf(file_bytes: bytes) -> list[dict]:
    """使用 PyMuPDF 逐页提取 PDF 文字。"""

    try:
        with pymupdf.open(
            stream=BytesIO(bytes(file_bytes)),
            filetype="pdf",
        ) as document:
            if document.needs_pass:
                raise ValueError("PDF 已加密，请先取消密码保护后再上传。")

            if document.page_count == 0:
                raise ValueError("PDF 中没有页面，请检查文件是否完整。")

            pages = []
            for page_number, page in enumerate(document, start=1):
                pages.append(
                    {
                        "page": page_number,
                        "text": page.get_text("text").strip(),
                    }
                )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF 无法读取，请检查文件是否损坏。") from exc

    if not any(item["text"] for item in pages):
        raise ValueError(
            "没有提取到文字，文件可能是扫描版 PDF，需要先做 OCR 文字识别。"
        )

    return pages
