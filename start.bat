@echo off
REM ECAHelper 一键启动：优先 venv，缺失/损坏则回退 managed runtime（离线也能跑）
set PYTHON=C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe
set VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default
set ROOT=%~dp0
cd /d "%ROOT%"

if exist "%VENV%\Scripts\python.exe" (
    "%VENV%\Scripts\python.exe" -c "import flask" >nul 2>&1 && (
        echo [start] 使用 venv 启动 ECAHelper...
        "%VENV%\Scripts\python.exe" "%ROOT%app.py"
        goto :eof
    )
)

echo [start] venv 不可用或缺失 flask，回退到 managed runtime 启动...
echo [start] （如需隔离环境，请先运行 setup_env.bat 联网安装依赖）
"%PYTHON%" "%ROOT%app.py"
pause
