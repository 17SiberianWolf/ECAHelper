# -*- mode: python ; coding: utf-8 -*-
"""ECAHelper PyInstaller 规格文件（唯一打包真源，onedir 模式）。

要点（见 重构设计书.md §4.4）：
  · onedir（非 onefile）：启动快、DB 落盘位置明确、便于把 OriginSource 放旁边。
  · console=True：保留控制台，便于观察 startup.log 与报错（单机单人场景）。
  · 只读资源（web/templates、web/static、schema.sql）随包进 _MEIPASS；
    其中 schema.sql 落到 bundle 的 ``eca_helper/schema.sql``，与
    config.SCHEMA_PATH 的冻结分支对应。
  · pathex=['src'] 让分析器把顶层模块 config 与包 eca_helper 收集进包。
  · hiddenimports：waitress（app.py 中在 try 内 import，静态分析可能漏）
    与 openpyxl（大量使用）。
  · DB / exports / OriginSource **不打进包**：由 build_exe.bat 复制到 exe 同级，
    运行期由 config 解析到 exe 目录（可写数据根）。

CLI 等价（手动构建时参考）：
    pyinstaller --noconfirm --clean --onedir --name ECAHelper --paths src ^
        --add-data "web\\templates;web\\templates" ^
        --add-data "web\\static;web\\static" ^
        --add-data "src\\eca_helper\\schema.sql;eca_helper" ^
        --hidden-import waitress --hidden-import openpyxl src\\app.py
"""

a = Analysis(
    ['src/app.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('web/templates', 'web/templates'),
        ('web/static', 'web/static'),
        # 注意：datas 的第 2 项是「目标目录」；文件会被放入该目录下（保持同名）。
        # 故此处写 'eca_helper'，最终落点为 _MEIPASS/eca_helper/schema.sql。
        ('src/eca_helper/schema.sql', 'eca_helper'),
    ],
    hiddenimports=['waitress', 'openpyxl'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ECAHelper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ECAHelper',
)
