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


@bp.route("/api/options/tasks")
def api_options_tasks():
    """任务候选（只读）：全部 task + 累计工时 + 行数，按累计工时降序。

    供综合检索页「任务类别」可搜索下拉使用（US-R2-03）。无静态截断。
    """
    conn = get_connection()
    try:
        tasks = aggregate.list_tasks(conn)
    finally:
        conn.close()
    return jsonify({"tasks": tasks})


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
        include_sub_organization=bool(payload.get("include_sub_organization", False)),
    )
    conn = get_connection()
    try:
        result = aggregate.search(conn, f)
        result["by_month"] = aggregate.fill_month_gaps(result["by_month"], start, end)
    finally:
        conn.close()
    return jsonify(result)


@bp.route("/api/search/facets", methods=["POST"])
def api_search_facets():
    """联动计数（只读）：在「其他维度已选条件」下，返回各维度候选值及其行数。

    前端据此给每个下拉项标注「当前其他条件下有 N 行」，并剔除零行候选，
    从机制上避免用户选到空组合。参数同 /api/query/search。
    """
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
        include_sub_organization=bool(payload.get("include_sub_organization", False)),
    )
    conn = get_connection()
    try:
        facets = aggregate.search_facets(conn, f)
    finally:
        conn.close()
    return jsonify(facets)
