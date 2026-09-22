"""导入相关路由（系统设计书.md §5.1 / T05）。

提供：首页 / 导入页 / 导入 API。API 接受 {paths, mode} 调用 importer.import_files。
默认 paths 为空时导入 ORIGIN_DIR 全量。
"""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from config import ORIGIN_DIR
from eca_helper.db import ensure_db
from eca_helper.parsers import importer

bp = Blueprint("import_routes", __name__)


@bp.route("/")
@bp.route("/import")
def import_page():
    """导入页（首页）。"""
    ensure_db()
    return render_template("import.html", origin_dir=str(ORIGIN_DIR))


@bp.route("/api/import", methods=["POST"])
def api_import():
    """执行导入。

    请求体 JSON: {"paths": [可选目录/文件], "mode": "skip"|"overwrite"|"copy"}
    返回 ImportReport.to_dict()。
    """
    payload = request.get_json(silent=True) or {}
    paths = payload.get("paths") or [str(ORIGIN_DIR)]
    mode = payload.get("mode", "skip")
    if mode not in ("skip", "overwrite", "copy"):
        mode = "skip"
    report = importer.import_files(paths, mode=mode)
    return jsonify(report.to_dict())
