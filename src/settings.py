"""读取本地 AI 配置。

配置来源优先级：
1. 系统环境变量
2. 项目根目录的 .env 文件

安全规则：
- API Key 只保存在本地 .env 或系统环境变量中。
- AISettings 的 repr 不包含 API Key，避免日志或调试输出泄露。
- 页面只显示服务商和模型名称，不显示密钥。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

DEFAULT_TIMEOUT = 60
DEFAULT_MAX_CHUNKS = 20
DEFAULT_CHUNK_SIZE = 6000
DEFAULT_OVERLAP_CHARS = 300


class AIConfigError(Exception):
    """AI 配置不完整或格式错误。"""


@dataclass(frozen=True)
class AISettings:
    provider: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    timeout: int = DEFAULT_TIMEOUT
    max_chunks: int = DEFAULT_MAX_CHUNKS
    chunk_size: int = DEFAULT_CHUNK_SIZE
    overlap_chars: int = DEFAULT_OVERLAP_CHARS


def _env_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
    read_value: Callable[[str], str],
) -> int:
    raw = read_value(name)
    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError:
        return default

    if not minimum <= value <= maximum:
        return default
    return value


def load_ai_settings(env_path: str | Path | None = None) -> AISettings | None:
    """读取配置；缺少必要字段时返回 None。

    必要字段：AI_API_KEY、AI_BASE_URL、AI_MODEL。
    其他字段有安全默认值，填错时回退到默认值。

    系统环境变量优先于 .env 文件。
    每次调用都会重新读取 .env，修改配置后刷新页面即可生效。
    """

    path = Path(env_path) if env_path is not None else ENV_PATH
    file_values = {}
    if path.is_file():
        try:
            file_values = dotenv_values(path)
        except Exception as exc:
            raise AIConfigError(f"无法读取 .env 文件：{exc}") from exc

    def read_value(name: str) -> str:
        env_value = os.getenv(name)
        if env_value is not None and env_value.strip():
            return env_value.strip()
        return (file_values.get(name) or "").strip()

    api_key = read_value("AI_API_KEY")
    base_url = read_value("AI_BASE_URL").rstrip("/")
    model = read_value("AI_MODEL")
    provider = read_value("AI_PROVIDER") or "OpenAI 兼容服务"

    if not api_key or not base_url or not model:
        return None

    if not base_url.startswith(("http://", "https://")):
        raise AIConfigError("AI_BASE_URL 必须以 http:// 或 https:// 开头。")

    return AISettings(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=_env_int("AI_TIMEOUT", DEFAULT_TIMEOUT, 5, 300, read_value),
        max_chunks=_env_int(
            "AI_MAX_CHUNKS", DEFAULT_MAX_CHUNKS, 1, 50, read_value
        ),
        chunk_size=_env_int(
            "AI_CHUNK_SIZE", DEFAULT_CHUNK_SIZE, 1000, 20000, read_value
        ),
        overlap_chars=DEFAULT_OVERLAP_CHARS,
    )
