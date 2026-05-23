@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ================================
echo   实时语音转文字
echo   Real-time Speech to Text
echo ================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境，请先运行 install.bat 安装依赖
    pause
    exit /b 1
)

if not exist "models\zh\tokens.txt" (
    echo [提示] 中文模型未安装，正在下载...
    .venv\Scripts\python.exe download_models.py --lang zh
)

if not exist "models\en\tokens.txt" (
    echo [提示] 英文模型未安装，正在下载...
    .venv\Scripts\python.exe download_models.py --lang en
)

echo 正在启动应用...
.venv\Scripts\python.exe main.py

pause
