"""
实时语音转文字 —— tkinter 三栏极简白底黑字 GUI
左：原始转录 | 中：LLM 润色 | 右：AI 口译笔记
零 COM 依赖，高 DPI 清晰文字
"""

import os
import sys
import ctypes
import json
import tkinter as tk
from tkinter import ttk, messagebox

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from transcriber import AudioTranscriber
from llm import LLMProcessor
from download_models import download_model

def _get_runtime_dir():
    """运行目录：exe 模式用 exe 所在目录，开发模式用脚本目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(_get_runtime_dir(), "config.json")


def get_base_dir():
    """获取基础目录：exe 运行时用 exe 所在目录（可写），开发时用脚本所在目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_config():
    """加载配置（运行目录优先，其次 AppData）"""
    paths = [CONFIG_PATH,
             os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                          "实时语音转文字", "config.json")]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


def save_config(cfg: dict) -> bool:
    """保存配置到运行目录，失败则回退 AppData"""
    paths = [CONFIG_PATH,
             os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                          "实时语音转文字", "config.json")]
    for p in paths:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            continue
    return False


# ═══════════════════════════════════════════
# 口译笔记专用 Prompt
# ═══════════════════════════════════════════
INTERPRETER_SYSTEM_PROMPT = """你是一个专业的口译笔记记录员。请将以下语音转录内容整理为口译笔记，严格遵循以下原则：

**竖向记录，意群分行**：每个意群独占一行，纵向排列
**快速书写，减笔连笔**：词语尽量缩写、简写，例如"经济"→"经"，"发展"→"发"
**缩略书写，少字多意**：用最少字数表意，如"改革开放以来取得巨大成就"→"改开 来 巨成"
**巧用符号，形象表意**：多用符号代替文字，如 ↑ ↓ → ← ∴ ∵ ≠ ≈ ＞ ＜
**段落划线，明确结束**：每个段落/话题结束后用 `────────` 分隔

示例格式：
────────
主：Q3 财报
营 ↓15% vs Q2
∵ 北美 市 ↓
→ 需 调 策略
────────
副：新产品 线
AI 助 手 上 线
客 户 +30%
────────

请直接输出口译笔记，不要任何解释。"""


