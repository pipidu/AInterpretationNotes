@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo =====================================
echo   实时语音转文字 —— 环境安装
echo =====================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 创建虚拟环境
if exist ".venv" (
    echo [跳过] 虚拟环境已存在
) else (
    echo [1/3] 创建虚拟环境...
    python -m venv .venv
)

:: 安装依赖
echo [2/3] 安装 Python 依赖...
.venv\Scripts\pip.exe install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

:: 下载模型
echo [3/3] 下载语音识别模型...
.venv\Scripts\python.exe download_models.py --lang all

echo.
echo =====================================
echo   安装完成！
echo   双击 run.bat 启动应用
echo =====================================
pause
