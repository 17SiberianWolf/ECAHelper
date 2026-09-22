"""综合检索路由（系统设计书.md §4.7 综合检索 / T07）。

页面：/search
API  ：/api/query/search  {start, end, organization?, cost_center?, task?, resource_id?, project_id?, include_empty_project?}
选项：/api/options/filters 返回组织 / 成本中心 清单（供下拉）
"""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from eca_helper.db import ensure_db, get_connection
from eca_helper.queries import aggregate
from eca_helper.queries.aggregate import QueryFilter

bp = Blueprint("search_routes", __name__)


@bp.route("/search")
def search_page():
    ensure_db()
    conn = get_connection()
    try:
        lo, hi = aggregate.month_bounds(conn)
    finally:
        conn.close()
    return render_template("search.html", month_lo=lo, month_hi=hi)


@bp.route("/api/options/filters")
def api_options_filters():
    conn = get_connection()
    try:
        orgs = aggregate.list_organizations(conn)
        ccs = aggregate.list_cost_centers(conn)
    finally:
        conn.close()
    return jsonify({"organizations": orgs, "cost_centers": ccs})


@bp.route("/api/query/search", methods=["POST"])
def api_query_search():
    payload = request.get_json(silent=True) or {}
    start = payload.get("start")
    end = payload.get("end")
    if not start or not end:
        return jsonify({"error": "start / end 为必填"}), 400
    f = QueryFilter(
        report_month_start=start,
        report_month_end=end,
        organization=(payload.get("organization") or None),
        cost_center=(payload.get("cost_center") or None),
        task=(payload.get("task") or None),
        resource_id=(payload.get("resource_id") or None),
        project_id=(payload.get("project_id") or None),
        include_empty_project=bool(payload.get("include_empty_project", False)),
    )
    conn = get_connection()
    try:
        result = aggregate.search(conn, f)
        result["by_month"] = aggregate.fill_month_gaps(result["by_month"], start, end)
    finally:
        conn.close()
    return jsonify(result)
