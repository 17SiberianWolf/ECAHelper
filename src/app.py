"""ECAHelper 应用入口（重构设计书.md §3 / T01 / T03）。

职责：
    - 构建 Flask app（模板/静态目录由 config 的三态路径解析定位）；
    - 注册全部蓝图（导入/项目/员工/检索/质量/导出/图表）；
    - 启动期 ensure_db() 建库；
    - 日志与审计子系统（第二轮 T07）：create_app() 内先 setup_logging()，
      注册蓝图后 register_hooks(app)（每请求至多 1 条审计，仅落本机）；
    - 数据自举（T03，决策 5）：以完成标记 ``data/.auto_import.done`` 为门槛，
      标记缺失时**同步（阻塞）导入** OriginSource（skip 幂等，可自愈补齐半途
      失败的部分库），全部成功才写标记；失败仅记日志、不阻断服务；
    - 使用 Waitress 常驻（纯 Python，无 C 依赖）；
    - 端口固定 APP_PORT（被占用自动 +1），并自动打开浏览器。

三态运行（开发直跑 / 项目内 venv / PyInstaller 冻结）下的 sys.path：
    · 非冻结：把本文件所在目录（<root>/src）注入 sys.path[0]，
              使 `import config` / `from eca_helper... import ...` 生效；
    · 冻结：禁止手工注入（由 PyInstaller 引导器负责），故此处加 frozen 守卫。
"""

from __future__ import annotations

import logging
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

from eca_helper.db import ensure_db
from eca_helper.logging_setup import register_hooks, setup_logging
from eca_helper.parsers import importer
from eca_helper.routes import (
    chart_routes,
    employee_routes,
    export_routes,
    import_routes,
    log_routes,
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
    log_routes.bp,
)

# 自动导入“完成标记”：位于可写数据目录内（data/.auto_import.done）。
# 以标记是否存在作为自举门槛（取代旧的 is_empty 判定），使“半途失败的
# 部分库”在下次启动时能够自愈补齐（见 _bootstrap 说明）。
_AUTO_IMPORT_MARKER = config.DATA_DIR / ".auto_import.done"


def create_app() -> Flask:
    # 日志先于一切初始化（第二轮 T07）：文件 + 控制台双通道，随后才注册蓝图与挂钩。
    setup_logging()
    app = Flask(
        __name__,
        template_folder=str(config.TEMPLATE_DIR),
        static_folder=str(config.STATIC_DIR),
    )
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
    for bp in _BLUEPRINTS:
        app.register_blueprint(bp)
    # 请求挂钩（审计至多每请求 1 条）必须在蓝图注册之后挂载。
    register_hooks(app)
    return app


def _find_free_port(preferred: int) -> int:
    port = preferred
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            return port
        except OSError:
            port += 1
        finally:
            s.close()


def _write_auto_import_marker(log) -> None:
    """写入自动导入完成标记（失败仅记日志，绝不影响服务启动）。"""
    try:
        _AUTO_IMPORT_MARKER.parent.mkdir(parents=True, exist_ok=True)
        _AUTO_IMPORT_MARKER.write_text("done\n", encoding="utf-8")
        log(f"[ECAHelper] 已写入初始化完成标记：{_AUTO_IMPORT_MARKER}")
    except OSError as exc:  # noqa: BLE001 - 标记写入失败不影响服务
        log(f"[ECAHelper] 写入完成标记失败（不影响服务启动）：{exc!r}")


def _bootstrap(log) -> None:
    """启动自举：以「完成标记」为门槛同步（阻塞）导入，失败/半途中断可自愈。

    设计（健壮性修复）：
        - 门槛由旧的 ``is_empty()``（行数==0）改为完成标记
          ``config.DATA_DIR/.auto_import.done``。旧的 is_empty 判定会把
          “半途失败的部分库”误判为非空，导致此后每次启动都跳过导入、永久
          停留于不完整数据；
        - **标记不存在** -> 执行 ``import_directory(ORIGIN_DIR, mode="skip")``
          （skip 模式幂等：已导入文件自动跳过，从而把“部分库”缺失的文件补齐）；
          返回后**仅当 report.files_failed == 0 且无失败文件**时才写入标记；
        - **标记存在** -> 直接跳过（保持“不重复导入、不自动抓取新月份”语义）；
        - **ORIGIN_DIR 不存在** -> 打印“未找到源数据目录，跳过自动导入”并写入
          标记。取舍：写入标记可避免每次启动都空扫目录；代价是日后若再补入
          OriginSource，将不会自动导入（需手动导入，或先删除该标记）；此取舍
          是为“迁移到新 PC 首跑不卡顿”而有意为之；
        - 全程**同步**执行 + 整体 try/except，任何失败只记日志、绝不阻断服务。

    顺序（决策 5）：先于浏览器计时器与 waitress.serve。
    """
    try:
        config.ensure_dirs()
        ensure_db()

        if _AUTO_IMPORT_MARKER.exists():
            log("[ECAHelper] 已完成初始化（.auto_import.done），跳过自动导入。")
            return

        origin = config.ORIGIN_DIR
        if not origin.exists():
            log(f"[ECAHelper] 未找到源数据目录 {origin}，跳过自动导入。")
            _write_auto_import_marker(log)
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
        if d["files_failed"] == 0 and not d["failed_files"]:
            _write_auto_import_marker(log)
        else:
            log(
                f"[ECAHelper] 存在 {d['files_failed']} 个失败文件，本次不写入完成标记；"
                "下次启动将自动重试补齐。"
            )
    except Exception as exc:  # noqa: BLE001 - 自举失败不得阻断服务
        log(f"[ECAHelper] 自动导入失败（不影响服务启动）：{exc!r}")


def main() -> None:
    # 启动日志同时输出到 stdout（start.bat 依赖重定向生成 startup.log）与文件日志。
    setup_logging()
    sys_logger = logging.getLogger("eca.system")

    def log(msg: str) -> None:
        print(msg, flush=True)
        try:
            sys_logger.info(msg)
        except Exception:  # noqa: BLE001 - 日志失败不得影响启动
            pass

    log("=" * 64)
    log(f"[ECAHelper] 数据目录 : {config.APP_DIR}")
    log(f"[ECAHelper] 数据库   : {config.DB_PATH}")

    # 数据自举（完成标记门槛，标记缺失即幂等补齐）：同步执行，
    # 先于浏览器计时器与 waitress.serve（决策 5）。
    _bootstrap(log)

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
