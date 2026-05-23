"""
模型下载工具
从 GitHub Releases 下载 Sherpa-ONNX 流式语音识别模型
支持中文、英文和中英双语模型
"""

import os
import sys
import tarfile
import requests
from pathlib import Path

# 模型配置：名称 -> (文件名, 模型类型)
MODELS = {
    "zh": {
        "name": "中文 Zipformer 流式模型",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23.tar.bz2",
        "filename": "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23.tar.bz2",
    },
    "en": {
        "name": "英文 Zipformer 流式模型",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-en-2023-02-21.tar.bz2",
        "filename": "sherpa-onnx-streaming-zipformer-en-2023-02-21.tar.bz2",
    },
    "bilingual": {
        "name": "中英双语 Zipformer 流式模型",
        "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2",
        "filename": "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2",
    },
}

# HuggingFace 镜像（国内用户下载更快）
HF_MIRROR = "https://hf-mirror.com"

HF_MODELS = {
    "zh": {
        "name": "中文 Zipformer 流式模型 (HF镜像)",
        "url": f"{HF_MIRROR}/csukuangfj/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23/resolve/main/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23.tar.bz2",
        "filename": "sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23.tar.bz2",
    },
    "en": {
        "name": "英文 Zipformer 流式模型 (HF镜像)",
        "url": f"{HF_MIRROR}/csukuangfj/sherpa-onnx-streaming-zipformer-en-2023-02-21/resolve/main/sherpa-onnx-streaming-zipformer-en-2023-02-21.tar.bz2",
        "filename": "sherpa-onnx-streaming-zipformer-en-2023-02-21.tar.bz2",
    },
    "bilingual": {
        "name": "中英双语 Zipformer 流式模型 (HF镜像)",
        "url": f"{HF_MIRROR}/csukuangfj/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/resolve/main/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2",
        "filename": "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20.tar.bz2",
    },
}


def download_with_progress(url: str, dest: str, desc: str) -> None:
    """带进度条的下载"""
    print(f"\n正在下载 {desc}...")
    print(f"URL: {url}")

    resp = requests.get(url, stream=True, timeout=120)
    total = int(resp.headers.get("content-length", 0))

    downloaded = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded / total * 100
                bar_len = 40
                filled = int(bar_len * downloaded / total)
                bar = "█" * filled + "░" * (bar_len - filled)
                mb_dl = downloaded / (1024 * 1024)
                mb_total = total / (1024 * 1024)
                print(f"\r  [{bar}] {pct:.1f}%  {mb_dl:.1f}/{mb_total:.1f} MB", end="")
    print()


def extract_tar_bz2(archive_path: str, dest_dir: str) -> str:
    """解压 tar.bz2 并返回解压后的目录名"""
    print(f"\n正在解压 {archive_path} -> {dest_dir}")
    with tarfile.open(archive_path, "r:bz2") as tar:
        # 获取顶层目录名
        top_dir = tar.getnames()[0].split("/")[0]
        tar.extractall(path=dest_dir, filter="data")

    extracted = os.path.join(dest_dir, top_dir)
    print(f"解压完成: {extracted}")
    return extracted


def download_model(lang: str, use_mirror: bool = False) -> bool:
    """下载指定语言的模型"""
    models = HF_MODELS if use_mirror else MODELS
    if lang not in models:
        print(f"不支持的模型语言: {lang}")
        print(f"可选: {', '.join(models.keys())}")
        return False

    info = models[lang]
    dest_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    lang_dir = os.path.join(dest_dir, lang)

    # 检查是否已存在
    if os.path.exists(lang_dir):
        tokens = os.path.join(lang_dir, "tokens.txt")
        has_encoder = any("encoder" in f.lower() for f in os.listdir(lang_dir))
        if os.path.exists(tokens) and has_encoder:
            print(f"模型 {lang} 已存在于 {lang_dir}，跳过下载。")
            return True

    os.makedirs(dest_dir, exist_ok=True)

    archive_path = os.path.join(dest_dir, info["filename"])

    # 下载
    try:
        download_with_progress(info["url"], archive_path, info["name"])
    except Exception as e:
        print(f"下载失败: {e}")
        if not use_mirror:
            print("尝试使用 HuggingFace 镜像重新下载...")
            return download_model(lang, use_mirror=True)
        return False

    # 解压
    try:
        extracted_dir = extract_tar_bz2(archive_path, dest_dir)
        # 重命名为 lang 目录
        if os.path.exists(lang_dir):
            import shutil
            shutil.rmtree(lang_dir)
        os.rename(extracted_dir, lang_dir)
        print(f"模型已安装到: {lang_dir}")
    except Exception as e:
        print(f"解压失败: {e}")
        return False

    # 清理压缩包
    try:
        os.remove(archive_path)
    except OSError:
        pass

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="下载 Sherpa-ONNX 流式语音识别模型")
    parser.add_argument(
        "--lang",
        type=str,
        default="all",
        choices=["zh", "en", "bilingual", "all"],
        help="下载的模型语言 (默认: all)",
    )
    parser.add_argument(
        "--mirror",
        action="store_true",
        help="使用 HuggingFace 镜像下载（国内推荐）",
    )
    args = parser.parse_args()

    langs = ["zh", "en", "bilingual"] if args.lang == "all" else [args.lang]

    success = True
    for lang in langs:
        if not download_model(lang, use_mirror=args.mirror):
            success = False

    if success:
        print("\n✓ 模型下载完成！")
    else:
        print("\n✗ 部分模型下载失败，请检查网络连接后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
