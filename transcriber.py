"""
实时语音转文字——后台推理线程（纯 threading，无 GUI 依赖）
"""

import os
import glob
import logging
import warnings
import threading
import numpy as np
import sherpa_onnx
import soundcard as sc

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning, module="soundcard")
warnings.filterwarnings("ignore", message=".*data discontinuity.*")

MODEL_SAMPLE_RATE = 16000


class AudioTranscriber(threading.Thread):

    def __init__(self, lang="zh", source="microphone",
                 model_dir="models", use_gpu=True):
        super().__init__(daemon=False)
        self.lang = lang
        self.source = source
        self.model_dir = os.path.join(model_dir, lang)
        self.use_gpu = use_gpu
        self._running = False
        self._sample_rate = MODEL_SAMPLE_RATE

        self.on_partial = None
        self.on_final = None
        self.on_status = None

    def _emit_status(self, msg):
        if self.on_status:
            self.on_status(msg)

    def _emit_partial(self, text):
        if self.on_partial:
            self.on_partial(text)

    def _emit_final(self, text):
        if self.on_final:
            self.on_final(text)

    # ── 模型文件 ──
    def _find_model_files(self):
        def pick(pattern):
            candidates = glob.glob(os.path.join(self.model_dir, pattern))
            if not candidates:
                raise FileNotFoundError(f"未找到 ({pattern}): {self.model_dir}")
            non_int8 = [c for c in candidates if "int8" not in c.lower()]
            return non_int8[0] if non_int8 else candidates[0]
        return (
            pick("*encoder-epoch*.onnx"),
            pick("*decoder-epoch*.onnx"),
            pick("*joiner-epoch*.onnx"),
            os.path.join(self.model_dir, "tokens.txt"),
        )

    # ── 识别器 ──
    def _create_recognizer(self):
        encoder, decoder, joiner, tokens = self._find_model_files()

        # zh: greedy cjkchar  |  en / bilingual: beam search bpe
        if self.lang == "zh":
            modeling_unit = "cjkchar"
            decoding_method = "greedy_search"
            max_active_paths = None
        else:
            modeling_unit = "bpe"
            decoding_method = "modified_beam_search"
            max_active_paths = 4

        def _build(provider, threads):
            kwargs = dict(
                tokens=tokens, encoder=encoder, decoder=decoder,
                joiner=joiner, sample_rate=self._sample_rate,
                feature_dim=80, num_threads=threads, provider=provider,
                decoding_method=decoding_method,
                enable_endpoint_detection=True,
                rule1_min_trailing_silence=2.4,
                rule2_min_trailing_silence=1.2,
                rule3_min_utterance_length=5.0,
                model_type="", modeling_unit=modeling_unit,
            )
            if max_active_paths is not None:
                kwargs["max_active_paths"] = max_active_paths
            return sherpa_onnx.OnlineRecognizer.from_transducer(**kwargs)

        if self.use_gpu:
            try:
                r = _build("cuda", 1)
                self._emit_status("✓ 模型已加载 (CUDA GPU)")
                return r
            except Exception:
                self._emit_status("⚠ CUDA 不可用，回退 CPU")

        r = _build("cpu", os.cpu_count() or 4)
        self._emit_status("✓ 模型已加载 (CPU)")
        return r

    # ── 主循环 ──
    def run(self):
        recorder = None
        try:
            self._running = True
            self._emit_status("正在加载模型...")
            recognizer = self._create_recognizer()
            stream = recognizer.create_stream()
            self._emit_status("模型加载完成，开始监听...")

            recorder = self._create_recorder()
            chunk = int(self._sample_rate * 0.2)
            accumulated = ""

            while self._running:
                try:
                    data = recorder.record(numframes=chunk)
                except Exception:
                    continue
                data = data.flatten().astype(np.float32)

                stream.accept_waveform(self._sample_rate, data)
                while recognizer.is_ready(stream):
                    recognizer.decode_stream(stream)

                result = recognizer.get_result(stream)
                if result and result != accumulated:
                    accumulated = result
                    self._emit_partial(result)

                if recognizer.is_endpoint(stream):
                    if result.strip():
                        self._emit_final(result.strip())
                    recognizer.reset(stream)
                    accumulated = ""

        except Exception as e:
            logger.exception("识别线程异常")
            self._emit_status(f"错误: {e}")
        finally:
            if recorder is not None:
                try:
                    recorder.__exit__(None, None, None)
                except Exception:
                    pass
            self._emit_status("识别已停止")
            self._running = False

    # ── 音频源 ──
    def _create_recorder(self):
        return self._loopback() if self.source == "system" else self._microphone()

    def _microphone(self):
        mic = sc.default_microphone()
        r = mic.recorder(samplerate=self._sample_rate, channels=1,
                         blocksize=int(self._sample_rate * 0.2))
        r.__enter__()
        self._emit_status(f"麦克风已就绪 ({mic.name})")
        return r

    def _loopback(self):
        try:
            speaker_name = sc.default_speaker().name
        except Exception:
            speaker_name = ""
        all_mics = [m for m in sc.all_microphones(include_loopback=True)
                    if m.isloopback]
        matched = [m for m in all_mics
                   if speaker_name and (speaker_name in m.name or m.name in speaker_name)]
        others = [m for m in all_mics if m not in matched]
        candidates = matched + others
        if not candidates:
            raise RuntimeError("未找到 Loopback 内录设备")
        errors = []
        for mic in candidates:
            try:
                r = mic.recorder(samplerate=self._sample_rate, channels=1,
                                 blocksize=int(self._sample_rate * 0.2))
                r.__enter__()
                self._emit_status(f"系统音频内录已就绪 ({mic.name})")
                return r
            except Exception as e:
                errors.append(f"{mic.name}: {e}")
        raise RuntimeError("无法打开 Loopback:\n" + "\n".join(errors))

    # ── 停止：只设标志位，join 极短时间 ──
    def stop(self):
        self._running = False
        self.join(timeout=0.5)
