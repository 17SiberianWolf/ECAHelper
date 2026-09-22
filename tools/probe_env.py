import sys, os, glob, io, json

out = io.StringIO()
def w(*a):
    print(*a, file=out)

w("python:", sys.version.replace("\n", " "))
w("exe:", sys.executable)

src = r"C:\Users\Administrator\Desktop\ECAHelper\OriginSource"
files = sorted(glob.glob(os.path.join(src, "*")))
w("file count:", len(files))
for f in files:
    w("  ", os.path.basename(f), os.path.getsize(f))

for mod in ("openpyxl", "pandas", "xlrd", "sqlite3", "flask", "fastapi"):
    try:
        m = __import__(mod)
        w(f"MODULE {mod}: OK", getattr(m, "__version__", ""))
    except Exception as e:
        w(f"MODULE {mod}: MISSING ({e})")

with open(r"C:\Users\Administrator\Desktop\ECAHelper\tools\_env_report.txt", "w", encoding="utf-8") as fh:
    fh.write(out.getvalue())
print("done")
