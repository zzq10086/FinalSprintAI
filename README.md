# FinalSprint AI

FinalSprint AI 是面向大学生的 AI 期末复习与冲刺平台。目标是在考试前 7 天，帮助学生从课程资料中提炼重点、安排复习计划、练习题目并记录错题。

当前版本为 **v0.2.1（第二阶段 MVP）**，已实现课程任务、TXT/PDF 资料提取、AI 考点提炼、本地结果保存和课程日期修改。

## 已实现功能

- 创建课程/复习任务：课程名称、考试日期、每日可复习时间
- 选择当前复习任务，查看距离考试的天数
- 修改当前课程的考试日期和每日复习时间
- 上传 TXT 或 PDF 文件
- 提取 TXT 文本并自动识别 UTF-8、GB18030、UTF-16 编码
- 提取 PDF 文字，并保留原始页码
- 空文件、超限文件、损坏文件、扫描版 PDF、加密 PDF 的明确错误提示
- 使用 OpenAI 兼容接口提炼核心考点、关键词和知识点解释
- 为考点标注重要度、难度和来源页码
- 按约 6000 字分段，默认最多分析 20 段，避免单次费用失控
- 超时、限流、余额不足、Key 无效、返回格式错误的中文提示
- 保存 AI 分析结果，重复打开页面不重复调用 API
- 显示本次调用消耗的 token 数量
- 未配置 API Key 时，资料上传、提取和查看仍可正常使用
- 自动化测试覆盖资料解析、本地存储、配置读取、文本分段、AI 适配器和页面流程

## 技术栈

- Python 3.13（在 3.13.7 上测试）
- Streamlit 1.66
- PyMuPDF 2.0
- requests（调用 OpenAI 兼容接口）
- python-dotenv（读取本地 `.env`）
- pytest（仅开发测试使用）

课程和资料保存在本机 `data/` 目录。只有点击“AI 提炼考点”时，当前资料文本才会发送给配置的模型服务。

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

## 配置 AI（以通义千问为例）

1. 复制配置模板：

```powershell
Copy-Item .env.example .env
```

2. 填写 API Key。推荐使用安全脚本，输入时不会显示 Key：

```powershell
.\.venv\Scripts\python.exe scripts\set_api_key.py
```

也可以手动编辑：

```powershell
notepad .env
```

通义千问配置示例：

```text
AI_PROVIDER=通义千问
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_MODEL=qwen-plus
AI_API_KEY=sk-你的真实密钥
```

3. 保存后刷新页面。左侧栏会显示“AI 已配置”，可以点击“测试 AI 连接”。

其他 OpenAI 兼容服务只需替换 `AI_BASE_URL` 和 `AI_MODEL`，示例见 `.env.example`。

> API Key 只保存在本地 `.env` 或系统环境变量中，不会显示在页面，也不会提交到 Git。

## 运行测试

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -v
```

测试使用模拟 HTTP 响应，不会消耗真实 API 额度。

## 使用流程

1. 展开“创建新的复习任务”，填写课程名称、考试日期和每日复习时间。
2. 在“当前复习任务”下拉框选择课程。
3. 如需修改考试日期，展开“✏️ 修改当前课程的考试日期 / 每日复习时间”。
4. 上传 TXT 或 PDF，点击“提取并保存资料”。
5. 在资料卡片中点击“AI 提炼考点”，等待分段分析完成。
6. 查看考点解释、关键词、重要度、难度和来源页码。
7. 展开“查看来源页原文”核对 AI 结果。

首次启动时会自动创建 `data/courses.json`、`data/materials/` 和 `data/analyses/`，无需手动创建。

## 项目结构

```text
FinalSprintAI/
├── app.py                      # Streamlit 页面入口
├── requirements.txt            # 运行依赖
├── requirements-dev.txt        # 测试依赖
├── .env.example                # 模型配置模板（不含真实密钥）
├── README.md
├── .gitignore
├── scripts/
│   └── set_api_key.py          # 安全写入本地 API Key
├── src/
│   ├── __init__.py
│   ├── document_parser.py      # TXT/PDF 文本提取
│   ├── text_chunker.py         # 按字符分段并保留页码
│   ├── settings.py             # 读取 .env / 环境变量
│   ├── ai_service.py           # OpenAI 兼容接口与考点解析
│   └── storage.py              # 本地 JSON 存储
├── tests/
│   ├── test_app.py
│   ├── test_document_parser.py
│   ├── test_text_chunker.py
│   ├── test_settings.py
│   ├── test_ai_service.py
│   └── test_storage.py
└── data/                       # 本地学习数据（不提交到 Git）
    └── .gitkeep
```

## 已知限制

- **扫描版 PDF 无法直接提取文字**，当前版本会提示需要 OCR，不会返回伪造内容。
- TXT 文件最大 20 MB，超过会拒绝；大型 PDF 建议拆分后再上传。
- 默认最多分析 20 个文本段。资料特别长时只会分析前 20 段，页面会明确提示；可在 `.env` 中调整 `AI_MAX_CHUNKS`。
- AI 生成内容可能出错、遗漏或页码标注不准确，必须结合原始教材核对。
- 当前按标题去重，近似但不同的考点可能重复出现。
- 分析过程是同步等待，长资料可能需要数十秒到数分钟。
- 尚未实现复习计划、练习题和错题本。
- 目前是单机应用，没有多用户账号和云端同步。

## 下一阶段目标

第三阶段将实现七天复习计划：

- 根据考试日期计算剩余天数
- 根据每天可用时间生成任务
- 按考点重要性和难度分配复习顺序
- 支持标记任务完成和查看进度
- 处理考试日期已过、当天考试和剩余时间不足等情况

## 安全与隐私

- 不要提交 `.env`、API Key、课程资料或个人学习数据。
- `data/`、`.env` 和 `.streamlit/secrets.toml` 已在 `.gitignore` 中排除。
- 只有点击 AI 分析时，当前资料文本才会发送给配置的模型服务。
- 不会发送其他课程、账号信息或本地文件路径。
- 如果 Key 泄露，应立即在模型服务商控制台删除并重新创建。
