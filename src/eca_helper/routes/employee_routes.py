"""员工工时查询路由（系统设计书.md §4.7 员工差异 / T07）。

页面：/employee
API  ：/api/query/employee  {resource_id 或 q(自由文本), start, end}
选项：/api/options/persons   返回人员清单（含 canonical 名）
"""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from config import UNKNOWN_RESOURCE
from eca_helper.db import ensure_db, get_connection
from eca_helper.queries import aggregate
from eca_helper.services import person_service

bp = Blueprint("employee_routes", __name__)


@bp.route("/employee")
def employee_page():
    ensure_db()
    conn = get_connection()
    try:
        lo, hi = aggregate.month_bounds(conn)
    finally:
        conn.close()
    return render_template("employee_query.html", month_lo=lo, month_hi=hi, unknown=UNKNOWN_RESOURCE)


@bp.route("/api/options/persons")
def api_options_persons():
    conn = get_connection()
    try:
        persons = person_service.list_persons(conn, limit=5000)
    finally:
        conn.close()
    return jsonify(persons)


@bp.route("/api/query/employee", methods=["POST"])
def api_query_employee():
    payload = request.get_json(silent=True) or {}
    start = payload.get("start")
    end = payload.get("end")
    if not start or not end:
        return jsonify({"error": "start / end 为必填"}), 400

    rid = (payload.get("resource_id") or "").strip().upper()
    q = (payload.get("q") or "").strip()
    if not rid and q:
        conn0 = get_connection()
        try:
            hits = person_service.resolve_resource(conn0, q)
        finally:
            conn0.close()
        if not hits:
            return jsonify({"error": f"未找到匹配人员: {q}"}), 404
        rid = hits[0]

    if not rid:
        return jsonify({"error": "resource_id / q 为必填"}), 400

    conn = get_connection()
    try:
        result = aggregate.aggregate_employee(conn, rid, start, end)
        result["by_month"] = aggregate.fill_month_gaps(result["by_month"], start, end)
        p = person_service.get_person(conn, rid)
        result["canonical_name"] = p["canonical_name"] if p else None
        result["resource_id"] = rid
    finally:
        conn.close()
    return jsonify(result)
