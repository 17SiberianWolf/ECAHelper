"""ECAHelper 全局配置与常量（三态路径可移植化）。

路径约定（见 重构设计书.md §3）：
    本项目同时支持三种运行形态，路径由唯一的探测函数 ``_detect()`` 解析：

    ① 开发直跑     ``python src\\app.py``           （资源根 == 数据根 == 项目根）
    ② 项目内 venv  ``<root>\\.venv\\Scripts\\python src\\app.py``（同 ①）
    ③ 冻结 onedir  ``dist\\ECAHelper\\ECAHelper.exe``（PyInstaller）

    为支持「只读资源」与「可写数据」分离，引入两个基准目录：

    BUNDLE_DIR  只读资源根（模板/静态/schema）：
                 · 非冻结 -> 项目根
                 · 冻结   -> ``sys._MEIPASS``（PyInstaller 6.x onedir 下即
                             ``dist\\ECAHelper\\_internal``）
    APP_DIR     可写数据根（DB / 导出）：
                 · 非冻结 -> 项目根
                 · 冻结   -> exe 所在目录；若该目录不可写则回退到
                             ``%LOCALAPPDATA%\\ECAHelper``（决策 3，仅日志、不致命）
    INSTALL_DIR 安装目录（冻结态用于定位随包分发的 ``OriginSource``）：
                 · 非冻结 -> 项目根
                 · 冻结   -> exe 所在目录（``OriginSource`` 由打包脚本复制到此处）

    派生路径：
        DB_PATH     = APP_DIR / data / eca_helper.db
        EXPORT_DIR  = APP_DIR / data / exports
        ORIGIN_DIR  = INSTALL_DIR / OriginSource
        TEMPLATE_DIR= BUNDLE_DIR / web / templates
        STATIC_DIR  = BUNDLE_DIR / web / static
        SCHEMA_PATH = 冻结态 BUNDLE_DIR/eca_helper/schema.sql，
                      否则 <src>/eca_helper/schema.sql

    ROOT 仅作向后兼容保留，语义 = 可写数据根（APP_DIR）；重构后仓库内除 app.py 外
    无模块再用 ROOT 拼接 templates/static（已全部改用 TEMPLATE_DIR/STATIC_DIR）。

归一化规则、双语字段映射（BILINGUAL）、业务枚举中文映射、跳过规则等均在此集中定义，
供 parsers / queries / routes / templates 复用，避免跨文件重复硬编码。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_FROZEN = getattr(sys, "frozen", False)


def _detect() -> tuple[Path, Path]:
    """探测 (BUNDLE_DIR, INSTALL_DIR)。

    · 冻结（PyInstaller onedir）：BUNDLE_DIR = ``sys._MEIPASS``（只读资源），
      INSTALL_DIR = 可执行文件所在目录。
    · 非冻结：BUNDLE_DIR = INSTALL_DIR = 项目根（``src/`` 的上一级）。
    """
    if _FROZEN:
        bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        install = Path(sys.executable).resolve().parent
        return bundle, install
    src_dir = Path(__file__).resolve().parent  # config.py 位于 src/
    root = src_dir.parent  # 项目根（含 src/web/data/OriginSource）
    return root, root


def _writable_base(install: Path) -> Path:
    """返回可写数据根。

    非冻结直接返回项目根；冻结态优先用 exe 目录，若不可写则回退到
    ``%LOCALAPPDATA%\\ECAHelper`` 并打印一行说明（决策 3：简单、有日志、绝不致命）。
    """
    if not _FROZEN:
        return install
    try:
        install.mkdir(parents=True, exist_ok=True)
        probe = install / ".eca_write_test"
        probe.write_bytes(b"")
        probe.unlink()
        return install
    except OSError:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        fallback = Path(base) / "ECAHelper"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # 极端情况下仍不强抛，交由后续写入报错暴露
        print(f"[ECAHelper] 程序目录不可写，运行数据将存储于: {fallback}", flush=True)
        return fallback


# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
BUNDLE_DIR, INSTALL_DIR = _detect()
APP_DIR = _writable_base(INSTALL_DIR)

SRC_DIR = Path(__file__).resolve().parent if not _FROZEN else APP_DIR
ROOT = APP_DIR  # 兼容旧引用；语义 = 可写数据根

DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "eca_helper.db"
EXPORT_DIR = DATA_DIR / "exports"

ORIGIN_DIR = INSTALL_DIR / "OriginSource"

TEMPLATE_DIR = BUNDLE_DIR / "web" / "templates"
STATIC_DIR = BUNDLE_DIR / "web" / "static"

SCHEMA_PATH = (
    (BUNDLE_DIR / "eca_helper" / "schema.sql")
    if _FROZEN
    else (Path(__file__).resolve().parent / "eca_helper" / "schema.sql")
)

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
    """确保运行时目录存在（数据库目录 + 导出目录）。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
