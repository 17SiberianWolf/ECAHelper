"""人员维度服务（系统设计书.md §3.1 person 表 / PRD P0-4 / Q2）。

以 Resource ID 归一化值为主键；同一 ID 的多种姓名写法归入别名列表，
canonical_name = 出现频次最高的写法。默认不自动合并（WATA/WATA02 视为不同人）；
手动合并写 person_merge 并重路由（P2-2，本期默认不自动）。
"""

from __future__ import annotations

import json
from collections import Counter

from config import UNKNOWN_RESOURCE


def _aliases(row) -> set:
    if not row:
        return set()
    return set(json.loads(row["name_aliases"] or "[]"))


def ensure_persons_for_batch(conn, rows, batch_id: str) -> None:
    """根据一批明细行维护 person 表（新增/补别名/补首见信息/重算 canonical）。

    rows: 该批次的明细 dict 列表（需含 resource_id_norm, name_snapshot,
          organization, cost_center）。
    """
    seen: dict[str, tuple] = {}          # rid -> (name, organization, cost_center)
    aliases_batch: dict[str, Counter] = {}
    for r in rows:
        rid = r.get("resource_id_norm")
        if rid is None:
            continue
        nm = r.get("name_snapshot") or ""
        org = r.get("organization")
        cc = r.get("cost_center")
        if rid not in seen:
            seen[rid] = (nm, org, cc)
        if nm:
            aliases_batch.setdefault(rid, Counter())[nm] += 1

    cur = conn.cursor()
    for rid, (nm, org, cc) in seen.items():
        cur.execute(
            "SELECT resource_id_norm, name_aliases, first_organization, "
            "first_cost_center, first_seen_batch FROM person WHERE resource_id_norm=?",
            (rid,),
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO person (resource_id_norm, canonical_name, name_aliases, "
                "first_organization, first_cost_center, first_seen_batch) "
                "VALUES (?,?,?,?,?,?)",
                (
                    rid,
                    nm or None,
                    json.dumps([nm] if nm else []),
                    org,
                    cc,
                    batch_id,
                ),
            )
        else:
            merged = _aliases(row)
            for a in aliases_batch.get(rid, {}):
                merged.add(a)
            cur.execute(
                "UPDATE person SET name_aliases=?, "
                "first_organization=COALESCE(first_organization,?), "
                "first_cost_center=COALESCE(first_cost_center,?), "
                "first_seen_batch=COALESCE(first_seen_batch,?) "
                "WHERE resource_id_norm=?",
                (json.dumps(sorted(merged)), org, cc, batch_id, rid),
            )
    for rid in seen:
        recompute_canonical(conn, rid)
    conn.commit()


def recompute_canonical(conn, rid: str) -> None:
    """按 timesheet_record 中该 ID 的 name_snapshot 频次重算 canonical_name。"""
    cur = conn.cursor()
    cur.execute(
        "SELECT name_snapshot, COUNT(*) AS c FROM timesheet_record "
        "WHERE resource_id_norm=? AND name_snapshot IS NOT NULL AND name_snapshot<>'' "
        "GROUP BY name_snapshot ORDER BY c DESC, name_snapshot LIMIT 1",
        (rid,),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE person SET canonical_name=? WHERE resource_id_norm=?",
            (row["name_snapshot"], rid),
        )
        conn.commit()


def resolve_resource(conn, query_str: str) -> list[str]:
    """按 ID 或姓名别名解析 resource_id_norm 候选列表。

    1) 直接归一化命中 person 主键；
    2) 否则在 canonical_name / name_aliases(JSON) 中做子串匹配。
    返回候选 rid 列表（可能多个，UI 可让用户选择；默认不自动合并）。
    """
    q = (query_str or "").strip()
    if not q:
        return []
    norm = q.upper()
    cur = conn.cursor()
    # 1) 精确主键命中
    cur.execute("SELECT resource_id_norm FROM person WHERE resource_id_norm=?", (norm,))
    exact = [r["resource_id_norm"] for r in cur.fetchall()]
    if exact:
        return exact
    # 2) 别名/规范名 子串匹配
    cur.execute(
        "SELECT resource_id_norm, canonical_name, name_aliases FROM person"
    )
    found: list[str] = []
    for r in cur.fetchall():
        aliases = _aliases(r)
        hay = {r["canonical_name"] or ""} | aliases
        if any(norm in (a or "").upper() for a in hay):
            found.append(r["resource_id_norm"])
    return found


def merge(conn, from_rid: str, to_rid: str, note: str = "") -> None:
    """手动合并：from 重路由到 to（写 person_merge + person.merged_into）。

    决策 Q2：默认不自动合并；仅当用户在 UI 显式操作时调用。
    """
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO person_merge (from_resource_id_norm, to_resource_id_norm, "
        "created_at, note) VALUES (?,?, datetime('now'), ?)",
        (from_rid, to_rid, note),
    )
    cur.execute(
        "UPDATE person SET merged_into=? WHERE resource_id_norm=?", (to_rid, from_rid)
    )
    conn.commit()


def get_person(conn, rid: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM person WHERE resource_id_norm=?", (rid,))
    return cur.fetchone()


def list_persons(conn, limit: int = 2000):
    cur = conn.cursor()
    cur.execute(
        "SELECT resource_id_norm, canonical_name, name_aliases FROM person "
        "ORDER BY resource_id_norm LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def unknown_resource() -> str:
    return UNKNOWN_RESOURCE
