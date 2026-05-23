"""
LLM 润色处理器
定时收集原始转录文本，调用 OpenAI 兼容 API 优化后输出
"""

import json
import threading
import time
import requests
import logging

logger = logging.getLogger(__name__)


class LLMProcessor:
    """后台 LLM 润色线程"""

    def __init__(self, base_url: str = "", api_key: str = "",
                 model: str = "", interval: float = 5.0,
                 context: str = "", append_mode: bool = False):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.interval = max(1.0, interval)
        self.context = context.strip()
        self.append_mode = append_mode

        self._thread: threading.Thread | None = None
        self._running = False
        self._raw_text = ""           # 累积的原始文本
        self._last_processed = ""     # 上次已处理的文本
        self._lock = threading.Lock()

        # 自定义 system prompt（None 则用默认润色 prompt）
        self._custom_system_prompt: str | None = None

        # 回调
        self.on_result = None
        self.on_status = None
        # append_mode 累积输出
        self._previous_output: str = ""

    def feed(self, text: str):
        """追加原始转录文本"""
        with self._lock:
            self._raw_text = text

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    # ── 主循环 ──
    def _run(self):
        while self._running:
            time.sleep(self.interval)
            if not self._running:
                break
            self._process()

    def _process(self):
        if not self.base_url or not self.api_key or not self.model:
            return

        with self._lock:
            raw = self._raw_text.strip()
        if not raw:
            return
        if raw == self._last_processed:
            return

        if self.append_mode:
            # 只把新增部分发给 API，附上前次笔记
            new_text = raw
            if self._last_processed and raw.startswith(self._last_processed):
                new_text = raw[len(self._last_processed):].strip()
            if not new_text:
                return
            try:
                result = self._call_api(new_text)
                if result:
                    self._last_processed = raw
                    self._previous_output += result.rstrip() + "\n"
                    if self.on_result:
                        self.on_result(self._previous_output.strip())
            except Exception as e:
                logger.exception("LLM API 调用失败")
                if self.on_status:
                    self.on_status(f"LLM 错误: {e}")
        else:
            # 替换模式：全文润色
            try:
                result = self._call_api(raw)
                if result:
                    self._last_processed = raw
                    if self.on_result:
                        self.on_result(result)
            except Exception as e:
                logger.exception("LLM API 调用失败")
                if self.on_status:
                    self.on_status(f"LLM 错误: {e}")

    def _call_api(self, text: str) -> str:
        """调用 OpenAI 兼容 API，关闭思考模式并兼容多种响应格式"""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # 构建 system prompt
        if self._custom_system_prompt is not None:
            system_prompt = self._custom_system_prompt
        else:
            system_prompt = (
                "你是一个专业的语音转录后处理器。你的任务是：\n"
                "1. 修正语音识别中的同音错别字和语病\n"
                "2. 添加合理的标点符号和段落换行\n"
                "3. 保持原意不变，不添加额外信息\n"
                "4. 如果是英文，修正拼写错误并添加标点\n"
                "5. 直接输出优化后的文本，不要任何解释"
            )
        if self.context:
            system_prompt += (
                "\n\n【会话背景/关键词】\n" + self.context + "\n"
                "请结合以上背景信息进行纠错和润色，"
                "尤其是专有名词和领域术语。"
            )

        # 构建 user message
        user_message = text
        if self.append_mode and self._previous_output:
            user_message = (
                f"【已有的笔记】\n{self._previous_output.strip()}\n\n"
                f"【新增转写内容】\n{text}\n\n"
                f"请仅为【新增转写内容】生成口译笔记，"
                f"直接输出追加的笔记，不要重复已有内容。"
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.3,
            # max_tokens: 给足空间，最少 4096
            "max_tokens": max(min(len(text) * 3, 16384), 4096),
            # ── 关闭思考模式（多个位置，兼容不同 API） ──
            "reasoning_effort": "none",
            "enable_thinking": False,
            "thinking": {"type": "disabled"},
        }
        resp = requests.post(
            url, headers=headers, json=payload, timeout=60
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"API 返回 {resp.status_code}: {resp.text[:500]}"
            )

        data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})
        finish = choice.get("finish_reason", "unknown")

        # 优先 content，其次 reasoning_content，取非空值
        content = (msg.get("content") or "").strip()
        reasoning = (msg.get("reasoning_content") or "").strip()

        logger.info(
            "LLM finish_reason=%s content_len=%d reasoning_len=%d",
            finish, len(content), len(reasoning)
        )

        result = content or reasoning

        if not result:
            keys = list(msg.keys())
            raise RuntimeError(
                f"模型未返回任何文本。finish_reason={finish}, "
                f"message keys={keys}"
            )
        return result
