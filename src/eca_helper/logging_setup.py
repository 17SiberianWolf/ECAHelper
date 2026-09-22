"""日志配置与 Flask 请求挂钩（第二轮 T07 / 增量设计书 §6.1 / §6.3）。

设计要点（务必遵守）：
    - 根 logger 名 ``"eca"``，``propagate=False``；子 logger 用
      ``logging.getLogger("eca.xxx")``（如 ``eca.system`` / ``eca.audit``）；
    - **文件 + 控制台双通道**：
        · ``TimedRotatingFileHandler`` 落 ``config.LOG_DIR/eca.log``（按天滚动、保留 30 天）；
        · 另加 ``StreamHandler(sys.stdout)`` —— start.bat 依赖重定向 stdout 生成
          startup.log，故控制台通道必须保留；
    - request_id 用 ``contextvars.ContextVar`` 保存，经 ``logging.Filter`` 写入
      ``record.request_id``（缺失补 "-"，避免 formatter KeyError）；
    - 日志消息统一**中文**；级别默认 INFO，可用环境变量 ``ECA_LOG_LEVEL`` 覆盖；
    - 隐私红线（AC-07-5）：**绝不创建任何网络/远程 handler**，日志仅落本机。

审计写入时机（每请求至多 1 条）：
    before_request  → 生成 request_id、记 INFO「请求开始」
    after_request   → 未被 errorhandler 标记过时写 1 条 result=ok
    errorhandler    → 写 1 条 result=fail（含堆栈）并标记 g._audit_done=True
"""

from __future__ import annotations

import contextvars
import logging
import logging.handlers
import time
import traceback
import uuid
from pathlib import Path

from flask import g, jsonify, request

import config
from eca_helper.services import audit_service

_LOGGER_NAME = "eca"
_LOG_FILE_NAME = "eca.log"
_DEFAULT_REQUEST_ID = "-"
_MAX_DETAIL = 4000

# 一次请求的 request_id（贯穿文件日志与审计表）
_req_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=_DEFAULT_REQUEST_ID
)

# 需要记录的页面路径（GET）
_PAGE_PATHS = ("/", "/import", "/project", "/employee", "/search", "/quality", "/logs")
# 需要记录的 API 前缀
_API_PREFIXES = (
    "/api/query/",
    "/api/import",
    "/api/export",
    "/api/quality/",
    "/api/logs/",
)
# 明确不记录的前缀/路径
_SKIP_PATHS = ("/static/", "/favicon.ico", "/api/export/download")


