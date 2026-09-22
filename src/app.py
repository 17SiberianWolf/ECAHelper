"""ECAHelper 应用入口（重构设计书.md §3 / T01 / T03）。

职责：
    - 构建 Flask app（模板/静态目录由 config 的三态路径解析定位）；
    - 注册全部蓝图（导入/项目/员工/检索/质量/导出/图表）；
    - 启动期 ensure_db() 建库；
    - 空库自举：DB 为空且存在 OriginSource 时**同步（阻塞）导入**（T03，
      决策 5：保证首次数据完整可见），失败仅记日志、不阻断服务；
    - 使用 Waitress 常驻（纯 Python，无 C 依赖）；
    - 端口固定 APP_PORT（被占用自动 +1），并自动打开浏览器。

三态运行（开发直跑 / 项目内 venv / PyInstaller 冻结）下的 sys.path：
    · 非冻结：把本文件所在目录（<root>/src）注入 sys.path[0]，
              使 `import config` / `from eca_helper... import ...` 生效；
    · 冻结：禁止手工注入（由 PyInstaller 引导器负责），故此处加 frozen 守卫。
"""

from __future__ import annotations

import socket
import sys
import threading
import webbrowser
from pathlib import Path

# 非冻结时注入 src/ 到 sys.path，保证顶层模块名 `config` / `eca_helper` 可导入。
if not getattr(sys, "frozen", False):
    SRC_DIR = Path(__file__).resolve().parent
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

import eca_helper  # noqa: F401  确保 src/ 注入 sys.path
import config
from flask import Flask

from eca_helper.db import ensure_db, is_empty
from eca_helper.parsers import importer
from eca_helper.routes import (
    chart_routes,
    employee_routes,
    export_routes,
    import_routes,
    project_routes,
    quality_routes,
    search_routes,
)

_BLUEPRINTS = (
    import_routes.bp,
    project_routes.bp,
    employee_routes.bp,
    search_routes.bp,
    quality_routes.bp,
    export_routes.bp,
    chart_routes.bp,
)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(config.TEMPLATE_DIR),
        static_folder=str(config.STATIC_DIR),
    )
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
    for bp in _BLUEPRINTS:
        app.register_blueprint(bp)
    return app


def _find_free_port(preferred: int) -> int:
    port = preferred
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            port += 1


def _bootstrap_if_empty(log) -> None:
    """首次启动自举：库为空且存在 OriginSource 时同步（阻塞）导入。

    顺序（决策 5）：ensure_dirs() -> ensure_db() -> is_empty() ->
    import_directory(ORIGIN_DIR, mode="skip")。全程 try/except 包裹，
    任何失败只写日志、绝不阻断服务启动。
    """
    try:
        config.ensure_dirs()
        db_path = ensure_db()
        if not is_empty(db_path):
            log("[ECAHelper] 数据库已有数据，跳过自动导入。")
            return
        origin = config.ORIGIN_DIR
        if not origin.exists():
            log(f"[ECAHelper] 未找到源数据目录 {origin}，跳过自动导入。")
            return
        log(f"[ECAHelper] 首次运行：正在从 {origin} 自动导入数据，请稍候……")
        report = importer.import_directory(str(origin), mode="skip")
        d = report.to_dict()
        log(
            "[ECAHelper] 自动导入完成："
            f"文件总数 {d['files_total']}，导入 {d['files_imported']}，"
            f"跳过 {d['files_skipped']}，失败 {d['files_failed']}；"
            f"新增明细 {d['new_rows']} 行（重复 {d['duplicate_rows']}，"
            f"异常 {d['anomaly_rows']}，0 工时 {d['zero_rows']}）。"
        )
    except Exception as exc:  # noqa: BLE001 - 自举失败不得阻断服务
        log(f"[ECAHelper] 自动导入失败（不影响服务启动）：{exc!r}")


def main() -> None:
    def log(msg: str) -> None:
        print(msg, flush=True)

    log("=" * 64)
    log(f"[ECAHelper] 数据目录 : {config.APP_DIR}")
    log(f"[ECAHelper] 数据库   : {config.DB_PATH}")

    # 空库自举：同步执行，先于浏览器计时器与 waitress.serve（决策 5）
    _bootstrap_if_empty(log)

    app = create_app()
    port = _find_free_port(config.APP_PORT)
    log(f"[ECAHelper] 启动于 http://127.0.0.1:{port}/")

    def open_browser() -> None:
        try:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        except Exception:  # noqa: BLE001 - 打开浏览器失败不影响服务
            pass

    threading.Timer(1.2, open_browser).start()

    try:
        import waitress

        waitress.serve(app, host="127.0.0.1", port=port)
    except ImportError:
        # 退回开发服务器（仍可用，仅提示）
        log("[ECAHelper] 未安装 waitress，使用 Flask 开发服务器（生产建议 waitress）。")
        app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