# ═══════════════════════════════════════════
# 设置对话框（滚动单页布局）
# ═══════════════════════════════════════════
class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config: dict, on_save):
        super().__init__(parent)
        self.title("LLM 设置")
        self.geometry("560x600")
        self.minsize(440, 400)
        self.configure(bg="#FFFFFF")
        self.transient(parent)
        self.grab_set()

        self._config = config.copy()
        self._on_save = on_save

        font = ("Microsoft YaHei", 12)
        font_small = ("Microsoft YaHei", 10)
        font_prompt = ("Consolas", 10)

        # ── 底部按钮 ──
        btn_frame = tk.Frame(self, bg="#FFFFFF")
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=12)

        tk.Button(btn_frame, text="取消", bg="#EEEEEE", fg="#333333",
                  font=font, relief=tk.FLAT, padx=24, pady=6,
                  cursor="hand2", command=self.destroy).pack(side=tk.RIGHT)

        tk.Button(btn_frame, text="保存", bg="#1A1A1A", fg="#FFFFFF",
                  font=font, relief=tk.FLAT, padx=24, pady=6,
                  cursor="hand2", command=self._save).pack(
            side=tk.RIGHT, padx=(0, 12))

        # ── 滚动区域 ──
        canvas = tk.Canvas(self, bg="#FFFFFF", highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0), pady=(12, 0))

        inner = tk.Frame(canvas, bg="#FFFFFF")
        canvas.create_window((0, 0), window=inner, anchor=tk.NW, width=520)

        # ── 润色 LLM 配置 ──
        self._build_section(inner, font, font_small, font_prompt,
                            prefix="llm", title="🎨 润色 LLM",
                            default_model="gpt-4o-mini", default_interval="5")

        # 分隔线
        tk.Frame(inner, bg="#EEEEEE", height=1).pack(fill=tk.X, padx=16, pady=12)

        # ── 口译 LLM 配置 ──
        self._build_section(inner, font, font_small, font_prompt,
                            prefix="llm2", title="📝 口译笔记 LLM",
                            default_model="gpt-4o-mini", default_interval="8",
                            default_prompt=INTERPRETER_SYSTEM_PROMPT)

        # 分隔线
        tk.Frame(inner, bg="#EEEEEE", height=1).pack(fill=tk.X, padx=16, pady=12)

        # ── 关于 ──
        about = tk.Frame(inner, bg="#FFFFFF")
        about.pack(fill=tk.X, padx=16, pady=(0, 12))
        tk.Label(about, text="实时语音转文字", bg="#FFFFFF",
                 fg="#1A1A1A", font=("Microsoft YaHei", 14, "bold")
                 ).pack()
        tk.Label(about, text="作者：pipidu  |  github.com/pipidu", bg="#FFFFFF",
                 fg="#888888", font=font_small).pack(pady=(4, 0))

        # ── 更新滚动区域 ──
        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        # 鼠标滚轮支持
        def _on_mousewheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self._wheel_binding = _on_mousewheel

        self._center()

    def _build_section(self, parent, font, font_small, font_prompt,
                       prefix, title,
                       default_model="gpt-4o-mini", default_interval="5",
                       default_prompt=""):
        cf = self._config
        pad = {"padx": 16, "pady": (6, 0)}

        # 标题
        tk.Label(parent, text=title, bg="#FFFFFF",
                 fg="#333333", font=("Microsoft YaHei", 12, "bold"),
                 anchor=tk.W).pack(fill=tk.X, padx=16, pady=(8, 4))

        # ── API 地址 + Key 同行 ──
        row1 = tk.Frame(parent, bg="#FFFFFF")
        row1.pack(fill=tk.X, padx=16, pady=(4, 0))
        tk.Label(row1, text="API 地址", bg="#FFFFFF", fg="#888888",
                 font=font_small).pack(anchor=tk.W)
        var_url = tk.StringVar(value=cf.get(f"{prefix}_url", "https://api.openai.com/v1"))
        tk.Entry(row1, textvariable=var_url, font=font,
                 bg="#FAFAFA", relief=tk.FLAT, borderwidth=1,
                 highlightbackground="#E0E0E0",
                 highlightthickness=1).pack(fill=tk.X, pady=(2, 0))
        setattr(self, f"_{prefix}_url_var", var_url)

        tk.Label(row1, text="API Key", bg="#FFFFFF", fg="#888888",
                 font=font_small).pack(anchor=tk.W, pady=(6, 0))
        var_key = tk.StringVar(value=cf.get(f"{prefix}_key", ""))
        tk.Entry(row1, textvariable=var_key, font=font,
                 bg="#FAFAFA", relief=tk.FLAT, borderwidth=1,
                 highlightbackground="#E0E0E0", highlightthickness=1,
                 show="•").pack(fill=tk.X, pady=(2, 0))
        setattr(self, f"_{prefix}_key_var", var_key)

        # ── 模型 + 间隔 同行 ──
        row2 = tk.Frame(parent, bg="#FFFFFF")
        row2.pack(fill=tk.X, padx=16, pady=(6, 0))

        mf = tk.Frame(row2, bg="#FFFFFF")
        mf.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(mf, text="模型", bg="#FFFFFF", fg="#888888",
                 font=font_small).pack(anchor=tk.W)
        var_model = tk.StringVar(value=cf.get(f"{prefix}_model", default_model))
        tk.Entry(mf, textvariable=var_model, font=font,
                 bg="#FAFAFA", relief=tk.FLAT, borderwidth=1,
                 highlightbackground="#E0E0E0",
                 highlightthickness=1).pack(fill=tk.X, pady=(2, 0))
        setattr(self, f"_{prefix}_model_var", var_model)

        ivf = tk.Frame(row2, bg="#FFFFFF")
        ivf.pack(side=tk.LEFT, padx=(16, 0))
        tk.Label(ivf, text="间隔(秒)", bg="#FFFFFF", fg="#888888",
                 font=font_small).pack(anchor=tk.W)
        var_iv = tk.StringVar(value=str(cf.get(f"{prefix}_interval", int(default_interval))))
        tk.Entry(ivf, textvariable=var_iv, font=font, width=4,
                 bg="#FAFAFA", relief=tk.FLAT, borderwidth=1,
                 highlightbackground="#E0E0E0",
                 highlightthickness=1).pack(pady=(2, 0))
        setattr(self, f"_{prefix}_interval_var", var_iv)

        # ── System Prompt ──
        tk.Label(parent, text="System Prompt（留空使用内置默认）",
                 bg="#FFFFFF", fg="#888888",
                 font=font_small).pack(anchor=tk.W, padx=16, pady=(8, 0))
        prompt_text = tk.Text(
            parent, font=font_prompt, bg="#FAFAFA", fg="#333333",
            wrap=tk.WORD, relief=tk.FLAT, borderwidth=1,
            highlightbackground="#C0C0C0", highlightthickness=1,
            height=4, padx=8, pady=6,
        )
        prompt_text.pack(fill=tk.X, padx=16, pady=(2, 0))
        stored = cf.get(f"{prefix}_prompt", "")
        prompt_text.insert("1.0", stored or default_prompt)
        setattr(self, f"_{prefix}_prompt_text", prompt_text)

        # ── 追加模式 ──
        append_var = tk.BooleanVar(value=cf.get(f"{prefix}_append", False))
        cb = tk.Checkbutton(
            parent, text="追加模式（不覆盖已有内容）",
            variable=append_var, bg="#FFFFFF", fg="#555555",
            font=font_small, selectcolor="#FFFFFF",
            activebackground="#FFFFFF", cursor="hand2",
        )
        cb.pack(anchor=tk.W, padx=16, pady=(6, 4))
        setattr(self, f"_{prefix}_append_var", append_var)

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _save(self):
        for prefix, label in [("llm", "润色"), ("llm2", "口译")]:
            try:
                iv = float(getattr(self, f"_{prefix}_interval_var").get())
                if iv < 1:
                    raise ValueError
            except ValueError:
                messagebox.showwarning(
                    "无效输入", f"{label} 间隔必须是≥1的数字", parent=self)
                return

        cfg = self._config.copy()
        for prefix in ["llm", "llm2"]:
            cfg[f"{prefix}_url"] = getattr(self, f"_{prefix}_url_var").get().strip()
            cfg[f"{prefix}_key"] = getattr(self, f"_{prefix}_key_var").get().strip()
            cfg[f"{prefix}_model"] = getattr(self, f"_{prefix}_model_var").get().strip()
            cfg[f"{prefix}_interval"] = float(getattr(self, f"_{prefix}_interval_var").get())
            cfg[f"{prefix}_prompt"] = getattr(self, f"_{prefix}_prompt_text").get("1.0", "end-1c").strip()
            cfg[f"{prefix}_append"] = getattr(self, f"_{prefix}_append_var").get()

        ok = save_config(cfg)
        if not ok:
            messagebox.showwarning("保存失败", "无法写入配置文件。", parent=self)
        self._on_save(cfg)
        # 解绑滚轮
        if hasattr(self, '_wheel_binding'):
            self.unbind_all("<MouseWheel>")
        self.destroy()

    def destroy(self):
        if hasattr(self, '_wheel_binding'):
            self.unbind_all("<MouseWheel>")
        super().destroy()


