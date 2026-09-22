"""表头 -> 内部字段列映射（系统设计书.md §4.2 / PRD §4）。

按「表头文本归一化键」查映射字典，得到内部字段与其列索引（0-based）。
缺失列 -> 索引 None -> 落库 NULL；未知列（v1 游离日期列、2023.10 的 real CC）-> 无映射 -> 忽略。

内部字段           v1（9 列）              v2（16~17 列）
name               Resourcename            Resourcename
resource_id        Resource ID             Resource ID
organization       Organization            Organization
cost_center        Cost Center             Cost Center
wh_cost_center     —                       WH Cost Center
project_id         Project ID              Project ID
project_name       Project                 Project
task               Task                    Task
wbs_nr             WBS Nr                  WBS Nr
to_wbs_no          —                       To WBS No.
to_cost_center     —                       To Cost Center
to_internal_order  —                       To Internal Order
to_reference_proj_no —                     To Reference Proj.No.
reference_proj_name   —                    Reference Proj.Name
actuals_total_h    Actuals Total in h      Actuals Total in h
transaction_group  —                       Transaction Group
site_type          —                       Site Type（部分文件无）
"""

from __future__ import annotations

import re

from eca_helper.parsers.excel_locator import _hdr_key, detect_version

# 归一化表头键 -> 内部字段名
_HEADER_MAP = {
    "resourcename": "name",
    "resource id": "resource_id",
    "organization": "organization",
    "cost center": "cost_center",
    "wh cost center": "wh_cost_center",
    "project id": "project_id",
    "project": "project_name",
    "task": "task",
    "wbs nr": "wbs_nr",
    "to wbs no": "to_wbs_no",
    "to cost center": "to_cost_center",
    "to internal order": "to_internal_order",
    "to reference proj.no": "to_reference_proj_no",
    "reference proj.name": "reference_proj_name",
    "actuals total in h": "actuals_total_h",
    "transaction group": "transaction_group",
    "site type": "site_type",
}


def build_column_map(header_cells):
    """根据表头单元格构建 内部字段 -> 列索引(0-based) 的字典。

    缺失字段不在字典中（即索引 None，落库 NULL）。版本探测通过 detect_version 完成。
    """
    column_map: dict[str, int] = {}
    for idx, cell in enumerate(header_cells):
        key = _hdr_key(cell)
        field = _HEADER_MAP.get(key)
        if field and field not in column_map:
            column_map[field] = idx
    return column_map


def detect_version(header_cells) -> str:
    """版本探测（转发 excel_locator.detect_version，保持模块内可用）。"""
    return detect_version(header_cells)
