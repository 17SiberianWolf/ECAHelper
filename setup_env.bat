@echo off
REM ECAHelper 环境准备：在 managed venv 中安装依赖（不污染全局运行时）
set PYTHON=C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe
set VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default
set ROOT=%~dp0

if not exist "%VENV%\Scripts\python.exe" (
    echo [setup] 创建 venv: %VENV%
    "%PYTHON%" -m venv "%VENV%"
)

echo [setup] 安装依赖 (flask / waitress / openpyxl)...
"%VENV%\Scripts\python.exe" -m pip install -U pip
"%VENV%\Scripts\python.exe" -m pip install -r "%ROOT%requirements.txt"

echo [setup] 完成。可运行 start.bat 启动。
pause