# ═══════════════════════════════════════════
# 首次运行模型下载对话框
# ═══════════════════════════════════════════
MODEL_INFO = {
    "zh": {"name": "中文 (Zipformer)", "size": "~70 MB"},
    "en": {"name": "English (Zipformer)", "size": "~280 MB"},
    "bilingual": {"name": "中英混合 (Zipformer)", "size": "~488 MB"},
}


class ModelDownloader(tk.Toplevel):
    def __init__(self, parent, missing):
        super().__init__(parent)
        self.title("首次运行 — 下载语音识别模型")
        self.geometry("480x400")
        self.resizable(False, False)
        self.configure(bg="#FFFFFF")
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._missing = missing
        self._var_map = {}
        self._model_dir = os.path.join(get_base_dir(), "models")

        font = ("Microsoft YaHei", 12)
        font_small = ("Microsoft YaHei", 10)

        # 头部
        tk.Label(self, text="检测到部分模型未下载", bg="#FFFFFF",
                 fg="#1A1A1A", font=("Microsoft YaHei", 14, "bold"),
                 anchor=tk.W).pack(fill=tk.X, padx=24, pady=(24, 4))
        tk.Label(self, text="请选择需要下载的模型（可多选）：", bg="#FFFFFF",
                 fg="#888888", font=font_small,
                 anchor=tk.W).pack(fill=tk.X, padx=24, pady=(0, 12))

        # 勾选列表
        for code, name in missing:
            info = MODEL_INFO.get(code, {"name": code, "size": ""})
            v = tk.BooleanVar(value=True)
            self._var_map[code] = v
            cb = tk.Checkbutton(
                self, variable=v,
                text=f"{info['name']}  ({info['size']})",
                bg="#FFFFFF", fg="#333333", font=font,
                selectcolor="#FFFFFF", activebackground="#FFFFFF",
                cursor="hand2",
            )
            cb.pack(anchor=tk.W, padx=24, pady=(4, 0))

        if not missing:
            tk.Label(self, text="所有模型已就绪 ✔", bg="#FFFFFF",
                     fg="#2E7D32", font=font).pack(pady=16)

        # ── 进度条 + 文本 ──
        progress_frame = tk.Frame(self, bg="#FFFFFF")
        progress_frame.pack(fill=tk.X, padx=24, pady=(12, 6))

        self._progress_bar = ttk.Progressbar(
            progress_frame, mode="determinate", length=380)
        self._progress_bar.pack(fill=tk.X, pady=(0, 4))

        self._progress_text = tk.Label(
            progress_frame, text="", bg="#FFFFFF", fg="#888888",
            font=font_small, anchor=tk.W)
        self._progress_text.pack(fill=tk.X)

        # ── 按钮 ──
        btn_bar = tk.Frame(self, bg="#FFFFFF")
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=24, pady=16)

        tk.Button(btn_bar, text="跳过", bg="#EEEEEE", fg="#666666",
                  font=font, relief=tk.FLAT, padx=16, pady=6,
                  activebackground="#DDDDDD",
                  cursor="hand2", command=self._skip).pack(side=tk.LEFT)

        self._dl_btn = tk.Button(
            btn_bar, text="确认下载", bg="#1A1A1A", fg="#FFFFFF",
            font=("Microsoft YaHei", 12, "bold"), relief=tk.FLAT,
            padx=20, pady=6,
            activebackground="#333333", activeforeground="#FFFFFF",
            cursor="hand2", command=self._start_download,
        )
        self._dl_btn.pack(side=tk.RIGHT)

        self._center()

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _start_download(self):
        selected = [(code, self._var_map[code]) for code, _ in self._missing]
        to_dl = [code for code, v in selected if v.get()]
        if not to_dl:
            self.destroy()
            return

        self._dl_btn.configure(state=tk.DISABLED, text="下载中...")
        self._progress_bar.configure(maximum=len(to_dl), value=0)
        self._progress_text.configure(text="准备下载...")

        import threading
        threading.Thread(target=self._run_download, args=(to_dl,),
                         daemon=True).start()

    def _run_download(self, to_dl):
        total = len(to_dl)
        for i, code in enumerate(to_dl):
            info = MODEL_INFO.get(code, {"name": code, "size": ""})
            name = info["name"]

            self.after(0, self._progress_text.configure,
                       {"text": f"正在下载 {name} ..."})
            self.after(0, self._progress_bar.configure, {"value": i})

            start = __import__("time").time()
            try:
                ok = download_model(code)
            except Exception as e:
                self.after(0, self._progress_text.configure,
                           {"text": f"❌ {name} 下载失败: {e}"})
                continue

            elapsed = __import__("time").time() - start
            self.after(0, self._progress_bar.configure, {"value": i + 1})

            if ok:
                remaining = total - i - 1
                eta = ""
                if elapsed > 0 and remaining > 0:
                    eta_s = int(elapsed * remaining)
                    if eta_s >= 60:
                        eta = f"，预计剩余 {eta_s // 60} 分 {eta_s % 60} 秒"
                    else:
                        eta = f"，预计剩余 {eta_s} 秒"
                self.after(0, self._progress_text.configure,
                           {"text": f"✅ {name} 下载完成{eta}"})
            else:
                self.after(0, self._progress_text.configure,
                           {"text": f"⚠ {name} 下载失败"})

        self.after(0, self._on_done)

    def _on_done(self):
        self._progress_text.configure(text="✅ 全部下载完成，可以开始识别")
        self._dl_btn.destroy()
        f = tk.Frame(self, bg="#FFFFFF")
        f.pack(side=tk.BOTTOM, fill=tk.X, padx=24, pady=(0, 16))
        tk.Button(
            f, text="关闭", bg="#1A1A1A", fg="#FFFFFF",
            font=("Microsoft YaHei", 12), relief=tk.FLAT, padx=24, pady=6,
            activebackground="#333333", activeforeground="#FFFFFF",
            cursor="hand2", command=self.destroy,
        ).pack(side=tk.RIGHT)

    def _skip(self):
        messagebox.showinfo(
            "功能受限",
            "未下载模型的语言将无法使用。\n"
            "稍后可在运行时重新选择模型，系统会自动提示下载。",
            parent=self)
        self.destroy()

    def _on_close(self):
        self._skip()

    def _on_close(self):
        self._skip()


