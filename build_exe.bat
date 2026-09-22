@echo off
chcp 936 >nul 2>&1
REM ==========================================================================
REM  ECAHelper PyInstaller onedir 打包脚本
REM  产物：dist\ECAHelper\ECAHelper.exe
REM  随包复制 OriginSource\ 并在 exe 同级创建 data\exports\，便于整目录分发。
REM ==========================================================================
setlocal enableextensions
cd /d "%~dp0"

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

if not defined PY (
    echo [build] 未找到 .venv，请先运行 deploy.bat 或 setup_env.bat 创建环境。
    pause
    exit /b 1
)

REM 确保已安装 PyInstaller（缺失则自动安装）
"%PY%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [build] 未检测到 PyInstaller，正在安装 requirements-dev.txt ...
    "%PY%" -m pip install -r "requirements-dev.txt"
    if errorlevel 1 (
        echo [build] PyInstaller 安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)

echo [build] 开始打包（onedir）...
"%PY%" -m PyInstaller --noconfirm --clean ECAHelper.spec
if errorlevel 1 (
    echo [build] 打包失败，请查看上方日志。
    pause
    exit /b 1
)

echo [build] 复制 OriginSource 到 dist\ECAHelper ...
if exist "OriginSource" (
    xcopy "OriginSource" "dist\ECAHelper\OriginSource\" /E /I /Y >nul
)

echo [build] 创建 data\exports 目录 ...
if not exist "dist\ECAHelper\data\exports\" mkdir "dist\ECAHelper\data\exports"

echo.
echo ============================================================
echo   打包完成：dist\ECAHelper\ECAHelper.exe
echo   请将整个 dist\ECAHelper 目录（含 OriginSource 与 data）拷贝到目标机器运行。
echo ============================================================
echo.
pause
endlocal
