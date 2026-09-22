import glob
import io
import json
import os
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]  # tools/ 的上一级 = 项目根
SRC = ROOT / "OriginSource"
out = io.StringIO()
def w(*a): print(*a, file=out)

files = sorted([f for f in glob.glob(os.path.join(SRC, "*.xlsx")) if not os.path.basename(f).startswith("~$")])
w("total xlsx:", len(files))

# ---------- 1. sheet names for every file ----------
w("\n=== SHEET NAMES ===")
for f in files:
    wb = load_workbook(f, read_only=True, data_only=True)
    w(os.path.basename(f), "|", wb.sheetnames)
    wb.close()

# ---------- 2. deep dive on the 3rd sheet of a few files ----------
def dump(f, nrows=12):
    w("\n" + "=" * 90)
    w("FILE:", os.path.basename(f))
    wb = load_workbook(f, read_only=True, data_only=True)
    for si, sn in enumerate(wb.sheetnames):
        ws = wb[sn]
        w(f"\n-- [{si}] sheet='{sn}'  dims={ws.calculate_dimension()}  max_row={ws.max_row} max_col={ws.max_column}")
        cnt = 0
        for r in ws.iter_rows(values_only=True):
            if cnt >= nrows: break
            w(f"   r{cnt}: {list(r)}")
            cnt += 1
    wb.close()

for f in [files[3], files[7], files[11], files[34]]:
    dump(f)

with open(ROOT / "tools" / "_sheet_report.txt", "w", encoding="utf-8") as fh:
    fh.write(out.getvalue())
print("ok")
