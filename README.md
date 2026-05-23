# 🎙️ AI 实时语音转文字 & 口译笔记

基于 [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) 的本地离线实时语音识别工具，支持中英文混合识别，内置 LLM 润色和 AI 口译笔记功能。

## ✨ 特性

- **极低延迟**：流式 Zipformer 模型，逐字/逐词实时上屏，延迟 < 2 个单词
- **本地离线**：无需联网，CPU / CUDA GPU 均可运行
- **三语支持**：中文 (70MB)、English (280MB)、中英混合 (488MB)
- **双音频源**：麦克风输入 / 系统音频内录（WASAPI Loopback）
- **LLM 润色**：自动修正错别字、补全标点，支持自定义 System Prompt
- **AI 口译笔记**：符合专业口译规范的纵向意群笔记，支持追加模式
- **双模式输出**：替换模式（全文重写）/ 追加模式（增量追加不覆盖）
- **独立 LLM 配置**：润色和口译可使用不同的 API 和模型
- **白底黑字极简 GUI**：三栏布局可自由隐藏，高 DPI 清晰显示

## 📥 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/pipidu/AInterpretationNotes.git
cd AInterpretationNotes

# 双击运行（Windows）
install.bat
```

或手动安装：

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 2. 下载模型

首次运行会自动弹出模型下载对话框，勾选所需模型即可。

或手动下载：

```bash
python download_models.py --lang zh       # 中文
python download_models.py --lang en       # English
python download_models.py --lang bilingual # 中英混合
python download_models.py --lang all      # 全部
```

### 3. 启动

```bash
python main.py
# 或双击 run.bat
```

## 🖥️ 界面预览

```
┌──────────────────────────────────────────────────────┐
│  [▾ 音频源] [▾ 语言]  ☑润色 ☑口译 [▶ 开始识别] [⚙] │
├──────────────────────────────────────────────────────┤
│  背景/关键词: [输入会议主题、专有名词…]              │
├────────────┬──────────────┬───────────────────────────┤
│ 原始转录   │ LLM 润色     │ AI 口译笔记              │
│ (黑字白底) │ (绿字淡绿底) │ (棕字淡黄底)             │
│            │              │ ────────                  │
│ 同音错字…  │ 修正版文本…  │ 主：Q3 财报              │
│            │              │ 营 ↓15% vs Q2             │
│            │              │ ∵ 北美 市 ↓              │
│            │              │ ────────                  │
└────────────┴──────────────┴───────────────────────────┘
```

## ⚙️ LLM 设置

点击 ⚙ 设置按钮，可分别配置「润色 LLM」和「口译 LLM」：

- **API 地址**：OpenAI 兼容格式（默认 `https://api.openai.com/v1`）
- **API Key**：你的 API 密钥
- **模型**：如 `gpt-4o-mini`、`deepseek-chat` 等
- **处理间隔**：几秒处理一次
- **System Prompt**：自定义提示词
- **追加模式**：新内容只新增不覆盖（口译笔记推荐）

## 🛠️ 技术栈

| 组件 | 用途 |
|------|------|
| [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) | 流式语音识别引擎 |
| [tkinter](https://docs.python.org/3/library/tkinter.html) | GUI 框架（零 COM 依赖） |
| [soundcard](https://github.com/bastibe/soundcard) | 音频捕获 & WASAPI Loopback |
| OpenAI 兼容 API | LLM 润色 & 口译笔记 |

## 📦 编译为 EXE

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "实时语音转文字" main.py
```

生成的 exe 约 78 MB（不含模型），模型在首次运行时按需下载。

## 📄 License

Apache-2.0

## 👤 作者

**pipidu** — [github.com/pipidu](https://github.com/pipidu)
