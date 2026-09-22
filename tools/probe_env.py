import glob
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # tools/ 的上一级 = 项目根
SRC = ROOT / "OriginSource"

out = io.StringIO()
def w(*a):
    print(*a, file=out)

w("python:", sys.version.replace("\n", " "))
w("exe:", sys.executable)

files = sorted(glob.glob(os.path.join(str(SRC), "*")))
w("file count:", len(files))
for f in files:
    w("  ", os.path.basename(f), os.path.getsize(f))

for mod in ("openpyxl", "pandas", "xlrd", "sqlite3", "flask", "fastapi"):
    try:
        m = __import__(mod)
        w(f"MODULE {mod}: OK", getattr(m, "__version__", ""))
    except Exception as e:
        w(f"MODULE {mod}: MISSING ({e})")

with open(ROOT / "tools" / "_env_report.txt", "w", encoding="utf-8") as fh:
    fh.write(out.getvalue())
print("done")
