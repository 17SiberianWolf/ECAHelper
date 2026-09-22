@echo off
REM ECAHelper 一键启动（健壮版）
REM - 优先托管运行时（已含 flask 3.1.3 + openpyxl 3.1.5，离线可跑）；缺失则回退 venv
REM - 所有输出写入 startup.log；启动异常时 pause，避免黑窗一闪而过无痕迹
set PYTHON=C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe
set VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default
set ROOT=%~dp0
cd /d "%ROOT%"

set STARTED=0

"%PYTHON%" -c "import flask, openpyxl" >nul 2>&1 && (
    echo.
    echo ============================================================
    echo   ECAHelper 正在启动……
    echo   运行日志 : startup.log
    echo   浏览器   : 数秒后自动打开（或手动访问下方地址）
    echo   访问地址 : http://127.0.0.1:5000
    echo   停止服务 : 关闭本窗口 或 按 Ctrl+C
    echo ============================================================
    echo.
    "%PYTHON%" -u app.py > "%ROOT%startup.log" 2>&1 || pause
    set STARTED=1
)

if "%STARTED%"=="0" (
    if exist "%VENV%\Scripts\python.exe" (
        "%VENV%\Scripts\python.exe" -c "import flask, openpyxl" >nul 2>&1 && (
            echo.
            echo ============================================================
            echo   ECAHelper 正在启动（venv 运行时）……
            echo   运行日志 : startup.log
            echo   访问地址 : http://127.0.0.1:5000
            echo   停止服务 : 关闭本窗口 或 按 Ctrl+C
            echo ============================================================
            echo.
            "%VENV%\Scripts\python.exe" -u app.py > "%ROOT%startup.log" 2>&1 || pause
            set STARTED=1
        )
    )
)

if "%STARTED%"=="0" (
    echo [start] 未检测到 flask/openpyxl。请先双击 setup_env.bat 联网安装依赖，再运行本文件。
    echo 详细错误见 startup.log。
    pause
)
