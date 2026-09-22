import collections
import glob
import io
import os
import re
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]  # tools/ 的上一级 = 项目根
SRC = ROOT / "OriginSource"
out = io.StringIO()
def w(*a): print(*a, file=out)
def norm(s):
    if s is None: return ""
    return re.sub(r"\s+"," ",str(s).replace("\xa0"," ")).strip()

files = sorted([x for x in glob.glob(os.path.join(SRC,"*.xlsx")) if not os.path.basename(x).startswith("~$")])

def load(fp):
    wb = load_workbook(fp, read_only=True, data_only=True)
    for sn in wb.sheetnames:
        ws = wb[sn]
        for i,r in enumerate(ws.iter_rows(values_only=True)):
            if i>5: break
            c=[norm(x) for x in r]
            if any(x=="Resourcename" for x in c) and any("Actuals Total in h" in x for x in c):
                hdr=c
                while hdr and hdr[-1]=="": hdr.pop()
                return wb, ws, i, hdr
    return wb, None, None, None

# ---- 1. Project ID 空行的 Task 分布 ----
blanktask = collections.Counter()
neg = []
strval = []
dupdetail = []
for fp in files:
    base=os.path.basename(fp)
    wb,ws,hi,hdr = load(fp)
    if ws is None: wb.close(); continue
    ti=hdr.index("Task"); pi=hdr.index("Project ID"); vi=hdr.index("Actuals Total in h")
    rows=list(ws.iter_rows(min_row=hi+2, values_only=True))
    for r in rows:
        c=[norm(x) for x in r]
        v=r[vi] if vi<len(r) else None
        if c[pi]=="" and (v not in (None,"")): blanktask[c[ti]]+=1
        if isinstance(v,(int,float)) and v<0: neg.append((base, c[0], c[pi], c[ti], v))
        if not isinstance(v,(int,float)) and v not in (None,""): strval.append((base, repr(v)))
    # duplicates
    cnt=collections.Counter(tuple(norm(x) for x in r[:vi+1]) for r in rows)
    dups=[(k,n) for k,n in cnt.items() if n>1]
    if dups:
        sample=dups[0]
        dupdetail.append((base, len(dups), sample[1], sample[0]))
    wb.close()

w("=== Project ID 为空的行，按 Task 分类（Top20）===")
for k,n in blanktask.most_common(20): w(f"   {k!r}: {n}")
w("总计空 Project ID 行:", sum(blanktask.values()))

w("\n=== 负工时行（冲销）===")
w("数量:", len(neg))
for x in neg[:15]: w("   ", x)

w("\n=== 非数值工时 ===")
for x in strval: w("   ", x)

w("\n=== 同文件内重复行明细样例 ===")
for base,n,cnt,key in dupdetail[:8]:
    w(f"{base}: {n} 组重复, 最大重复 {cnt} 次")
    w(f"    key={key[:9]}")
wb=None
with open(ROOT / "tools" / "_deep2_report.txt", "w", encoding="utf-8") as fh:
    fh.write(out.getvalue())
print("ok")
