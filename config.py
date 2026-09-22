"""ECAHelper 全局配置与常量。

路径约定（见 系统设计书.md §8）：
    ROOT        = 项目根目录 (本文件所在目录)
    DB_PATH     = ROOT/eca_helper.db
    ORIGIN_DIR  = ROOT/OriginSource
    EXPORT_DIR  = ROOT/data/exports

归一化规则、双语字段映射（BILINGUAL）、业务枚举中文映射、跳过规则等均在此集中定义，
供 parsers / queries / routes / templates 复用，避免跨文件重复硬编码。
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "eca_helper.db"
ORIGIN_DIR = ROOT / "OriginSource"
EXPORT_DIR = ROOT / "data" / "exports"
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"

# 启动端口（决策 +2：固定 5000，被占用则 +1 回退）
APP_PORT = 5000

# ---------------------------------------------------------------------------
# 归一化规则常量
# ---------------------------------------------------------------------------
# 空 Resource ID 桶（决策 Q1：原样落库，归入「未标识人员」）
UNKNOWN_RESOURCE = "__UNKNOWN__"

# 文件名月份解析正则（决策：仅认文件名；兼容 2025.01including 这类缺空格写法）
MONTH_PATTERN = r"(20\d{2})\.(\d{1,2})"

# Excel 数据表定位特征（见 系统设计书.md §4.1 / 附录A 陷阱一）
HEADER_RESOURCE = "Resourcename"
HEADER_ACTUALS = "Actuals Total in h"
HEADER_SCAN_ROWS = 12  # 每张 Sheet 扫描前 N 行定位表头

# 跳过规则（决策：~$ 锁文件 / 在管项目主数据 本期不导入）
LOCK_PREFIX = "~$"
MASTER_DATA_HINTS = ("在管项目", "master project", "project master")

# ---------------------------------------------------------------------------
# 双语字段映射表（导出表头 + 质量面板用，见 系统设计书.md §8）
# 内部字段 -> (EN, ZH)
# ---------------------------------------------------------------------------
BILINGUAL = {
    "report_month": ("Report Month", "报告月份"),
    "resource_id_norm": ("Resource ID", "资源号"),
    "name_snapshot": ("Resourcename", "姓名"),
    "organization": ("Organization", "组织"),
    "cost_center": ("Cost Center", "成本中心"),
    "project_id_norm": ("Project ID", "项目号"),
    "project_name": ("Project", "项目名称"),
    "task": ("Task", "任务"),
    "wbs_nr": ("WBS Nr", "WBS 编号"),
    "actuals_total_h": ("Actuals Total in h", "实际工时(h)"),
    "source_file": ("Source File", "源文件"),
    "source_row": ("Source Row", "源行号"),
}

# 导出列顺序（含上述内部字段；task_zh 为可选业务枚举中文映射列，见 Q7）
EXPORT_COLUMNS = [
    "report_month",
    "resource_id_norm",
    "name_snapshot",
    "organization",
    "cost_center",
    "project_id_norm",
    "project_name",
    "task",
    "task_zh",
    "wbs_nr",
    "actuals_total_h",
    "source_file",
    "source_row",
]

# 业务枚举中文映射（Q7：可选附注列）
BUSINESS_ENUM_ZH = {
    "Leave": "休假",
    "Procurement services": "采购服务",
    "SCF (Annual Leave)": "年假",
    "SCF (Sick Leave)": "病假",
}

# 质量面板排除类别
EXCLUSION_CATEGORIES = ("duplicate", "anomaly", "zero", "empty_rid")

# 导出文件命名约定（决策 +3）：导出_<类型>_<YYYYMMDD_HHMM>.<xlsx|csv>
EXPORT_PREFIX = "导出"


def bilingual_header(field: str, lang: str = "both") -> str:
    """返回某内部字段的导出表头。

    lang:
        'both' -> "Project ID / 项目号"
        'en'   -> "Project ID"
        'zh'   -> "项目号"
    """
    en, zh = BILINGUAL.get(field, (field, field))
    if lang == "en":
        return en
    if lang == "zh":
        return zh
    return f"{en} / {zh}"


def ensure_dirs() -> None:
    """确保运行时目录存在（导出目录）。"""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
