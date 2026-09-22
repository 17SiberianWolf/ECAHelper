"""临时冒烟测试：对 3 个样本文件跑通核心导入管线（不污染最终库）。"""
import os
import sys

ROOT = r"C:/Users/Administrator/Desktop/ECAHelper"
sys.path.insert(0, ROOT)
import eca_helper  # noqa: F401  (注入 ROOT 到 sys.path)
from eca_helper.db import ensure_db, get_connection
from eca_helper.parsers import importer
from config import ORIGIN_DIR

TMP_DB = os.path.join(ROOT, "tools", "_smoke3.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)

ensure_db(TMP_DB)

samples = [
    os.path.join(ORIGIN_DIR, "Timesheet of 2023.2 including SC.xlsx"),
    os.path.join(ORIGIN_DIR, "Timesheet of 2024.07 including SC.xlsx"),
    os.path.join(ORIGIN_DIR, "Timesheet of 2026.09 including SC.xlsx"),
]

report = importer.import_files(samples, mode="skip", db_path=TMP_DB)
print("=== ImportReport ===")
for k, v in report.to_dict().items():
    if k not in ("failed_files", "per_file"):
        print(f"  {k}: {v}")
print("  per_file:")
for pf in report.per_file:
    print("   ", pf)

conn = get_connection(TMP_DB)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) AS n, SUM(actuals_total_h) AS h, "
            "COUNT(DISTINCT resource_id_norm) AS p, COUNT(DISTINCT report_month) AS m "
            "FROM timesheet_record")
r = cur.fetchone()
print("\n=== Aggregate (all 3 files) ===")
print(f"  rows={r['n']}  total_h={r['h']}  persons={r['p']}  months={r['m']}")

cur.execute("SELECT report_month, COUNT(*) AS n, SUM(actuals_total_h) AS h, "
            "SUM(is_duplicate) AS dup, SUM(is_anomaly_actuals) AS anom "
            "FROM timesheet_record GROUP BY report_month")
print("\n  by month:")
for row in cur.fetchall():
    print(f"    {row['report_month']}: rows={row['n']} h={row['h']} "
          f"dup={row['dup']} anom={row['anom']}")

cur.execute("SELECT COUNT(*) AS n FROM person")
print(f"\n  person rows: {cur.fetchone()['n']}")

# 幂等验证：同文件再导一次应 skip
report2 = importer.import_files(samples, mode="skip", db_path=TMP_DB)
print(f"\n=== Idempotency (re-import skip) ===")
print(f"  files_imported={report2.files_imported} files_skipped={report2.files_skipped}")
conn.close()
os.remove(TMP_DB)
print("\nDONE")
