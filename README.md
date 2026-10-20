# FinalSprint AI

FinalSprint AI 是面向大学生的 AI 期末复习与冲刺平台。目标是在考试前 7 天，帮助学生从课程资料中提炼重点、安排复习计划、练习题目并记录错题。

当前版本为 **v0.1（第一阶段 MVP）**，已实现课程任务创建、TXT/PDF 资料上传、文本提取和本地保存。

## 已实现功能

- 创建课程/复习任务：课程名称、考试日期、每日可复习时间
- 选择当前复习任务，查看距离考试的天数
- 上传 TXT 或 PDF 文件
- 提取 TXT 文本并自动识别 UTF-8、GB18030、UTF-16 编码
- 提取 PDF 文字，并保留原始页码
- 空文件、超限文件、损坏文件、扫描版 PDF、加密 PDF 的明确错误提示
- 课程和提取结果保存为本地 JSON，重启应用后仍可查看
- 自动化测试覆盖资料解析和本地存储

## 技术栈

- Python 3.13（在 3.13.7 上测试）
- Streamlit 1.66
- PyMuPDF 2.0
- pytest（仅开发测试使用）

所有数据保存在本机 `data/` 目录，不会上传到服务器。`data/` 已加入 `.gitignore`。

## 安装与运行（Windows）

在项目根目录打开 PowerShell：

```powershell
cd D:\FinalSprintAI

# 如果还没有虚拟环境，执行下面这一行
python -m venv .venv

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 安装运行依赖
python -m pip install -r requirements.txt

# 启动应用
streamlit run app.py
```

浏览器通常会自动打开 <http://localhost:8501>。如果没有自动打开，手动访问该地址。

如果 PowerShell 提示“禁止运行脚本”，可以只对当前窗口临时放行：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## 运行测试

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -v
```

## 使用流程

1. 展开“创建新的复习任务”，填写课程名称、考试日期和每日复习时间。
2. 在“当前复习任务”下拉框选择课程。
3. 上传 TXT 或 PDF，点击“提取并保存资料”。
4. 展开“已保存资料”查看每页文本和空页面提示。

首次启动时会自动创建 `data/courses.json` 和 `data/materials/`，无需手动创建。

## 项目结构

```text
FinalSprintAI/
├── app.py                      # Streamlit 页面入口
├── requirements.txt            # 运行依赖
├── requirements-dev.txt        # 测试依赖
├── README.md
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── document_parser.py      # TXT/PDF 文本提取
│   └── storage.py              # 本地 JSON 存储
├── tests/
│   ├── test_document_parser.py
│   └── test_storage.py
└── data/                       # 本地学习数据（不提交到 Git）
    └── .gitkeep
```

## 已知限制

- **扫描版 PDF 无法直接提取文字**，当前版本会提示需要 OCR，不会返回伪造内容。
- TXT 文件最大 20 MB，超过会拒绝；大型 PDF 建议拆分后再上传。
- 当前只按文件保存文本，尚未进行 AI 分段、考点提炼和向量检索。
- 尚未接入大模型 API，也没有复习计划、练习题和错题本。
- 目前是单机应用，没有多用户账号和云端同步。

## 下一阶段目标

第二阶段将接入 OpenAI 兼容的大模型 API：

- 使用 `.env` 安全读取 API Key
- 对提取文本进行分段
- 提炼考点、关键词和知识点解释
- 尽量保留资料页码作为来源
- 处理超时、限流、余额不足和返回格式错误
- 未配置 API 时，第一阶段的资料管理功能仍可使用

## 安全说明

- 不要提交 `.env`、API Key、课程资料或个人学习数据。
- `data/`、`.env` 和 `.streamlit/secrets.toml` 已在 `.gitignore` 中排除。
- 当前版本不会发起任何外部网络请求。
