"""导入相关路由（系统设计书.md §5.1 / T05 / R2-T03）。

提供：首页 / 导入页 / 导入 API / 目录文件清单 API。
导入 API 接受 {paths, mode} 调用 importer.import_files（paths 为空时导入 ORIGIN_DIR 全量）。
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from config import ORIGIN_DIR
from eca_helper.db import ensure_db, get_connection
from eca_helper.parsers import importer, normalizer
from eca_helper.parsers.excel_locator import should_skip

bp = Blueprint("import_routes", __name__)


@bp.route("/")
@bp.route("/import")
def import_page():
    """导入页（首页）。"""
    ensure_db()
    return render_template("import.html", origin_dir=str(ORIGIN_DIR))


@bp.route("/api/import/candidates")
def api_import_candidates():
    """目录文件清单（只读）：供导入页勾选。

    返回 ORIGIN_DIR 下的 *.xlsx 清单，每项含：
        name（文件名）/ path（绝对路径）/ size / size_bytes /
        parsed_month（从文件名解析，可能为 None）/ imported / skippable / status。
    - 「已导入」判定依据 = import_batch 表中已存在同 source_file 记录（AC-05-7）；
    - 跳过规则沿用 config.LOCK_PREFIX(~$) 与 config.MASTER_DATA_HINTS（excel_locator.should_skip）；
    - status ∈ {pending, imported, skip}；按报告月份降序（None 排最后）。
    """
    conn = get_connection()
    try:
        rows = conn.execute("SELECT DISTINCT source_file FROM import_batch").fetchall()
        imported_files = {r["source_file"] for r in rows}
    finally:
        conn.close()

    files: list[dict] = []
    if ORIGIN_DIR.exists():
        for f in ORIGIN_DIR.rglob("*.xlsx"):
            name = f.name
            skippable = should_skip(name)
            imported = name in imported_files
            if skippable:
                status = "skip"
            elif imported:
                status = "imported"
            else:
                status = "pending"
            try:
                size = f.stat().st_size
            except OSError:
                size = 0
            files.append(
                {
                    "name": name,
                    "path": str(f.resolve()),
                    "size": size,
                    "size_bytes": size,
                    "parsed_month": normalizer.parse_month(name),
                    "imported": imported,
                    "skippable": skippable,
                    "status": status,
                }
            )

    # 报告月份降序；None（无月份）排最后（"" 最小，reverse=True 时落到末尾）。
    files.sort(key=lambda x: x["parsed_month"] or "", reverse=True)
    return jsonify({"origin_dir": str(ORIGIN_DIR), "files": files})


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
