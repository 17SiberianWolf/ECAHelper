@echo off
REM ==========================================================================
REM  ECAHelper 一键启动（相对路径解析 Python，整目录可搬迁）
REM  解析顺序：项目内 .venv  ->  系统 python  ->  py -3
REM  每个候选都必须通过 `import flask, openpyxl` 校验才会被采用。
REM  所有运行输出写入 startup.log；找不到可用环境时给出明确中文提示并 pause。
REM ==========================================================================
setlocal enableextensions
cd /d "%~dp0"

set "PY="
set "PYARGS="

REM 1) 项目内虚拟环境（随目录一起复制，故用 %~dp0 相对定位）
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -c "import flask, openpyxl" >nul 2>&1
    if not errorlevel 1 set "PY=%~dp0.venv\Scripts\python.exe"
)

REM 2) 系统 PATH 中的 python（校验依赖后再采用）
if not defined PY for /f "delims=" %%I in ('where python 2^>nul') do (
    if not defined PY (
        "%%I" -c "import flask, openpyxl" >nul 2>&1 && set "PY=%%I"
    )
)

REM 3) py -3 启动器（校验依赖后再采用）
if not defined PY for /f "delims=" %%I in ('where py 2^>nul') do (
    if not defined PY (
        "%%I" -3 -c "import flask, openpyxl" >nul 2>&1 && (set "PY=%%I" & set "PYARGS=-3")
    )
)

if not defined PY (
    echo.
    echo ============================================================
    echo   未找到可用的 Python 运行环境。
    echo   需要 Python 3.10 或更高版本，且已安装 flask / openpyxl 依赖。
    echo.
    echo   请先双击 deploy.bat 一键部署（自动创建 .venv 并安装依赖），
    echo   或前往 https://www.python.org/downloads/ 安装 Python 后重试。
    echo ============================================================
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   ECAHelper 正在启动……
echo   运行日志 : startup.log
echo   访问地址 : http://127.0.0.1:5000
echo   停止服务 : 关闭本窗口 或 按 Ctrl+C
echo ============================================================
echo.
"%PY%" %PYARGS% -u "src\app.py" > "%~dp0startup.log" 2>&1 || pause
endlocal
