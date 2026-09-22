@echo off
chcp 936 >nul 2>&1
REM ==========================================================================
REM  ECAHelper 环境准备：仅创建项目内 .venv 并安装依赖（不启动服务）
REM  相对路径解析 Python，整目录可搬迁。
REM ==========================================================================
setlocal enableextensions
cd /d "%~dp0"

set "PY="
set "PYARGS="

if not defined PY for /f "delims=" %%I in ('where py 2^>nul') do (
    if not defined PY (
        set "PY=%%I" & set "PYARGS=-3"
    )
)
if not defined PY for /f "delims=" %%I in ('where python 2^>nul') do (
    if not defined PY (
        set "PY=%%I"
    )
)

if not defined PY (
    echo [setup] 未检测到 Python 3.10+，请前往 https://www.python.org/downloads/ 安装。
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [setup] 创建虚拟环境 .venv ...
    "%PY%" %PYARGS% -m venv ".venv"
    if errorlevel 1 (
        echo [setup] 创建 .venv 失败。
        pause
        exit /b 1
    )
)

echo [setup] 升级 pip ...
".venv\Scripts\python.exe" -m pip install -U pip

echo [setup] 安装依赖 (requirements.txt) ...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"

echo [setup] 完成。可运行 start.bat 启动。
pause
endlocal
