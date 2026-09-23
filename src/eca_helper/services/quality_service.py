"""数据质量面板服务（系统设计书.md §8 质量 / T08 / Q3）。

计算质量指标（空项目号 / 重复文件 / 异常行 / 0 工时 / 人员别名变体），
并提供明细下钻与「勾选排除持久化」（默认不排除，勾选后写入 exclusion 表）。

排除条款形态见 系统设计书.md §4.8：
    duplicate -> target_key = dup_group_key（source_file#hash）
    anomaly / zero / empty_rid -> target_key = source_file|source_row
"""

from __future__ import annotations

import json
import re

from config import SUSPICIOUS_PROJECT_PATTERN, UNKNOWN_RESOURCE

# 项目号形态异常（问题 8 / AC-08-2）：与项目下拉的「可疑」徽标共用同一判定源
# config.SUSPICIOUS_PROJECT_PATTERN，保证两处口径完全一致。
# 按 PRD 决策「只标记、不删不改」——本类别**不进入排除白名单**，工时照常计入统计。
_SHAPE_RE = re.compile(SUSPICIOUS_PROJECT_PATTERN)


def _project_shape_values(conn) -> list[dict]:
    """返回日期型项目号（形如 '2092-12-08 00:00:00'）的 [{value, rows, h}]。"""
    cur = conn.cursor()
    cur.execute(
        "SELECT project_id_norm AS pid, COUNT(*) AS rows, "
        "COALESCE(SUM(actuals_total_h), 0) AS h "
        "FROM timesheet_record "
        "WHERE project_id_norm IS NOT NULL AND project_id_norm <> '' "
        "GROUP BY project_id_norm"
    )
    out = []
    for r in cur.fetchall():
        if _SHAPE_RE.match(r["pid"] or ""):
            out.append({"value": r["pid"], "rows": r["rows"], "h": r["h"]})
    out.sort(key=lambda x: (-x["h"], -x["rows"]))
    return out


def quality_summary(conn) -> dict:
    """返回质量面板所需的全部指标。"""
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS n FROM timesheet_record WHERE project_id_norm IS NULL")
    empty_pid = cur.fetchone()["n"]

    cur.execute(
        "SELECT COUNT(DISTINCT source_file) AS files, COUNT(*) AS rows "
        "FROM timesheet_record WHERE is_duplicate=1"
    )
    d = cur.fetchone()
    dup_files, dup_rows = d["files"], d["rows"]

    cur.execute("SELECT COUNT(*) AS n FROM timesheet_record WHERE is_anomaly_actuals=1")
    anomaly = cur.fetchone()["n"]

    # 真实 0 工时行（不含异常行：异常行另计 category=anomaly）
    cur.execute(
        "SELECT COUNT(*) AS n FROM timesheet_record "
        "WHERE actuals_total_h = 0 AND is_anomaly_actuals = 0"
    )
    zero = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM person")
    persons_total = cur.fetchone()["n"]

    cur.execute("SELECT name_aliases FROM person")
    with_variants = 0
    for r in cur.fetchall():
        aliases = json.loads(r["name_aliases"] or "[]")
        if len(aliases) > 1:
            with_variants += 1

    cur.execute("SELECT COUNT(*) AS n FROM exclusion WHERE excluded = 1")
    active_exclusions = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n, COALESCE(SUM(actuals_total_h),0) AS h FROM timesheet_record")
    tot = cur.fetchone()
    total_rows = tot["n"]
    total_hours = tot["h"]

    shape = _project_shape_values(conn)

    return {
        "total_rows": total_rows,
        "total_hours": total_hours,
        "empty_pid": empty_pid,
        "duplicate_files": dup_files,
        "duplicate_rows": dup_rows,
        "anomaly_rows": anomaly,
        "zero_rows": zero,
        "persons_total": persons_total,
        "persons_with_variants": with_variants,
        "active_exclusions": active_exclusions,
        "project_shape_rows": sum(x["rows"] for x in shape),
        "project_shape_values": shape,
    }


