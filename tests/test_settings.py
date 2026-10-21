"""AI 配置读取测试。"""

from __future__ import annotations

import pytest

from src.settings import AIConfigError, load_ai_settings

ENV_NAMES = (
    "AI_PROVIDER",
    "AI_BASE_URL",
    "AI_MODEL",
    "AI_API_KEY",
    "AI_TIMEOUT",
    "AI_MAX_CHUNKS",
    "AI_CHUNK_SIZE",
)


@pytest.fixture(autouse=True)
def clear_ai_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def write_env(path, **overrides):
    values = {
        "AI_PROVIDER": "测试服务",
        "AI_BASE_URL": "https://example.com/v1",
        "AI_MODEL": "test-model",
        "AI_API_KEY": "secret-test-key",
        "AI_TIMEOUT": "60",
        "AI_MAX_CHUNKS": "20",
        "AI_CHUNK_SIZE": "6000",
    }
    values.update(overrides)
    content = "\n".join(f"{key}={value}" for key, value in values.items())
    path.write_text(content + "\n", encoding="utf-8")
    return path


def test_missing_file_returns_none(tmp_path):
    assert load_ai_settings(tmp_path / "missing.env") is None


def test_empty_api_key_returns_none(tmp_path):
    path = write_env(tmp_path / "test.env", AI_API_KEY="")

    assert load_ai_settings(path) is None


def test_complete_config_is_loaded(tmp_path):
    path = write_env(tmp_path / "test.env")

    settings = load_ai_settings(path)

    assert settings is not None
    assert settings.provider == "测试服务"
    assert settings.base_url == "https://example.com/v1"
    assert settings.model == "test-model"
    assert settings.api_key == "secret-test-key"
    assert settings.timeout == 60
    assert settings.max_chunks == 20
    assert settings.chunk_size == 6000


def test_api_key_is_hidden_from_repr(tmp_path):
    settings = load_ai_settings(write_env(tmp_path / "test.env"))

    assert settings is not None
    assert "secret-test-key" not in repr(settings)


def test_system_environment_overrides_file(tmp_path, monkeypatch):
    path = write_env(tmp_path / "test.env")
    monkeypatch.setenv("AI_MODEL", "system-model")
    monkeypatch.setenv("AI_API_KEY", "system-key")

    settings = load_ai_settings(path)

    assert settings is not None
    assert settings.model == "system-model"
    assert settings.api_key == "system-key"


def test_invalid_numbers_fall_back_to_defaults(tmp_path):
    path = write_env(
        tmp_path / "test.env",
        AI_TIMEOUT="abc",
        AI_MAX_CHUNKS="999",
        AI_CHUNK_SIZE="1",
    )

    settings = load_ai_settings(path)

    assert settings is not None
    assert settings.timeout == 60
    assert settings.max_chunks == 20
    assert settings.chunk_size == 6000


def test_invalid_base_url_raises_config_error(tmp_path):
    path = write_env(tmp_path / "test.env", AI_BASE_URL="example.com/v1")

    with pytest.raises(AIConfigError, match="http"):
        load_ai_settings(path)
