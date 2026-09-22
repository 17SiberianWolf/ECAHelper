"""归一化与基础解析函数（系统设计书.md §3.3 / §4.3 / §4.4）。

核心规则（务必全局一致，所有模块统一调用此处）：
    resource_id_norm : str(v).strip().upper()；空/None -> '__UNKNOWN__'
    project_id_norm  : 空/None -> None（非项目工时）；否则 str(v).strip().upper()
                       （先统一转字符串，故 int 70463 / float 0.0001 都可比）
    name             : str(v).strip()（原样）
    report_month     : 仅来自文件名（见 parse_month）
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime

from config import MONTH_PATTERN, UNKNOWN_RESOURCE

_MONTH_RE = re.compile(MONTH_PATTERN)


def normalize_resource_id(value) -> str:
    """Resource ID 归一化：去空格 + 大写；空/None -> '__UNKNOWN__'。"""
    if value is None:
        return UNKNOWN_RESOURCE
    s = str(value).strip().upper()
    return UNKNOWN_RESOURCE if s == "" else s


def normalize_project_id(value):
    """Project ID 归一化：空/None -> None（非项目工时）；否则去空格 + 大写。

    先 str() 再清洗，保证 int 70463 / float 0.0001 等形态统一可比。
    """
    if value is None:
        return None
    s = str(value).strip().upper()
    return None if s == "" else s


def normalize_name(value) -> str:
    """姓名原样存储（仅去首尾空白）。"""
    return str(value).strip() if value is not None else ""


def to_str(value):
    """通用字符串化（组织 / 成本中心等）：保留前导零，空 -> None。

    数值型（如 587 / 0.0001）先转字符串，避免把 '0527' 这类文本误当数字丢前导零；
    但若源本就是数字 527，则如实存 '527'（与 '0527' 文本由源决定，二者在源中本就不同）。
    """
    if value is None:
        return None
    s = str(value).strip()
    return s if s != "" else None


def parse_month(filename: str):
    """从文件名解析报告月份 YYYY-MM（仅认文件名，忽略表内日期）。

    兼容 'Timesheet of 2023.6 including SC.xlsx' -> 2023-06
          '2025.01including SC.xlsx'            -> 2025-01（月份与 including 缺空格）
    解析失败返回 None。
    """
    if not filename:
        return None
    m = _MONTH_RE.search(filename)
    if not m:
        return None
    year, month = m.group(1), int(m.group(2))
    if 1 <= month <= 12:
        return f"{year}-{month:02d}"
    return None


def parse_actuals(cell):
    """解析 Actuals 单元格 -> (hours: float, raw_text: str, is_anomaly: bool)。

    规则（系统设计书.md §4.6）：
        datetime/date -> 异常，hours=0，raw_text=str(value)
        None / ''     -> hours=0，raw_text=''
        可转 float     -> hours=float，raw_text=str(value)
        其它字符串     -> 异常，hours=0，raw_text=str(value)
    """
    if isinstance(cell, (datetime, date)):
        return 0.0, str(cell), True
    if cell is None:
        return 0.0, "", False
    if isinstance(cell, (int, float)):
        return float(cell), _num_text(cell), False
    s = str(cell).strip()
    if s == "":
        return 0.0, "", False
    try:
        return float(s), s, False
    except ValueError:
        return 0.0, s, True


def _num_text(value) -> str:
    """数值转原始文本（用于溯源/去重指纹）。int 320 -> '320'，float 320.0 -> '320.0'。"""
    if isinstance(value, float):
        # 去掉无意义的 .0 后缀以保持可读（去重仅用于同文件同内容判断，稳定即可）
        if value == int(value):
            return str(int(value))
        return repr(value)
    return str(value)


def row_fingerprint(*fields) -> str:
    """计算稳定行哈希（去重用）。fields 为业务列元组。"""
    h = hashlib.sha256()
    for f in fields:
        h.update(("\x1f" + ("" if f is None else str(f))).encode("utf-8"))
    return h.hexdigest()


def wbs_next_level(wbs: str, prefix: str = ""):
    """返回 WBS Nr 在 prefix 下的「下一级前缀」。

    prefix=''                  -> 取第一段（首个 '.' 之前）
    prefix='O 1830.061'         -> 'O 1830.061.<下一段>'
    不属于该 prefix 子树或无法下钻时返回 None。
    """
    if not wbs:
        return None
    if prefix:
        if not wbs.startswith(prefix + "."):
            return None
        rest = wbs[len(prefix) + 1 :]
        nxt = rest.split(".", 1)[0]
        return prefix + "." + nxt
    return wbs.split(".", 1)[0]


def month_iter(start: str, end: str):
    """生成 [start, end] 闭区间内所有 YYYY-MM（升序）。"""
    y0, m0 = (int(x) for x in start.split("-"))
    y1, m1 = (int(x) for x in end.split("-"))
    total0 = y0 * 12 + (m0 - 1)
    total1 = y1 * 12 + (m1 - 1)
    for t in range(total0, total1 + 1):
        y, m = divmod(t, 12)
        yield f"{y}-{m + 1:02d}"
