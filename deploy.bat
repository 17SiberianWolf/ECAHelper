@echo off
REM ==========================================================================
REM  ECAHelper 一键部署（相对路径，整目录可搬迁）
REM  流程：检测 Python(>=3.10) -> 创建项目内 .venv -> 升级 pip
REM          -> pip install -r requirements.txt -> 调用 start.bat
REM ==========================================================================
setlocal enableextensions
cd /d "%~dp0"

set "PY="
set "PYARGS="

REM 优先 py -3（版本受控），其次系统 python
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
    echo.
    echo ============================================================
    echo   未检测到 Python。请先安装 Python 3.10 或更高版本：
    echo   https://www.python.org/downloads/
    echo   安装时请勾选 "Add Python to PATH"，完成后重新运行 deploy.bat。
    echo ============================================================
    echo.
    pause
    exit /b 1
)

REM 版本校验：需要 >= 3.10
"%PY%" %PYARGS% -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ============================================================
    echo   检测到的 Python 版本过低，需要 3.10 或更高版本。
    echo   当前版本：
    "%PY%" %PYARGS% --version
    echo   请升级 Python 后重新运行 deploy.bat。
    echo ============================================================
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [deploy] 创建虚拟环境 .venv ...
    "%PY%" %PYARGS% -m venv ".venv"
    if errorlevel 1 (
        echo [deploy] 创建 .venv 失败，请检查上方错误信息。
        pause
        exit /b 1
    )
)

echo [deploy] 升级 pip ...
".venv\Scripts\python.exe" -m pip install -U pip

echo [deploy] 安装运行依赖 (requirements.txt) ...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 (
    echo [deploy] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

echo [deploy] 部署完成，正在启动 ECAHelper ...
call "%~dp0start.bat"
endlocal