class _RequestIdFilter(logging.Filter):
    """把 ContextVar 里的 request_id 注入 LogRecord（缺失补 "-"）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rid = _req_id.get()
        except Exception:  # noqa: BLE001 - 取不到就用占位符，绝不影响日志
            rid = _DEFAULT_REQUEST_ID
        if not rid:
            rid = _DEFAULT_REQUEST_ID
        record.request_id = rid
        return True


def get_logger(name: str = _LOGGER_NAME) -> logging.Logger:
    """取 ``eca`` 体系下的 logger。传入 ``"eca.system"`` 或 ``"system"`` 均可。"""
    if not name or name == _LOGGER_NAME:
        return logging.getLogger(_LOGGER_NAME)
    return logging.getLogger(name if name.startswith(_LOGGER_NAME) else f"{_LOGGER_NAME}.{name}")


def set_request_id(value: str) -> None:
    """设置当前上下文的 request_id。"""
    _req_id.set(value or _DEFAULT_REQUEST_ID)


def get_request_id() -> str:
    """取当前上下文的 request_id（缺失返回 "-"）。"""
    try:
        return _req_id.get() or _DEFAULT_REQUEST_ID
    except Exception:  # noqa: BLE001 - 绝不因取 request_id 失败而抛错
        return _DEFAULT_REQUEST_ID


def _resolve_level(level: str | None = None) -> int:
    """把级别名解析为 logging 级别；无法识别时回退 INFO。"""
    name = str(level or config.LOG_LEVEL or "INFO").upper()
    lvl = getattr(logging, name, None)
    return lvl if isinstance(lvl, int) else logging.INFO


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(module)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def setup_logging(level: str | None = None) -> logging.Logger:
    """配置 ``eca`` logger（文件 + 控制台双通道），并做过期日志兜底清理。

    可重复调用：会先摘除并关闭旧 handler 再重建。任何失败只警告、绝不阻断启动。
    """
    lvl = _resolve_level(level)
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(lvl)
    logger.propagate = False

    for old in list(logger.handlers):
        logger.removeHandler(old)
        try:
            old.close()
        except Exception:  # noqa: BLE001 - 关闭失败无需处理
            pass

    fmt = _build_formatter()
    rid_filter = _RequestIdFilter()

    # ---- 通道 1：文件（按天滚动，保留 30 天）----
    file_ok = False
    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.TimedRotatingFileHandler(
            filename=str(config.LOG_DIR / _LOG_FILE_NAME),
            when="midnight",
            interval=1,
            backupCount=config.LOG_RETENTION_DAYS,
            encoding="utf-8",
            delay=True,
        )
        fh.suffix = "%Y-%m-%d"
        fh.setLevel(lvl)
        fh.setFormatter(fmt)
        fh.addFilter(rid_filter)
        logger.addHandler(fh)
        file_ok = True
    except Exception as exc:  # noqa: BLE001 - Windows 下轮转可能撞文件占用 → 降级
        try:
            fh2 = logging.FileHandler(
                str(config.LOG_DIR / _LOG_FILE_NAME), encoding="utf-8"
            )
            fh2.setLevel(lvl)
            fh2.setFormatter(fmt)
            fh2.addFilter(rid_filter)
            logger.addHandler(fh2)
            file_ok = True
            logger.warning("按天滚动日志初始化失败，已降级为普通文件日志：%r", exc)
        except Exception as exc2:  # noqa: BLE001 - 双通道都失败也只能继续
            logger.warning("文件日志初始化失败（仅保留控制台日志）：%r", exc2)

    # ---- 通道 2：控制台（start.bat 依赖 stdout 重定向生成 startup.log）----
    try:
        sh = logging.StreamHandler(sys_stdout())
        sh.setLevel(lvl)
        sh.setFormatter(fmt)
        sh.addFilter(rid_filter)
        logger.addHandler(sh)
    except Exception as exc:  # noqa: BLE001 - 控制台失败不影响主流程
        logger.warning("控制台日志初始化失败：%r", exc)

    # 第三方降噪（仅开发服务器回退时存在）
    try:
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
    except Exception:  # noqa: BLE001
        pass

    if file_ok:
        _prune_old_logs(logger)
    return logger


def sys_stdout():
    """取 stdout 流（单独封装便于冻结态与测试环境差异）。"""
    import sys

    return sys.stdout


def _prune_old_logs(logger: logging.Logger) -> None:
    """启动兜底清理：删除 mtime 早于 now - LOG_RETENTION_DAYS 的 eca.log.* 文件。

    防止停机跨天导致 TimedRotatingFileHandler 漏删的历史文件堆积。失败仅警告。
    """
    try:
        cutoff = time.time() - config.LOG_RETENTION_DAYS * 86400
        base = Path(config.LOG_DIR)
        if not base.exists():
            return
        for f in base.glob(_LOG_FILE_NAME + ".*"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    logger.warning("已清理过期日志文件：%s", f.name)
            except Exception as exc:  # noqa: BLE001 - 单文件清理失败不影响其余
                logger.warning("清理过期日志文件失败（忽略）：%s %r", f.name, exc)
    except Exception as exc:  # noqa: BLE001 - 清理整体失败只警告
        logger.warning("日志清理失败（忽略）：%r", exc)


# ---------------------------------------------------------------------------
# 请求挂钩
# ---------------------------------------------------------------------------
def _should_log() -> bool:
    """判断当前请求是否纳入审计/日志记录。"""
    try:
        path = request.path or ""
    except Exception:  # noqa: BLE001 - 无请求上下文（如离线脚本）时不记录
        return False
    if request.method == "OPTIONS":
        return False
    if path.startswith(_SKIP_PATHS) or path in ("/favicon.ico",):
        return False
    if path.startswith(_API_PREFIXES):
        return True
    if request.method == "GET" and path in _PAGE_PATHS:
        return True
    return False


def _action_from_endpoint() -> str:
    """由 endpoint 推导 action：``api_query_project`` -> ``query.project``。"""
    endpoint = (request.endpoint or "").split(".")[-1]
    endpoint = endpoint.strip("_")
    if not endpoint:
        return "system.unknown"
    if endpoint.startswith("api_"):
        return endpoint[len("api_"):].replace("_", ".") or endpoint
    return endpoint.replace("_", ".")


def _category_for(path: str) -> str:
    if path.startswith("/api/query/"):
        return "query"
    if path.startswith("/api/import"):
        return "import"
    if path.startswith("/api/export"):
        return "export"
    if path.startswith("/api/quality/"):
        return "quality"
    return "system"


def _extract_target() -> str | None:
    """取请求参数里的关键对象（项目号 / 人员ID / 文件名），无则 None。"""
    payload: dict = {}
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            payload = request.get_json(silent=True) or {}
        except Exception:  # noqa: BLE001 - 解析失败按无 body 处理
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
    for key in (
        "project_id",
        "resource_id",
        "organization",
        "cost_center",
        "task",
        "category",
        "paths",
        "file",
    ):
        val = payload.get(key)
        if val is None:
            val = request.args.get(key)
        if val in (None, "", []):
            continue
        if isinstance(val, (list, tuple)):
            val = ",".join(str(x) for x in val[:3])
        return str(val)[:200]
    return None


def register_hooks(app) -> None:
    """注册 before_request / after_request / errorhandler 三个挂钩。"""

    logger = get_logger("eca.request")

    @app.before_request
    def _before_request() -> None:  # noqa: ANN202 - Flask 挂钩无需返回
        rid = uuid.uuid4().hex[:12]
        set_request_id(rid)
        g.request_id = rid
        g._t0 = time.perf_counter()
        g._audit_done = False
        if _should_log():
            logger.info("请求开始 %s %s", request.method, request.path)

    @app.after_request
    def _after_request(resp):
        try:
            if getattr(g, "_audit_done", False):
                return resp
            if not _should_log():
                return resp
            t0 = getattr(g, "_t0", None)
            duration_ms = int((time.perf_counter() - t0) * 1000) if t0 is not None else None
            path = request.path or ""
            audit_service.write_audit(
                category=_category_for(path),
                action=_action_from_endpoint(),
                level="INFO",
                target=_extract_target(),
                result="ok",
                status_code=resp.status_code,
                duration_ms=duration_ms,
                request_id=getattr(g, "request_id", None) or get_request_id(),
                message=f"{request.method} {path} 处理完成",
            )
            logger.info(
                "请求完成 %s %s 状态码=%s 耗时=%sms",
                request.method,
                path,
                resp.status_code,
                duration_ms,
            )
        except Exception as exc:  # noqa: BLE001 - 审计失败绝不影响响应
            try:
                logger.warning("审计写入失败（不影响响应）：%r", exc)
            except Exception:  # noqa: BLE001
                pass
        return resp

    @app.errorhandler(Exception)
    def _on_error(exc):  # noqa: ANN201 - 返回响应对象
        # HTTPException（400/404 等）交给 Flask 既有处理，保持原响应语义
        try:
            from werkzeug.exceptions import HTTPException

            if isinstance(exc, HTTPException):
                return exc
        except Exception:  # noqa: BLE001 - 判型失败则按普通异常处理
            pass

        tb = traceback.format_exc()
        rid = getattr(g, "request_id", None) or get_request_id()
        g._audit_done = True
        try:
            path = request.path or ""
            audit_service.write_audit(
                category=_category_for(path),
                action=_action_from_endpoint(),
                level="ERROR",
                target=_extract_target(),
                result="fail",
                status_code=500,
                duration_ms=None,
                request_id=rid,
                message=f"{request.method} {path} 处理异常：{exc!r}",
                detail=tb[:_MAX_DETAIL],
            )
        except Exception as write_exc:  # noqa: BLE001 - 双重兜底，绝不抛出
            try:
                logger.warning("异常审计写入失败（不影响响应）：%r", write_exc)
            except Exception:  # noqa: BLE001
                pass
        logger.error("请求异常 %s %s：%s", request.method, request.path, exc, exc_info=True)
        return jsonify({"error": f"服务器内部错误：{exc!r}"}), 500
