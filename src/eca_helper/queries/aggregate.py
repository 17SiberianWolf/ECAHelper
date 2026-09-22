"""三层聚合与多维检索引擎（系统设计书.md §4.7 / §4.8 / T07）。

统一约定：
    - timesheet_record 一律以别名 `r` 参与查询，便于复用 EXCLUSION_SQL；
    - 所有统计查询统一套用排除条款 EXCLUSION_SQL（默认 exclusion 表为空 → 含全部原始行）；
    - 时间区间使用 report_month BETWEEN :m_start AND :m_end（来自文件名，权威）。

对外提供：
    - aggregate_project / aggregate_employee / search
    - wbs_drill（WBS 下一级下钻）
    - top_n / by_organization / by_cost_center
    - month_bounds（可用月份范围，供快捷按钮）
    - fill_month_gaps（趋势图缺月补 0）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from eca_helper.parsers import normalizer

# 统一排除条款（Q3：默认 exclusion 表为空 → 不影响任何行）
EXCLUSION_SQL = """
AND NOT EXISTS (
  SELECT 1 FROM exclusion e WHERE e.excluded = 1 AND (
    (e.category='duplicate' AND r.dup_group_key IS NOT NULL AND e.target_key = r.dup_group_key)
    OR (e.category='anomaly'  AND e.target_key = r.source_file || '|' || r.source_row)
    OR (e.category='zero'     AND e.target_key = r.source_file || '|' || r.source_row)
    OR (e.category='empty_rid' AND e.target_key = r.source_file || '|' || r.source_row)
  )
)"""


@dataclass
class QueryFilter:
    """综合检索过滤条件（search 维度）。字段为 None 表示不限制。"""

    report_month_start: Optional[str] = None
    report_month_end: Optional[str] = None
    organization: Optional[str] = None
    cost_center: Optional[str] = None
    task: Optional[str] = None
    resource_id: Optional[str] = None
    project_id: Optional[str] = None
    include_empty_project: bool = False


# ---------------------------------------------------------------------------
# 基础条件拼接
# ---------------------------------------------------------------------------
def _escape_like(value: str) -> str:
    """转义 LIKE 模式中的通配符（\\ % _），配合 ESCAPE '\\' 使用。"""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _base_where(f: QueryFilter, params: dict) -> str:
    conds: list[str] = []
    if f.report_month_start and f.report_month_end:
        conds.append("r.report_month BETWEEN :m_start AND :m_end")
        params["m_start"] = f.report_month_start
        params["m_end"] = f.report_month_end
    if f.organization:
        conds.append("r.organization = :organization")
        params["organization"] = f.organization
    if f.cost_center:
        conds.append("r.cost_center = :cost_center")
        params["cost_center"] = f.cost_center
    if f.task:
        # 任务过滤：包含匹配（US-R2-03）。f.task 为空时不得拼接任何条件，
        # 保证「不带任务筛选」的查询结果与改动前逐字节等价（红线守恒）。
        conds.append("r.task LIKE :task ESCAPE '\\'")
        params["task"] = "%" + _escape_like(f.task) + "%"
    if f.resource_id:
        conds.append("r.resource_id_norm = :resource_id")
        params["resource_id"] = f.resource_id
    if f.project_id:
        conds.append("r.project_id_norm = :project_id")
        params["project_id"] = f.project_id
    return (" AND " + " AND ".join(conds)) if conds else ""


def _empty_project_cond(f: QueryFilter) -> str:
    """项目维度是否纳入空项目号行。search 维度由 include_empty_project 控制。"""
    if f.include_empty_project:
        return ""  # 不限制 project_id_norm
    return " AND r.project_id_norm IS NOT NULL"


# ---------------------------------------------------------------------------
# 三层聚合（通用）
# ---------------------------------------------------------------------------
def _three_layer(conn, where_suffix: str, params: dict, person_group: str = "r.resource_id_norm"):
    """返回 (total, by_month, by_person)。

    where_suffix 为附加的维度 WHERE 条件（不含 EXCLUSION 与 1=1）。
    person_group 指定层3 的 GROUP BY 字段（员工查询按项目）。
    """
    full_where = " FROM timesheet_record r WHERE 1=1 " + EXCLUSION_SQL + where_suffix
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(SUM(r.actuals_total_h),0) AS total_h, "
        "COUNT(*) AS rows, "
        "COUNT(DISTINCT r.resource_id_norm) AS persons, "
        "COUNT(DISTINCT r.report_month) AS months "
        + full_where,
        params,
    )
    total = dict(cur.fetchone())

    cur.execute(
        "SELECT r.report_month AS month, COALESCE(SUM(r.actuals_total_h),0) AS h, "
        "COUNT(*) AS rows " + full_where + " GROUP BY r.report_month ORDER BY r.report_month",
        params,
    )
    by_month = [dict(x) for x in cur.fetchall()]

    cur.execute(
        f"SELECT {person_group} AS key, r.name_snapshot AS name, "
        f"COALESCE(SUM(r.actuals_total_h),0) AS h, COUNT(*) AS rows "
        + full_where
        + f" GROUP BY {person_group} ORDER BY h DESC",
        params,
    )
    by_person = [dict(x) for x in cur.fetchall()]
    return total, by_month, by_person


# ---------------------------------------------------------------------------
# 项目工时查询
# ---------------------------------------------------------------------------
def aggregate_project(conn, project_id: str, start: str, end: str,
                      wbs_prefix: str = "") -> dict:
    """按项目号聚合：总计 / 按月 / 按人 / WBS 下一级。"""
    params = {"pid": project_id, "m_start": start, "m_end": end}
    where = " AND r.project_id_norm = :pid AND r.report_month BETWEEN :m_start AND :m_end"
    total, by_month, by_person = _three_layer(conn, where, params)
    wbs = wbs_drill(conn, project_id, wbs_prefix, start, end)
    return {
        "total": total,
        "by_month": by_month,
        "by_person": by_person,
        "wbs": wbs,
        "wbs_prefix": wbs_prefix,
    }


def wbs_drill(conn, project_id: str, prefix: str, start: str, end: str) -> list[dict]:
    """WBS 下一级下钻：按 prefix 过滤子树，Python 侧计算「下一级前缀」聚合。"""
    params = {"pid": project_id, "m_start": start, "m_end": end,
              "wbs_like": (prefix + ".%") if prefix else "%"}
    like_cond = " AND r.wbs_nr LIKE :wbs_like" if prefix else ""
    cur = conn.cursor()
    cur.execute(
        "SELECT r.wbs_nr AS wbs, COALESCE(SUM(r.actuals_total_h),0) AS h, COUNT(*) AS rows "
        "FROM timesheet_record r WHERE r.project_id_norm = :pid "
        "AND r.wbs_nr IS NOT NULL AND r.report_month BETWEEN :m_start AND :m_end "
        + like_cond + EXCLUSION_SQL + " GROUP BY r.wbs_nr",
        params,
    )
    agg: dict[str, list] = {}
    for row in cur.fetchall():
        nxt = normalizer.wbs_next_level(row["wbs"], prefix)
        if nxt is None:
            continue
        bucket = agg.setdefault(nxt, [0.0, 0])
        bucket[0] += row["h"]
        bucket[1] += row["rows"]
    result = [{"wbs": k, "h": v[0], "rows": v[1]} for k, v in agg.items()]
    result.sort(key=lambda x: -x["h"])
    return result


# ---------------------------------------------------------------------------
# 员工工时查询
# ---------------------------------------------------------------------------
def aggregate_employee(conn, resource_id: str, start: str, end: str) -> dict:
    """按人员聚合：总计 / 按月 / 按项目（含非项目工时单列）+ 非项目工时按 task 细分。"""
    params = {"rid": resource_id, "m_start": start, "m_end": end}
    where_all = " AND r.resource_id_norm = :rid AND r.report_month BETWEEN :m_start AND :m_end"
    total, by_month, _ = _three_layer(conn, where_all, params)

    cur = conn.cursor()
    # 按项目（排除空项目号）
    cur.execute(
        "SELECT r.project_id_norm AS key, r.project_name AS name, "
        "COALESCE(SUM(r.actuals_total_h),0) AS h, COUNT(*) AS rows "
        "FROM timesheet_record r WHERE r.resource_id_norm = :rid "
        "AND r.project_id_norm IS NOT NULL AND r.report_month BETWEEN :m_start AND :m_end "
        + EXCLUSION_SQL + " GROUP BY r.project_id_norm ORDER BY h DESC",
        params,
    )
    by_project = [dict(x) for x in cur.fetchall()]

    # 非项目工时（空项目号）按 task 细分
    cur.execute(
        "SELECT r.task AS task, COALESCE(SUM(r.actuals_total_h),0) AS h, COUNT(*) AS rows "
        "FROM timesheet_record r WHERE r.resource_id_norm = :rid "
        "AND r.project_id_norm IS NULL AND r.report_month BETWEEN :m_start AND :m_end "
        + EXCLUSION_SQL + " GROUP BY r.task ORDER BY h DESC",
        params,
    )
    non_project = [dict(x) for x in cur.fetchall()]
    return {
        "total": total,
        "by_month": by_month,
        "by_project": by_project,
        "non_project": non_project,
    }


# ---------------------------------------------------------------------------
# 综合检索
# ---------------------------------------------------------------------------
def search(conn, f: QueryFilter) -> dict:
    """综合检索：可选 organization/cost_center/task/resource_id/project_id/含空项目号。"""
    params: dict = {}
    where = _base_where(f, params) + _empty_project_cond(f)
    total, by_month, by_person = _three_layer(conn, where, params)
    # 项目维度分布（供结果概览）
    cur = conn.cursor()
    cur.execute(
        "SELECT r.project_id_norm AS key, r.project_name AS name, "
        "COALESCE(SUM(r.actuals_total_h),0) AS h, COUNT(*) AS rows "
        "FROM timesheet_record r WHERE 1=1 " + EXCLUSION_SQL + where
        + " AND r.project_id_norm IS NOT NULL GROUP BY r.project_id_norm ORDER BY h DESC LIMIT 50",
        params,
    )
    by_project = [dict(x) for x in cur.fetchall()]
    return {"total": total, "by_month": by_month, "by_person": by_person,
            "by_project": by_project}


# ---------------------------------------------------------------------------
# Top N / 组织 / 成本中心（P1）
# ---------------------------------------------------------------------------
_DIM_SQL = {
    "person": "r.resource_id_norm",
    "project": "r.project_id_norm",
    "org": "r.organization",
    "cost_center": "r.cost_center",
}


def top_n(conn, dimension: str, n: int, start: str, end: str,
          extra: Optional[QueryFilter] = None) -> list[dict]:
    """按维度取工时 Top N。dimension ∈ {person, project, org, cost_center}。"""
    dim_sql = _DIM_SQL.get(dimension, "r.resource_id_norm")
    params: dict = {"m_start": start, "m_end": end, "n": int(n)}
    where = ""
    if extra:
        where = _base_where(extra, params) + _empty_project_cond(extra)
    cur = conn.cursor()
    cur.execute(
        f"SELECT {dim_sql} AS key, COALESCE(SUM(r.actuals_total_h),0) AS h, COUNT(*) AS rows "
        "FROM timesheet_record r WHERE 1=1 " + EXCLUSION_SQL + where
        + f" AND {dim_sql} IS NOT NULL GROUP BY {dim_sql} ORDER BY h DESC LIMIT :n",
        params,
    )
    return [dict(x) for x in cur.fetchall()]


def by_organization(conn, start: str, end: str) -> list[dict]:
    return top_n(conn, "org", 100000, start, end)


def by_cost_center(conn, start: str, end: str) -> list[dict]:
    return top_n(conn, "cost_center", 100000, start, end)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def month_bounds(conn) -> tuple[Optional[str], Optional[str]]:
    """返回库内可用月份的最小/最大值。"""
    cur = conn.cursor()
    cur.execute("SELECT MIN(report_month) AS lo, MAX(report_month) AS hi FROM timesheet_record")
    r = cur.fetchone()
    return (r["lo"], r["hi"]) if r else (None, None)


def project_name_for(conn, project_id: str) -> Optional[str]:
    """取项目规范名（出现频次最高的 project_name）。"""
    cur = conn.cursor()
    cur.execute(
        "SELECT project_name, COUNT(*) AS c FROM timesheet_record "
        "WHERE project_id_norm = ? AND project_name IS NOT NULL AND project_name <> '' "
        "GROUP BY project_name ORDER BY c DESC LIMIT 1",
        (project_id,),
    )
    r = cur.fetchone()
    return r["project_name"] if r else None


def fill_month_gaps(by_month: list[dict], start: str, end: str) -> list[dict]:
    """对 [start, end] 内无数据的月份补 0（趋势图不断裂）。"""
    present = {m["month"]: m for m in by_month}
    out: list[dict] = []
    for m in normalizer.month_iter(start, end):
        if m in present:
            out.append(present[m])
        else:
            out.append({"month": m, "h": 0.0, "rows": 0})
    return out


def list_projects(conn, limit: int = 5000) -> list[dict]:
    """项目清单（实时聚合，不建主数据表）。"""
    cur = conn.cursor()
    cur.execute(
        "SELECT project_id_norm AS pid, project_id_raw AS raw, "
        "MAX(project_name) AS name FROM timesheet_record "
        "WHERE project_id_norm IS NOT NULL GROUP BY project_id_norm "
        "ORDER BY pid LIMIT ?",
        (limit,),
    )
    return [dict(x) for x in cur.fetchall()]


def list_organizations(conn, limit: int = 5000) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT organization FROM timesheet_record "
        "WHERE organization IS NOT NULL AND organization <> '' ORDER BY organization LIMIT ?",
        (limit,),
    )
    return [r["organization"] for r in cur.fetchall()]


def list_cost_centers(conn, limit: int = 5000) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT cost_center FROM timesheet_record "
        "WHERE cost_center IS NOT NULL AND cost_center <> '' ORDER BY cost_center LIMIT ?",
        (limit,),
    )
    return [r["cost_center"] for r in cur.fetchall()]


def list_tasks(conn) -> list[dict]:
    """任务候选清单：全部 task 值 + 累计工时 + 行数，按累计工时降序（US-R2-03 / AC-04-1）。

    - 返回**全部** task（约 1,175 条），不做任何静态截断（决策 13）；
    - 统计查询一律套用 EXCLUSION_SQL（Q3）。
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT r.task AS task, COALESCE(SUM(r.actuals_total_h),0) AS h, COUNT(*) AS rows "
        "FROM timesheet_record r WHERE 1=1 " + EXCLUSION_SQL
        + " AND r.task IS NOT NULL AND r.task <> '' "
        "GROUP BY r.task ORDER BY h DESC",
        {},
    )
    return [dict(x) for x in cur.fetchall()]
