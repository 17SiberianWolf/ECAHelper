"""图表数据路由（决策 +1：原生 SVG，无 ECharts/CDN / T11）。

提供 JSON 数据，由 static/js/charts.js 用原生 SVG 渲染：
    GET /api/chart/topn    Top N 排行（维度/数量可配）
    GET /api/chart/trend   按月趋势（缺月补 0）
    GET /api/chart/matrix  人员 × 项目 交叉矩阵（heatmap 数据）
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from eca_helper.db import ensure_db, get_connection
from eca_helper.queries import aggregate
from eca_helper.queries.aggregate import EXCLUSION_SQL, PROJECT_BASE_SQL, QueryFilter, _base_where

bp = Blueprint("chart_routes", __name__)


def _month_series(conn, start, end, extra: QueryFilter | None = None) -> list[dict]:
    """通用按月趋势（缺月补 0）。"""
    params: dict = {"m_start": start, "m_end": end}
    where = " AND r.report_month BETWEEN :m_start AND :m_end"
    if extra:
        where += _base_where(extra, params) + aggregate._empty_project_cond(extra)
    cur = conn.cursor()
    cur.execute(
        "SELECT r.report_month AS month, COALESCE(SUM(r.actuals_total_h),0) AS h, "
        "COUNT(*) AS rows FROM timesheet_record r WHERE 1=1 " + EXCLUSION_SQL + where
        + " GROUP BY r.report_month ORDER BY r.report_month",
        params,
    )
    rows = [dict(x) for x in cur.fetchall()]
    return aggregate.fill_month_gaps(rows, start, end)


@bp.route("/api/chart/topn")
def api_chart_topn():
    dimension = request.args.get("dimension", "project")
    if dimension not in ("person", "project", "org", "cost_center"):
        dimension = "project"
    try:
        n = max(1, min(int(request.args.get("n", 10)), 100))
    except ValueError:
        n = 10
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return jsonify({"error": "start / end 为必填"}), 400
    extra = QueryFilter(
        report_month_start=start,
        report_month_end=end,
        organization=request.args.get("organization"),
        cost_center=request.args.get("cost_center"),
        task=request.args.get("task"),
    )
    conn = get_connection()
    try:
        data = aggregate.top_n(conn, dimension, n, start, end, extra)
    finally:
        conn.close()
    return jsonify({"dimension": dimension, "n": n, "data": data})


@bp.route("/api/chart/trend")
def api_chart_trend():
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return jsonify({"error": "start / end 为必填"}), 400
    extra = QueryFilter(
        report_month_start=start,
        report_month_end=end,
        project_id=request.args.get("project_id"),
        resource_id=request.args.get("resource_id"),
        organization=request.args.get("organization"),
        cost_center=request.args.get("cost_center"),
        task=request.args.get("task"),
    )
    conn = get_connection()
    try:
        series = _month_series(conn, start, end, extra)
    finally:
        conn.close()
    return jsonify({"series": series})


@bp.route("/api/chart/matrix")
def api_chart_matrix():
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return jsonify({"error": "start / end 为必填"}), 400
    try:
        top_p = max(1, min(int(request.args.get("top_projects", 12)), 30))
        top_r = max(1, min(int(request.args.get("top_persons", 15)), 30))
    except ValueError:
        top_p, top_r = 12, 15

    conn = get_connection()
    try:
        projects = aggregate.top_n(conn, "project", top_p, start, end)
        persons = aggregate.top_n(conn, "person", top_r, start, end)
        pids = [p["key"] for p in projects if p["key"]]
        rids = [r["key"] for r in persons if r["key"]]
        cells: dict[str, float] = {}
        if pids and rids:
            qm_p = ",".join("?" for _ in pids)
            qm_r = ",".join("?" for _ in rids)
            cur = conn.cursor()
            cur.execute(
                "SELECT " + PROJECT_BASE_SQL + " AS pid, r.resource_id_norm AS rid, "
                "COALESCE(SUM(r.actuals_total_h),0) AS h FROM timesheet_record r "
                "WHERE r.report_month BETWEEN ? AND ? " + EXCLUSION_SQL
                + " AND " + PROJECT_BASE_SQL + f" IN ({qm_p}) AND r.resource_id_norm IN ({qm_r}) "
                "GROUP BY " + PROJECT_BASE_SQL + ", r.resource_id_norm",
                [start, end] + pids + rids,
            )
            for row in cur.fetchall():
                cells[f"{row['pid']}|{row['rid']}"] = row["h"]
    finally:
        conn.close()
    return jsonify({
        "projects": [p["key"] for p in projects],
        "persons": [r["key"] for r in persons],
        "cells": cells,
    })