# ═══════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("实时语音转文字")
        self.geometry("1600x720")
        self.minsize(1100, 500)
        self.configure(bg="#FFFFFF")

        self._font_default = ("Microsoft YaHei", 14)
        self._font_text    = ("Microsoft YaHei", 11)
        self._font_small   = ("Microsoft YaHei", 10)
        self._font_title   = ("Microsoft YaHei", 12, "bold")

        self._transcriber: AudioTranscriber | None = None
        self._llm: LLMProcessor | None = None          # 润色
        self._llm2: LLMProcessor | None = None         # 口译
        self._full_transcript = ""

        self._model_dir = os.path.join(get_base_dir(), "models")
        self._config = load_config()

        self._build_ui()
        self._center()

        # 检查模型，缺失时弹出下载对话框
        self.after(200, self._check_models_on_startup)

    def _check_models_on_startup(self):
        missing = self._missing_models()
        if missing:
            ModelDownloader(self, missing)

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── UI ──
    def _build_ui(self):
        # ── 顶栏 ──
        bar = tk.Frame(self, bg="#FFFFFF")
        bar.pack(fill=tk.X, padx=24, pady=(24, 0))

        tk.Label(bar, text="音频源", bg="#FFFFFF", fg="#888888",
                 font=self._font_small).pack(side=tk.LEFT)

        self._audio_var = tk.StringVar(value="麦克风")
        ttk.Combobox(bar, textvariable=self._audio_var,
                     font=self._font_default, state="readonly", width=14,
                     values=["麦克风", "系统音频"]).pack(
            side=tk.LEFT, padx=(6, 24))

        tk.Label(bar, text="识别语言", bg="#FFFFFF", fg="#888888",
                 font=self._font_small).pack(side=tk.LEFT)

        self._lang_var = tk.StringVar(value="中文")
        ttk.Combobox(bar, textvariable=self._lang_var,
                     font=self._font_default, state="readonly", width=10,
                     values=["中文", "English", "中英混合"]).pack(
            side=tk.LEFT, padx=(6, 0))

        tk.Frame(bar, bg="#FFFFFF").pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._settings_btn = tk.Button(
            bar, text="⚙  设置", bg="#EEEEEE", fg="#333333",
            font=self._font_default, relief=tk.FLAT, padx=16, pady=6,
            activebackground="#DDDDDD",
            cursor="hand2", command=self._open_settings,
        )
        self._settings_btn.pack(side=tk.RIGHT, padx=(0, 12))

        self._start_btn = tk.Button(
            bar, text="▶  开始识别", bg="#1A1A1A", fg="#FFFFFF",
            font=self._font_default, relief=tk.FLAT, padx=20, pady=6,
            activebackground="#333333", activeforeground="#FFFFFF",
            cursor="hand2", command=self._on_start,
        )
        self._start_btn.pack(side=tk.RIGHT, padx=(0, 12))

        # LLM 开关：放开始按钮左边
        self._polish_enabled_var = tk.BooleanVar(value=True)
        self._interp_enabled_var = tk.BooleanVar(value=True)

        self._interp_toggle_cb = tk.Checkbutton(
            bar, text="口译笔记", variable=self._interp_enabled_var,
            bg="#FFFFFF", fg="#555555", font=self._font_small,
            selectcolor="#FFFFFF", activebackground="#FFFFFF",
            cursor="hand2",
        )
        self._interp_toggle_cb.pack(side=tk.RIGHT, padx=(0, 4))

        self._polish_toggle_cb = tk.Checkbutton(
            bar, text="润色", variable=self._polish_enabled_var,
            bg="#FFFFFF", fg="#555555", font=self._font_small,
            selectcolor="#FFFFFF", activebackground="#FFFFFF",
            cursor="hand2",
        )
        self._polish_toggle_cb.pack(side=tk.RIGHT, padx=(0, 4))

        self._stop_btn = tk.Button(
            bar, text="■  停止", bg="#CC0000", fg="#FFFFFF",
            font=self._font_default, relief=tk.FLAT, padx=20, pady=6,
            activebackground="#EE0000", activeforeground="#FFFFFF",
            cursor="hand2", command=self._on_stop,
        )

        # 分割线
        tk.Frame(self, bg="#EEEEEE", height=1).pack(
            fill=tk.X, padx=24, pady=(16, 0))

        # ── 上下文输入栏 ──
        ctx_bar = tk.Frame(self, bg="#FFFFFF")
        ctx_bar.pack(fill=tk.X, padx=24, pady=(12, 0))
        tk.Label(ctx_bar, text="背景 / 关键词", bg="#FFFFFF",
                 fg="#888888", font=self._font_small).pack(side=tk.LEFT)
        self._context_var = tk.StringVar()
        self._context_entry = tk.Entry(
            ctx_bar, textvariable=self._context_var, font=self._font_text,
            bg="#FAFAFA", fg="#555555", relief=tk.FLAT, borderwidth=1,
            highlightbackground="#D0D0D0", highlightthickness=1,
        )
        self._context_entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                                 padx=(8, 0))
        self._context_entry.insert(
            0, "在此输入会议主题、专有名词、背景信息…（可选）")

        # ── 三栏区域 ──
        self._panes = tk.Frame(self, bg="#FFFFFF")
        self._panes.pack(fill=tk.BOTH, expand=True, padx=24, pady=8)

        for i in range(3):
            self._panes.grid_columnconfigure(i, weight=1, uniform="col")
        self._panes.grid_rowconfigure(0, weight=1)
        # 隐藏后恢复用的占位行
        self._panes.grid_rowconfigure(1, weight=0)

        # ── 左栏：原始转录 ──
        self._col_left = tk.Frame(self._panes, bg="#FFFFFF")
        self._col_left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._raw_text = self._build_text_column(
            self._col_left, "原始转录", "#FAFAFA", "#1A1A1A",
            "#D0D0D0", "点击「开始识别」后…")

        # ── 中栏：LLM 润色 ──
        self._col_mid = tk.Frame(self._panes, bg="#FFFFFF")
        self._col_mid.grid(row=0, column=1, sticky="nsew", padx=2)
        self._llm_text = self._build_text_column(
            self._col_mid, "LLM 润色", "#FAFAFC", "#2A6E3F",
            "#C0D8C0", "优化后…")

        # ── 右栏：AI 口译笔记 ──
        self._col_right = tk.Frame(self._panes, bg="#FFFFFF")
        self._col_right.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        self._interp_text = self._build_text_column(
            self._col_right, "AI 口译笔记", "#FFFBF0", "#8B4513",
            "#D4C8A0", "口译笔记…")

        # ── 隐藏后的恢复栏 ──
        self._reveal_bar = tk.Frame(self._panes, bg="#FAFAFA", height=36)
        self._reveal_bar.grid_propagate(False)

        # 记录每栏的可见状态与关联 widget
        self._col_info = [
            {"frame": self._col_left,  "name": "原始转录",  "text": self._raw_text,
             "color": "#1A1A1A", "visible": True},
            {"frame": self._col_mid,   "name": "LLM 润色",  "text": self._llm_text,
             "color": "#2A6E3F", "visible": True},
            {"frame": self._col_right, "name": "口译笔记",  "text": self._interp_text,
             "color": "#8B4513", "visible": True},
        ]

        # ── 状态栏 ──
        sf = tk.Frame(self, bg="#FFFFFF", height=28)
        sf.pack(fill=tk.X, padx=24, pady=(0, 12))
        sf.pack_propagate(False)
        self._status = tk.Label(
            sf, text="就绪 — 请选择音频源并开始",
            bg="#FFFFFF", fg="#888888", font=self._font_small, anchor=tk.W
        )
        self._status.pack(fill=tk.X)

    def _build_text_column(self, parent, title, bg, fg, border, placeholder):
        # 标题栏（含关闭按钮）
        hdr = tk.Frame(parent, bg="#FFFFFF")
        hdr.pack(fill=tk.X, pady=(0, 4))
        tk.Label(hdr, text=title, bg="#FFFFFF",
                 fg="#888888", font=self._font_title, anchor=tk.W
                 ).pack(side=tk.LEFT)
        hide_btn = tk.Label(hdr, text="✕", bg="#FFFFFF", fg="#CCCCCC",
                            font=self._font_title, cursor="hand2")
        hide_btn.pack(side=tk.RIGHT, padx=(4, 0))
        hide_btn.bind("<Enter>", lambda e: hide_btn.configure(fg="#666666"))
        hide_btn.bind("<Leave>", lambda e: hide_btn.configure(fg="#CCCCCC"))
        hide_btn.bind("<Button-1>", lambda e, p=parent: self._toggle_column(p))
        parent._hide_btn = hide_btn
        parent._header = hdr

        # 文本区
        body = tk.Frame(parent, bg=bg)
        body.pack(fill=tk.BOTH, expand=True)
        txt = tk.Text(
            body, font=self._font_text, bg=bg, fg=fg,
            wrap=tk.WORD, relief=tk.FLAT, borderwidth=1,
            highlightbackground=border, highlightthickness=1,
            padx=12, pady=12, state=tk.NORMAL,
        )
        scrollbar = tk.Scrollbar(body, command=txt.yview)
        txt.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        txt.insert(tk.END, placeholder)
        txt.configure(state=tk.DISABLED)
        parent._body = body
        return txt

    # ── 栏显隐 ──
    def _toggle_column(self, frame):
        """隐藏/显示指定栏"""
        for info in self._col_info:
            if info["frame"] is frame:
                if info["visible"]:
                    self._hide_column(info)
                else:
                    self._show_column(info)
                return

    def _hide_column(self, info):
        info["frame"].grid_remove()
        info["visible"] = False
        self._relayout_columns()

    def _show_column(self, info):
        info["visible"] = True
        self._relayout_columns()

    def _relayout_columns(self):
        """根据可见性重新分配列和权重"""
        visible = [c for c in self._col_info if c["visible"]]
        hidden = [c for c in self._col_info if not c["visible"]]

        # 先移除所有
        for info in self._col_info:
            info["frame"].grid_remove()

        # 重置所有列权重
        for i in range(3):
            self._panes.grid_columnconfigure(i, weight=0, uniform="")

        # 可见栏 grid 到连续列
        for i, info in enumerate(visible):
            info["visible"] = True
            if i == 0:
                padx = (0, 4) if len(visible) > 1 else (0, 0)
            elif i == len(visible) - 1:
                padx = (4, 0)
            else:
                padx = (2, 2)
            info["frame"].grid(row=0, column=i, sticky="nsew", padx=padx)

        # 恢复栏
        for w in self._reveal_bar.winfo_children():
            w.destroy()

        if hidden:
            for h in hidden:
                btn = tk.Label(
                    self._reveal_bar,
                    text=f"▸ {h['name']}",
                    bg="#FAFAFA", fg="#AAAAAA",
                    font=self._font_small, cursor="hand2",
                    padx=12, pady=6,
                )
                btn.pack(side=tk.LEFT, padx=2)
                btn.bind("<Enter>", lambda e, b=btn: b.configure(
                    fg="#666666", bg="#F0F0F0"))
                btn.bind("<Leave>", lambda e, b=btn: b.configure(
                    fg="#AAAAAA", bg="#FAFAFA"))
                btn.bind("<Button-1>",
                         lambda e, h=h: self._show_column(h))
            self._reveal_bar.grid(
                row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        else:
            self._reveal_bar.grid_remove()

        # 可见列平分剩余空间
        for i in range(len(visible)):
            self._panes.grid_columnconfigure(i, weight=1, uniform="col")

    # ── 启动／停止 ──
    def _find_model_dir(self, lang: str) -> str | None:
        """查找模型目录：先查 exe 旁，再查捆绑包"""
        d = os.path.join(self._model_dir, lang)
        if os.path.exists(os.path.join(d, "tokens.txt")):
            return d
        if getattr(sys, "frozen", False):
            bundled = os.path.join(sys._MEIPASS, "models", lang)
            if os.path.exists(os.path.join(bundled, "tokens.txt")):
                return bundled
        return None

    def _missing_models(self):
        """返回缺失的模型列表"""
        all_lang = {"zh": "中文", "en": "English", "bilingual": "中英混合"}
        missing = []
        for code, name in all_lang.items():
            if self._find_model_dir(code) is None:
                missing.append((code, name))
        return missing

    def _on_start(self):
        lang_label = self._lang_var.get()
        if lang_label == "中文":
            lang = "zh"
        elif lang_label == "English":
            lang = "en"
        else:
            lang = "bilingual"

        source = "microphone" if self._audio_var.get() == "麦克风" else "system"

        found = self._find_model_dir(lang)
        if found is None:
            self._set_status(f"❌ 未找到 {lang_label} 模型，正在下载…")
            self.after(100, lambda: ModelDownloader(
                self, [(lang, lang_label)]))
            return
        # 临时用找到的模型根目录
        model_root = os.path.dirname(found)

        self._full_transcript = ""
        for t in (self._raw_text, self._llm_text, self._interp_text):
            t.configure(state=tk.NORMAL)
            t.delete("1.0", tk.END)
            t.configure(state=tk.DISABLED)

        self._start_btn.pack_forget()
        self._settings_btn.pack_forget()
        self._stop_btn.pack(side=tk.RIGHT)

        # ASR
        self._transcriber = AudioTranscriber(
            lang=lang, source=source,
            model_dir=model_root, use_gpu=True,
        )
        self._transcriber.on_partial = self._on_raw_partial
        self._transcriber.on_final   = self._on_raw_final
        self._transcriber.on_status  = self._set_status
        self._transcriber.start()

        # LLM 润色 & 口译
        self._start_llm_services()

    def _on_stop(self):
        if self._transcriber and self._transcriber.is_alive():
            self._transcriber.stop()
        for llm in (self._llm, self._llm2):
            if llm:
                llm.stop()
        self._llm = self._llm2 = None

        self._stop_btn.pack_forget()
        self._settings_btn.pack(side=tk.RIGHT, padx=(0, 12))
        self._start_btn.pack(side=tk.RIGHT)

    # ── LLM 服务 ──
    def _start_llm_services(self):
        context = self._context_var.get().strip()
        if context == "在此输入会议主题、专有名词、背景信息…（可选）":
            context = ""

        cfg = self._config

        # ── 润色 LLM ──
        polish_enabled = self._polish_enabled_var.get()
        url = cfg.get("llm_url", "")
        key = cfg.get("llm_key", "")
        model = cfg.get("llm_model", "")
        interval = cfg.get("llm_interval", 5)
        append_mode = cfg.get("llm_append", False)
        if url and key and model and polish_enabled:
            self._llm = LLMProcessor(
                base_url=url, api_key=key, model=model,
                interval=interval, context=context,
                append_mode=append_mode,
            )
            polish_prompt = cfg.get("llm_prompt", "").strip()
            if polish_prompt:
                self._llm._custom_system_prompt = polish_prompt
            self._llm.on_result = self._on_llm_polish
            self._llm.on_status = self._set_status
            self._llm.start()
            mode_label = "追加" if append_mode else "替换"
            self._set_status(f"润色 LLM 已启动 ({model}, {mode_label})")
        else:
            self._set_status("润色 LLM " + ("未配置" if polish_enabled else "已禁用"))

        # ── 口译 LLM ──
        interp_enabled = self._interp_enabled_var.get()
        url2 = cfg.get("llm2_url", "")
        key2 = cfg.get("llm2_key", "")
        model2 = cfg.get("llm2_model", "")
        interval2 = cfg.get("llm2_interval", 8)
        append_mode2 = cfg.get("llm2_append", False)
        if url2 and key2 and model2 and interp_enabled:
            self._llm2 = LLMProcessor(
                base_url=url2, api_key=key2, model=model2,
                interval=interval2, context=context,
                append_mode=append_mode2,
            )
            interp_prompt = cfg.get("llm2_prompt", "").strip()
            self._llm2._custom_system_prompt = (
                interp_prompt or INTERPRETER_SYSTEM_PROMPT
            )
            self._llm2.on_result = self._on_llm_interp
            self._llm2.on_status = self._set_status
            self._llm2.start()
            mode_label = "追加" if append_mode2 else "替换"
            self._set_status(f"口译 LLM 已启动 ({model2}, {mode_label})")
        else:
            if interp_enabled:
                self._set_status("口译 LLM 未配置")

    # ── ASR 回调 ──
    def _on_raw_partial(self, text: str):
        self.after(0, self._update_raw, text)
        if self._llm or self._llm2:
            full = self._full_transcript
            if full and not full.endswith("\n"):
                full += "\n"
            combined = full + text
            if self._llm and self._polish_enabled_var.get():
                self._llm.feed(combined)
            if self._llm2 and self._interp_enabled_var.get():
                self._llm2.feed(combined)

    def _on_raw_final(self, text: str):
        self.after(0, self._append_raw_final, text)
        if self._llm or self._llm2:
            full = self._full_transcript
            if full:
                full += "\n"
            combined = full + text
            if self._llm and self._polish_enabled_var.get():
                self._llm.feed(combined)
            if self._llm2 and self._interp_enabled_var.get():
                self._llm2.feed(combined)

    def _update_raw(self, text: str):
        if not text:
            return
        display = self._full_transcript
        if display and not display.endswith("\n"):
            display += "\n"
        display += text
        self._raw_text.configure(state=tk.NORMAL)
        self._raw_text.delete("1.0", tk.END)
        self._raw_text.insert(tk.END, display)
        self._raw_text.see(tk.END)
        self._raw_text.configure(state=tk.DISABLED)

    def _append_raw_final(self, text: str):
        if not text:
            return
        if self._full_transcript:
            self._full_transcript += "\n"
        self._full_transcript += text
        self._raw_text.configure(state=tk.NORMAL)
        self._raw_text.delete("1.0", tk.END)
        self._raw_text.insert(tk.END, self._full_transcript)
        self._raw_text.see(tk.END)
        self._raw_text.configure(state=tk.DISABLED)

    # ── LLM 回调 ──
    def _on_llm_polish(self, text: str):
        self.after(0, self._set_col_text, self._llm_text, text)

    def _on_llm_interp(self, text: str):
        self.after(0, self._set_col_text, self._interp_text, text)

    def _set_col_text(self, widget, text: str):
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        if text:
            widget.insert(tk.END, text)
        widget.see(tk.END)
        widget.configure(state=tk.DISABLED)

    def _set_status(self, msg: str):
        self.after(0, self._status.configure, {"text": msg})

    # ── 设置 ──
    def _open_settings(self):
        SettingsDialog(self, self._config, self._on_settings_saved)

    def _on_settings_saved(self, cfg: dict):
        self._config = cfg
        self._set_status("设置已保存")

    def destroy(self):
        if self._transcriber and self._transcriber.is_alive():
            self._transcriber.stop()
        for llm in (self._llm, self._llm2):
            if llm:
                llm.stop()
        super().destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
