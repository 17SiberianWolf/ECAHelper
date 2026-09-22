"""数据质量面板路由（系统设计书.md §8 / T08 / Q3）。

页面：/quality
API  ：/api/quality/summary            质量指标汇总
      /api/quality/detail?category=... 明细下钻
      /api/quality/exclusion           POST {category, excluded} 勾选排除持久化
"""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from eca_helper.db import ensure_db, get_connection
from eca_helper.services import quality_service

bp = Blueprint("quality_routes", __name__)

_VALID = ("duplicate", "anomaly", "zero", "empty_rid")


@bp.route("/quality")
def quality_page():
    ensure_db()
    return render_template("quality.html")


@bp.route("/api/quality/summary")
def api_quality_summary():
    conn = get_connection()
    try:
        summary = quality_service.quality_summary(conn)
    finally:
        conn.close()
    return jsonify(summary)


@bp.route("/api/quality/detail")
def api_quality_detail():
    category = request.args.get("category", "")
    try:
        limit = int(request.args.get("limit", 500))
    except ValueError:
        limit = 500
    if category not in _VALID:
        return jsonify({"error": "unknown category"}), 400
    conn = get_connection()
    try:
        rows = quality_service.detail_rows(conn, category, limit)
    finally:
        conn.close()
    return jsonify({"category": category, "rows": rows})


@bp.route("/api/quality/exclusion", methods=["POST"])
def api_quality_exclusion():
    payload = request.get_json(silent=True) or {}
    category = payload.get("category", "")
    excluded = bool(payload.get("excluded", False))
    if category not in _VALID:
        return jsonify({"error": "unknown category"}), 400
    conn = get_connection()
    try:
        n = quality_service.set_category_exclusion(conn, category, excluded)
        summary = quality_service.quality_summary(conn)
    finally:
        conn.close()
    return jsonify({"category": category, "excluded": excluded, "written": n, "summary": summary})
