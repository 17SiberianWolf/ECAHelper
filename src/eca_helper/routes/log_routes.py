"""系统日志页与日志查询/导出 API（第二轮 T07 / 增量设计书 §6.5 / §4.2.5）。

页面：GET /logs
API ：GET /api/logs/query   —— 时间范围/级别/类别/关键词/成败 筛选 + 服务端分页，
                                响应键名固定为 items
      GET /api/logs/export  —— 同筛选条件（不含分页）导出 CSV，
                                复用 export_routes 的 /api/export/download 下载

每个请求独立 get_connection() / close()（与 routes/search_routes.py 一致）。
"""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from eca_helper.db import ensure_db, get_connection
from eca_helper.services import audit_service

bp = Blueprint("log_routes", __name__)

_DEFAULT_PAGE_SIZE = 50


def _arg(key: str, default: str = "") -> str:
    return (request.args.get(key) or default).strip()


def _filters_from_args(include_paging: bool = True) -> dict:
    """把查询串解析为 audit_service 的筛选字典。"""
    f: dict = {
        "start": _arg("start"),
        "end": _arg("end"),
        "level": _arg("level"),
        "category": _arg("category"),
        "keyword": _arg("keyword"),
    }
    ok = _arg("ok")
    if ok in ("ok", "fail"):
        f["result"] = ok
    if include_paging:
        f["page"] = _arg("page", "1")
        f["page_size"] = _arg("page_size", str(_DEFAULT_PAGE_SIZE))
    return f


@bp.route("/logs")
def logs_page():
    """系统日志页面。"""
    ensure_db()
    return render_template("logs.html", active="logs")


@bp.route("/api/logs/query")
def api_logs_query():
    """审计日志查询（服务端分页）。"""
    f = _filters_from_args(include_paging=True)
    conn = get_connection()
    try:
        total, items = audit_service.query_logs(f, conn=conn)
        page, page_size = audit_service.page_of(f)
    finally:
        conn.close()
    return jsonify({"total": total, "page": page, "page_size": page_size, "items": items})


@bp.route("/api/logs/export")
def api_logs_export():
    """审计日志导出 CSV（全部命中，不分页）。"""
    f = _filters_from_args(include_paging=False)
    conn = get_connection()
    try:
        path, filename = audit_service.export_logs_csv(f, conn=conn)
    finally:
        conn.close()
    return jsonify(
        {
            "path": path,
            "filename": filename,
            "download": f"/api/export/download?file={filename}",
        }
    )