def _category_rows(conn, category: str) -> list[tuple[str, str]]:
    """返回 (category, target_key) 列表，供排除持久化使用。"""
    cur = conn.cursor()
    if category == "duplicate":
        cur.execute(
            "SELECT DISTINCT dup_group_key FROM timesheet_record "
            "WHERE dup_group_key IS NOT NULL"
        )
        return [("duplicate", r["dup_group_key"]) for r in cur.fetchall()]
    key_sql = "source_file || '|' || source_row"
    if category == "anomaly":
        cond = "is_anomaly_actuals = 1"
    elif category == "zero":
        cond = "actuals_total_h = 0 AND is_anomaly_actuals = 0"
    elif category == "empty_rid":
        cond = f"resource_id_norm = '{UNKNOWN_RESOURCE}'"
    else:
        return []
    cur.execute(f"SELECT {key_sql} AS k FROM timesheet_record WHERE {cond}")
    return [(category, r["k"]) for r in cur.fetchall()]


def set_category_exclusion(conn, category: str, excluded: bool) -> int:
    """勾选/取消某类别的全部行排除。

    excluded=True  -> 该类别所有相关行写入 exclusion(excluded=1)；
    excluded=False -> 删除该类别的全部排除记录（恢复统计）。
    返回受影响（写入）的排除记录数。
    """
    cur = conn.cursor()
    if not excluded:
        cur.execute("DELETE FROM exclusion WHERE category = ?", (category,))
        conn.commit()
        return 0
    rows = _category_rows(conn, category)
    n = 0
    for cat, key in rows:
        cur.execute(
            "INSERT OR IGNORE INTO exclusion (category, target_key, excluded, created_at) "
            "VALUES (?, ?, 1, datetime('now'))",
            (cat, key),
        )
        n += 1
    conn.commit()
    return n


def detail_rows(conn, category: str, limit: int = 500) -> list[dict]:
    """质量明细下钻：返回某类别的明细行（供面板溯源 source_row）。"""
    cur = conn.cursor()
    base_cols = (
        "r.source_file AS source_file, r.source_row AS source_row, "
        "r.resource_id_norm AS resource_id_norm, r.name_snapshot AS name_snapshot, "
        "r.project_id_norm AS project_id_norm, r.actuals_total_h AS actuals_total_h, "
        "r.actuals_raw_text AS actuals_raw_text"
    )
    if category == "duplicate":
        cur.execute(
            f"SELECT {base_cols}, r.dup_group_key AS grp FROM timesheet_record r "
            "WHERE r.dup_group_key IS NOT NULL ORDER BY r.dup_group_key, r.source_row LIMIT ?",
            (limit,),
        )
    elif category == "anomaly":
        cur.execute(
            f"SELECT {base_cols} FROM timesheet_record r WHERE r.is_anomaly_actuals = 1 "
            "ORDER BY r.source_file, r.source_row LIMIT ?",
            (limit,),
        )
    elif category == "zero":
        cur.execute(
            f"SELECT {base_cols} FROM timesheet_record r WHERE r.actuals_total_h = 0 "
            "ORDER BY r.source_file, r.source_row LIMIT ?",
            (limit,),
        )
    elif category == "empty_rid":
        cur.execute(
            f"SELECT {base_cols} FROM timesheet_record r "
            f"WHERE r.resource_id_norm = '{UNKNOWN_RESOURCE}' "
            "ORDER BY r.source_file, r.source_row LIMIT ?",
            (limit,),
        )
    elif category == "project_shape":
        # 先用同一判定源取到命中项目号，再按号取明细（保证与徽标/汇总口径一致）
        vals = [v["value"] for v in _project_shape_values(conn)]
        if not vals:
            return []
        ph = ",".join("?" for _ in vals)
        cur.execute(
            f"SELECT {base_cols} FROM timesheet_record r "
            f"WHERE r.project_id_norm IN ({ph}) "
            "ORDER BY r.source_file, r.source_row LIMIT ?",
            (*vals, limit),
        )
    else:
        return []
    return [dict(x) for x in cur.fetchall()]
