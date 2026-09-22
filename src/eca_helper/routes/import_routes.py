"""导入相关路由（系统设计书.md §5.1 / T05 / R2-T03）。

提供：首页 / 导入页 / 导入 API / 目录文件清单 API。
导入 API 接受 {paths, mode} 调用 importer.import_files（paths 为空时导入 ORIGIN_DIR 全量）。
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from config import ORIGIN_DIR
from eca_helper.db import ensure_db, get_connection
from eca_helper.parsers import importer, normalizer
from eca_helper.parsers.excel_locator import should_skip

bp = Blueprint("import_routes", __name__)


def _safe_upload_name(name: str) -> str:
    """清洗上传文件名：仅去除路径成分与 Windows 非法字符，**保留中文**。

    不用 werkzeug 的 secure_filename——它会剥掉全部非 ASCII 字符，
    把「在管项目2026.08.xlsx」变成「2026.08.xlsx」，破坏同名幂等判断。
    """
    name = (name or "").replace("\\", "_").replace("/", "_")
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)
    name = name.strip().lstrip(".") or "upload.xlsx"
    return name


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


@bp.route("/api/import/upload", methods=["POST"])
def api_import_upload():
    """传统文件选择框上传导入（第二轮用户反馈）。

    前端用 ``<input type="file" multiple>`` 选文件后以 multipart/form-data 上传；
    后端把文件**以原文件名**落到临时目录再交给 importer——这样
    ``source_file == path.name`` 与既有批次同名，「已导入同名跳过」的幂等
    语义（Q4）完全不变。导入完成后清理临时目录。

    无论成功还是失败，都返回可供前端弹窗提示的结构：
        成功 -> ImportReport.to_dict() + {"uploaded": n}
        失败 -> {"error": "...", "uploaded": n, "failed_names": [...]}
    """
    fs = request.files.getlist("files") or request.files.getlist("file")
    if not fs:
        return jsonify({"error": "未选择任何文件", "uploaded": 0}), 400

    tmp = Path(tempfile.mkdtemp(prefix="eca_import_"))
    saved: list[Path] = []
    rejected: list[str] = []
    try:
        for f in fs:
            raw = f.filename or ""
            name = _safe_upload_name(raw)
            if not name.lower().endswith(".xlsx"):
                rejected.append(f"{raw}（仅支持 .xlsx）")
                continue
            if should_skip(name):
                rejected.append(f"{raw}（锁文件/主数据，自动跳过）")
                continue
            dest = tmp / name
            f.save(str(dest))
            saved.append(dest)

        if not saved:
            return jsonify(
                {"error": "没有可导入的文件", "uploaded": 0,
                 "rejected": rejected, "failed_names": rejected}
            ), 400

        report = importer.import_files([str(p) for p in saved], mode="skip")
        data = report.to_dict()
        data["uploaded"] = len(saved)
        if rejected:
            data["rejected"] = rejected
        return jsonify(data)
    except Exception as exc:  # noqa: BLE001 - 上传导入失败也要能给前端弹窗
        return jsonify(
            {"error": f"导入失败：{exc!r}", "uploaded": len(saved),
             "failed_names": rejected}
        ), 500
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
