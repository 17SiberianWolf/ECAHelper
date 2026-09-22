"""Excel 数据表定位（系统设计书.md §4.1 / 附录A 陷阱一）。

定位策略：扫描每张 Sheet 的前若干行，找到「同时含 Resourcename 与 Actuals Total in h」
（大小写/空白/尾点归一）的行作为表头。不依赖表位置/表名。前两张 Sheet 通常为透视表，
全部忽略（即从第 1 张起遍历，由表头特征决定，无需硬编码跳过前两张）。
"""

from __future__ import annotations

import re

from config import (
    HEADER_ACTUALS,
    HEADER_RESOURCE,
    HEADER_SCAN_ROWS,
    LOCK_PREFIX,
    MASTER_DATA_HINTS,
)

_RESOURCE_KEY = "resourcename"
_ACTUALS_KEY = "actuals total in h"


def _hdr_key(value) -> str:
    """表头文本归一化键：去首尾空白、折叠空白、转小写、去尾点。"""
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.rstrip(".")
    return s


def should_skip(filename: str) -> bool:
    """是否应跳过该文件：~$ 锁文件 / 在管项目主数据（本期不导入）。"""
    base = filename.strip()
    if base.startswith(LOCK_PREFIX):
        return True
    low = base.lower()
    return any(hint.lower() in low for hint in MASTER_DATA_HINTS)


def detect_version(header_cells) -> str:
    """版本探测：表头含 'wh cost center' -> v2，否则 v1。"""
    keys = [_hdr_key(c) for c in header_cells]
    return "v2" if "wh cost center" in keys else "v1"


def locate_data_sheet(wb):
    """在 workbook 中定位数据表。

    返回 dict: {
        'sheet': sheet 名,
        'header_row': 表头行索引（0-based，相对 Sheet 内 iter_rows 顺序）,
        'header_cells': 表头行原始单元格列表,
        'version': 'v1' | 'v2',
    } 或 None（无法定位）。
    """
    for sn in wb.sheetnames:
        ws = wb[sn]
        max_row = min(ws.max_row or 0, HEADER_SCAN_ROWS)
        if max_row <= 0:
            continue
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= max_row:
                break
            cells = list(row)
            keys = [_hdr_key(c) for c in cells]
            has_resource = _RESOURCE_KEY in keys
            has_actuals = any(_ACTUALS_KEY in k for k in keys if k)
            if has_resource and has_actuals:
                # 去掉尾部空单元格，避免游离列干扰列索引
                while cells and _hdr_key(cells[-1]) == "":
                    cells.pop()
                return {
                    "sheet": sn,
                    "header_row": i,
                    "header_cells": cells,
                    "version": detect_version(cells),
                }
    return None
