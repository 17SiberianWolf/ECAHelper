"""完整冒烟测试：导入全部 43 个有效文件，与附录A基线对账。
基线：33,015 行 / 1,572,771.8h；空项目号 6,575；重复文件 29；异常 14（全 2023.2）；
0 工时 36；资源号 270；有别名变体 192。
"""
import json
import os
import sys

ROOT = r"C:/Users/Administrator/Desktop/ECAHelper"
sys.path.insert(0, ROOT)
import eca_helper  # noqa: F401
from eca_helper.db import ensure_db, get_connection, reset_db
from eca_helper.parsers import importer
from eca_helper.queries import aggregate
from config import ORIGIN_DIR, DB_PATH

# 用真实库（先重置，保证干净）
reset_db(DB_PATH)
print("DB:", DB_PATH)

report = importer.import_files([str(ORIGIN_DIR)], mode="skip")
print("ImportReport:", json.dumps(report.to_dict(), ensure_ascii=False))

conn = get_connection()
cur = conn.cursor()

def one(sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()

r = one("SELECT COUNT(*) n, SUM(actuals_total_h) h, "
        "COUNT(DISTINCT resource_id_norm) p, COUNT(DISTINCT report_month) m, "
        "COUNT(DISTINCT project_id_norm) pr FROM timesheet_record")
total_rows, total_h, persons, months, projects = r["n"], r["h"], r["p"], r["m"], r["pr"]

empty_pid = one("SELECT COUNT(*) n FROM timesheet_record WHERE project_id_norm IS NULL")["n"]
dup_files = one("SELECT COUNT(DISTINCT source_file) n FROM timesheet_record WHERE is_duplicate=1")["n"]
dup_rows = one("SELECT COUNT(*) n FROM timesheet_record WHERE is_duplicate=1")["n"]
anom = one("SELECT COUNT(*) n FROM timesheet_record WHERE is_anomaly_actuals=1")["n"]
zero = one("SELECT COUNT(*) n FROM timesheet_record WHERE actuals_total_h=0")["n"]
empty_rid = one("SELECT COUNT(*) n FROM timesheet_record WHERE resource_id_norm='__UNKNOWN__'")["n"]

cur.execute("SELECT name_aliases FROM person")
import json as _j
with_var = sum(1 for x in cur.fetchall() if len(_j.loads(x["name_aliases"] or "[]")) > 1)
person_total = one("SELECT COUNT(*) n FROM person")["n"]

conn.close()

# 基线对账
BASE_ROWS = 33015
BASE_H = 1572771.8
print("\n=== 对账 ===")
print(f"  rows      : {total_rows}   (基线 {BASE_ROWS})  {'OK' if total_rows==BASE_ROWS else 'MISMATCH'}")
print(f"  hours     : {total_h:.1f} (基线 {BASE_H})  {'OK' if abs(total_h-BASE_H)<1 else 'MISMATCH'}")
print(f"  months    : {months}")
print(f"  persons   : {persons}   (基线 270)  {'OK' if persons==270 else 'MISMATCH'}")
print(f"  projects  : {projects}")
print(f"  empty_pid : {empty_pid}  (基线 6575)  {'OK' if empty_pid==6575 else 'MISMATCH'}")
print(f"  dup_files : {dup_files}  (基线 29)   {'OK' if dup_files==29 else 'MISMATCH'}")
print(f"  dup_rows  : {dup_rows}")
print(f"  anomaly   : {anom}      (基线 14)   {'OK' if anom==14 else 'MISMATCH'}")
print(f"  zero      : {zero}      (基线 36)   {'OK' if zero==36 else 'MISMATCH'}")
print(f"  empty_rid : {empty_rid}")
print(f"  person_var: {with_var}  (基线 192)  {'OK' if with_var==192 else 'MISMATCH'}")
print(f"  person_tot: {person_total}")
print("\nDONE")
