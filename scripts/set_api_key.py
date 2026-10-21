"""安全地把 API Key 写入本地 .env 文件。

用法（在项目根目录）：
    .\\.venv\\Scripts\\python.exe scripts\\set_api_key.py

输入时终端不会显示 Key，脚本也不会把 Key 打印出来。
"""

from __future__ import annotations

import re
from getpass import getpass
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def main() -> None:
    print(f"配置文件：{ENV_PATH}")

    if not ENV_PATH.exists():
        ENV_PATH.write_text("AI_API_KEY=\n", encoding="utf-8")
        print("已创建 .env 文件。")

    key = getpass("请粘贴 API Key（输入不会显示），然后按回车：").strip()

    if not key:
        print("没有输入内容，配置未修改。")
        return

    if any(character.isspace() for character in key):
        print("Key 中包含空格或换行，配置未修改。请重新复制完整 Key。")
        return

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    output = []
    replaced = False

    for line in lines:
        if re.match(r"^\s*AI_API_KEY\s*=", line):
            output.append(f"AI_API_KEY={key}")
            replaced = True
        else:
            output.append(line)

    if not replaced:
        output.append(f"AI_API_KEY={key}")

    ENV_PATH.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    print(f"已保存。Key 长度：{len(key)} 个字符。")
    print("请回到 OpenCode 告诉我“已填好”，我会继续测试连接。")


if __name__ == "__main__":
    main()
