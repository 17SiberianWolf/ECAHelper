"""Web 层冒烟测试：用 Flask test_client 验证页面/API（无需端口与浏览器）。
前置：eca_helper.db 已由 _smoke_all 导入全部 44 个有效文件。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # tools/ 的上一级 = 项目根
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))  # 让 `import config` / `import app` 生效

import app as ecapp  # noqa: E402
from eca_helper.db import get_connection  # noqa: E402
from config import DB_PATH  # noqa: E402

application = ecapp.create_app()
client = application.test_client()


def check(method, path, body=None):
    if body is not None:
        resp = client.post(path, json=body)
    else:
        resp = client.get(path)
    ok = resp.status_code == 200
    print(f"[{'OK' if ok else 'FAIL'}] {method} {path} -> {resp.status_code}")
    return resp


def main():
    failures = 0
    for p in ("/", "/import", "/project", "/employee", "/search", "/quality"):
        r = check("GET", p)
        if r.status_code != 200:
            failures += 1

    # 选项接口
    check("GET", "/api/options/projects")
    check("GET", "/api/options/persons")
    check("GET", "/api/options/filters")

    # 质量汇总
    r = check("GET", "/api/quality/summary")
    if r.status_code == 200:
        s = r.get_json()
        print("   质量汇总: rows=%s hours=%.1f empty_pid=%s anomaly=%s zero=%s persons=%s" % (
            s["total_rows"], s["total_hours"], s["empty_pid"], s["anomaly_rows"],
            s["zero_rows"], s["persons_total"]))

    # 取一个 Top 项目做项目查询
    conn = get_connection(DB_PATH)
    row = conn.execute(
        "SELECT project_id_norm FROM timesheet_record WHERE project_id_norm IS NOT NULL "
        "GROUP BY project_id_norm ORDER BY SUM(actuals_total_h) DESC LIMIT 1"
    ).fetchone()
    rid_row = conn.execute(
        "SELECT resource_id_norm FROM timesheet_record WHERE resource_id_norm <> '__UNKNOWN__' "
        "GROUP BY resource_id_norm ORDER BY SUM(actuals_total_h) DESC LIMIT 1"
    ).fetchone()
    conn.close()
    pid = row["project_id_norm"]
    rid = rid_row["resource_id_norm"]
    print("   测试项目号:", pid, " 测试人员:", rid)

    r = check("POST", "/api/query/project", {"project_id": pid, "start": "2023-02", "end": "2026-09"})
    if r.status_code == 200:
        d = r.get_json()
        print("   项目查询 total h=%.1f rows=%s persons=%s" % (
            d["total"]["total_h"], d["total"]["rows"], d["total"]["persons"]))
        print("   by_month 月数=%d  by_person 人数=%d  wbs 级数=%d" % (
            len(d["by_month"]), len(d["by_person"]), len(d["wbs"])))

    r = check("POST", "/api/query/employee", {"resource_id": rid, "start": "2023-02", "end": "2026-09"})
    if r.status_code == 200:
        d = r.get_json()
        print("   员工查询 total h=%.1f 项目数=%d 非项目任务数=%d" % (
            d["total"]["total_h"], len(d["by_project"]), len(d["non_project"])))

    r = check("POST", "/api/query/search", {"start": "2023-02", "end": "2026-09"})
    if r.status_code == 200:
        d = r.get_json()
        print("   综合检索 total h=%.1f rows=%s" % (d["total"]["total_h"], d["total"]["rows"]))

    r = check("GET", "/api/chart/topn?dimension=project&n=10&start=2023-02&end=2026-09")
    r = check("GET", "/api/chart/trend?start=2023-02&end=2026-09&project_id=" + pid)
    r = check("GET", "/api/chart/matrix?start=2023-02&end=2026-09")

    # 导出
    r = check("POST", "/api/export", {
        "start": "2023-02", "end": "2026-09", "project_id": pid,
        "format": "csv", "lang": "both", "title": "冒烟"
    })
    if r.status_code == 200:
        d = r.get_json()
        print("   导出文件:", d.get("filename"), "路径:", d.get("path"))

    print("\n=== 失败数:", failures, "===")
    return failures


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
