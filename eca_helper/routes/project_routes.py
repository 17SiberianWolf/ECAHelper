"""项目工时查询路由（系统设计书.md §5.2 / T07）。

页面：/project
API  ：/api/query/project   {project_id, start, end, wbs_prefix}
选项：/api/options/projects  返回项目清单（供下拉）
"""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from eca_helper.db import ensure_db, get_connection
from eca_helper.queries import aggregate

bp = Blueprint("project_routes", __name__)


@bp.route("/project")
def project_page():
    ensure_db()
    conn = get_connection()
    try:
        lo, hi = aggregate.month_bounds(conn)
    finally:
        conn.close()
    return render_template("project_query.html", month_lo=lo, month_hi=hi)


@bp.route("/api/options/projects")
def api_options_projects():
    conn = get_connection()
    try:
        projects = aggregate.list_projects(conn)
    finally:
        conn.close()
    return jsonify(projects)


@bp.route("/api/query/project", methods=["POST"])
def api_query_project():
    payload = request.get_json(silent=True) or {}
    pid = (payload.get("project_id") or "").strip().upper()
    start = payload.get("start")
    end = payload.get("end")
    wbs_prefix = payload.get("wbs_prefix", "")
    if not pid or not start or not end:
        return jsonify({"error": "project_id / start / end 为必填"}), 400
    conn = get_connection()
    try:
        result = aggregate.aggregate_project(conn, pid, start, end, wbs_prefix)
        result["by_month"] = aggregate.fill_month_gaps(result["by_month"], start, end)
        result["project_name"] = aggregate.project_name_for(conn, pid)
        result["project_id"] = pid
    finally:
        conn.close()
    return jsonify(result)
