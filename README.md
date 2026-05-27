# 🎙️ AI 实时语音转文字 & 口译笔记

基于 [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) 的本地离线实时语音识别工具，支持中英文混合识别，内置 LLM 润色和 AI 口译笔记功能。

## ✨ 特性

- **极低延迟**：流式 Zipformer 模型，逐字/逐词实时上屏，延迟 < 2 个单词
- **本地离线**：无需联网，CPU / CUDA GPU 均可运行
- **三语支持**：中文 (70MB)、English (280MB)、中英混合 (488MB)
- **双音频源**：麦克风输入 / 系统音频内录（WASAPI Loopback）
- **LLM 润色**：自动修正错别字、补全标点，支持自定义 System Prompt
- **AI 口译笔记**：符合专业口译规范的纵向意群笔记，支持追加/替换双模式
- **三栏可隐藏**：原始转录 / LLM 润色 / AI 口译笔记，每栏可独立显示隐藏
- **独立 LLM 配置**：润色和口译可使用不同的 API 地址、Key、模型和提示词
- **追加模式**：新内容只追加不覆盖已有笔记（口译场景推荐）
- **背景上下文**：支持输入会议主题、专有名词等背景信息提升 LLM 准确度
- **白底黑字极简 GUI**：tkinter 原生界面，高 DPI 清晰显示，零 COM 依赖
- **首次运行引导**：自动检测缺失模型，弹出下载对话框，支持进度条和剩余时间预估

## 📥 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/pipidu/AInterpretationNotes.git
cd AInterpretationNotes
install.bat
```

或手动：

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 2. 下载模型

首次运行自动弹出下载对话框，勾选模型即可。或手动：

```bash
python download_models.py --lang zh       # 中文 ~70MB
python download_models.py --lang en       # English ~280MB
python download_models.py --lang bilingual # 中英混合 ~488MB
```

### 3. 启动

```bash
python main.py
# 或双击 run.bat
```

## 🖥️ 界面

```
┌──────────────────────────────────────────────────────────┐
│ [▾音频源] [▾语言]     ☑润色 ☑口译 [⚙设置] [▶开始识别]    │
├──────────────────────────────────────────────────────────┤
│ 背景/关键词: [输入会议主题、专有名词…________________]    │
├──────────────┬──────────────┬─────────────────────────────┤
│ 原始转录  ✕  │ LLM 润色  ✕  │ AI 口译笔记  ✕             │
│ (黑字白底)   │ (绿字淡绿底) │ (棕字淡黄底)               │
└──────────────┴──────────────┴─────────────────────────────┘
```

## ⚙️ 设置页面

单页滚动布局，润色和口译 LLM 配置一目了然：

- API 地址 + Key
- 模型名称 + 处理间隔
- System Prompt（留空使用内置默认）
- ☑ 追加模式

## 🛠️ 技术栈

| 组件 | 用途 |
|------|------|
| [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) | 流式语音识别引擎 |
| tkinter | GUI 框架（Python 内置，零 COM 依赖） |
| [soundcard](https://github.com/bastibe/soundcard) | 音频捕获 & WASAPI Loopback |
| OpenAI 兼容 API | LLM 润色 & 口译笔记 |

## 📦 编译为 EXE

```bash
pip install pyinstaller
pyinstaller 实时语音转文字.spec
```

- 不含模型：~78 MB
- 含三个模型：~998 MB

## 👤 作者

**pipidu** — [github.com/pipidu](https://github.com/pipidu)
