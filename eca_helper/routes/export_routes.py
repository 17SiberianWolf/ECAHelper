"""导出路由（系统设计书.md §5.3 / T12 / Q7）。

API：/api/export  POST {start, end, ..., format:'xlsx'|'csv', lang:'both'|'en'|'zh', title}
     返回 {path, filename}；文件已落盘 EXPORT_DIR，由前端下载。
"""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request, send_file

from eca_helper.db import ensure_db, get_connection
from eca_helper.queries import export

bp = Blueprint("export_routes", __name__)


@bp.route("/api/export", methods=["POST"])
def api_export():
    payload = request.get_json(silent=True) or {}
    if not payload.get("start") or not payload.get("end"):
        return jsonify({"error": "start / end 为必填"}), 400
    conn = get_connection()
    try:
        path, fname = export.export_from_request(conn, payload)
    finally:
        conn.close()
    return jsonify({"path": path, "filename": fname, "download": f"/api/export/download?file={fname}"})


@bp.route("/api/export/download")
def api_export_download():
    fname = request.args.get("file", "")
    if not fname or "/" in fname or "\\" in fname:
        return jsonify({"error": "invalid file"}), 400
    from config import EXPORT_DIR

    path = EXPORT_DIR / fname
    if not path.exists():
        return jsonify({"error": "file not found"}), 404
    return send_file(str(path), as_attachment=True, download_name=fname)
