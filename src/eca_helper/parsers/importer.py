"""Excel 导入管线（系统设计书.md §4 / T05）。

职责：
    - 遍历文件（默认跳过 ~$ 锁文件与在管项目主数据）；
    - 定位数据表（excel_locator.locate_data_sheet）；
    - 解析报告月份（normalizer.parse_month，仅文件名）；
    - 幂等控制（Q4：同名文件默认 skip 不翻倍）；
    - 逐行归一化（resource_id / project_id / name）；
    - 去重（normalizer.row_fingerprint，按文件内整行）；
    - 异常检测（Actuals 日期型 / 非数值）；
    - 批量落库 import_batch + timesheet_record，并维护 person 表；
    - 返回 ImportReport（新增行 / 跳过 / 各项标记计数）。

所有模块统一调用 normalizer 的归一化函数，确保跨文件规则一致。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from config import UNKNOWN_RESOURCE
from eca_helper.db import get_connection
from eca_helper.parsers import normalizer
from eca_helper.parsers.excel_locator import locate_data_sheet, should_skip
from eca_helper.parsers.field_mapper import build_column_map
from eca_helper.services import person_service

# timesheet_record 落库列（顺序需与 _insert_records 的元组一致）
_COLUMNS = [
    "import_batch_id",
    "resource_id_norm",
    "resource_id_raw",
    "name_snapshot",
    "organization",
    "cost_center",
    "wh_cost_center",
    "project_id_norm",
    "project_id_raw",
    "project_name",
    "task",
    "wbs_nr",
    "to_wbs_no",
    "to_cost_center",
    "to_internal_order",
    "to_reference_proj_no",
    "reference_proj_name",
    "actuals_total_h",
    "actuals_raw_text",
    "transaction_group",
    "site_type",
    "report_month",
    "source_file",
    "source_sheet",
    "source_row",
    "is_duplicate",
    "dup_group_key",
    "is_anomaly_actuals",
]
_N_COLS = len(_COLUMNS)  # 28


@dataclass
class ImportReport:
    """一次导入任务的汇总报告（供 API / 质量面板消费）。"""

    files_total: int = 0
    files_imported: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    new_rows: int = 0
    duplicate_rows: int = 0
    anomaly_rows: int = 0
    zero_rows: int = 0
    empty_rid_rows: int = 0
    failed_files: list = field(default_factory=list)  # [(filename, reason)]
    per_file: list = field(default_factory=list)  # [dict]

    def to_dict(self) -> dict:
        return {
            "files_total": self.files_total,
            "files_imported": self.files_imported,
            "files_skipped": self.files_skipped,
            "files_failed": self.files_failed,
            "new_rows": self.new_rows,
            "duplicate_rows": self.duplicate_rows,
            "anomaly_rows": self.anomaly_rows,
            "zero_rows": self.zero_rows,
            "empty_rid_rows": self.empty_rid_rows,
            "failed_files": self.failed_files,
            "per_file": self.per_file,
        }


# ---------------------------------------------------------------------------
# 公共入口
# ---------------------------------------------------------------------------
def import_files(paths, mode: str = "skip", db_path=None) -> ImportReport:
    """导入给定路径列表（文件或目录）。

    mode:
        'skip'      -> 已存在同名批次则跳过（Q4 默认，不翻倍）
        'overwrite' -> 删除旧批次后重新导入
        'copy'      -> 强制以新批次再导入一份（会翻倍，谨慎使用）
    返回 ImportReport。
    """
    files = _expand_paths(paths)
    report = ImportReport(files_total=len(files))
    conn = get_connection(db_path)
    try:
        for path in files:
            # 逐文件兜底（健壮性修复）：任何单文件异常都不得中断整批导入，
            # 记录失败后继续处理其余文件。
            try:
                import_one_file(conn, Path(path), mode, report)
            except Exception as exc:  # noqa: BLE001 - 单文件失败记录后继续
                name = Path(path).name
                report.files_failed += 1
                report.failed_files.append((name, f"未捕获异常: {exc!r}"))
                report.per_file.append(
                    {"file": name, "status": "failed", "reason": "unhandled"}
                )
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001 - 回滚失败不影响继续处理
                    pass
    finally:
        conn.close()
    return report


def import_directory(directory, mode: str = "skip", db_path=None) -> ImportReport:
    """便捷入口：直接导入一个目录下的全部 .xlsx。"""
    return import_files([directory], mode=mode, db_path=db_path)


# ---------------------------------------------------------------------------
# 单文件导入
# ---------------------------------------------------------------------------
def import_one_file(conn, path: Path, mode: str, report: ImportReport) -> None:
    name = path.name

    # 幂等控制（Q4）
    existing = _find_existing_batch(conn, name)
    if existing:
        if mode == "skip":
            report.files_skipped += 1
            report.per_file.append({"file": name, "status": "skipped"})
            return
        if mode == "overwrite":
            _delete_batch(conn, name)
        # mode == 'copy' 则不处理，直接继续导入新批次

    # 报告月份（仅文件名）
    month = normalizer.parse_month(name)
    if month is None:
        report.files_failed += 1
        report.failed_files.append((name, "无法从文件名解析报告月份"))
        report.per_file.append({"file": name, "status": "failed", "reason": "month"})
        return

    # 打开工作簿
    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - 导入期容错，记录失败而非中断
        report.files_failed += 1
        report.failed_files.append((name, f"打开失败: {exc}"))
        report.per_file.append({"file": name, "status": "failed", "reason": "open"})
        return

    try:
        loc = locate_data_sheet(wb)
        if loc is None:
            report.files_failed += 1
            report.failed_files.append((name, "无法定位数据表（缺少 Resourcename/Actuals 表头）"))
            report.per_file.append({"file": name, "status": "failed", "reason": "locate"})
            return
        column_map = build_column_map(loc["header_cells"])
        ws = wb[loc["sheet"]]
        rows = _extract_rows(ws, loc["header_row"], column_map, name, month)
    finally:
        wb.close()

    if not rows:
        report.files_failed += 1
        report.failed_files.append((name, "数据行为空"))
        report.per_file.append({"file": name, "status": "failed", "reason": "empty"})
        return

    # 去重标记（按文件内整行指纹）
    _mark_duplicates(rows, name)

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
    batch_id = f"{path.stem}-{ts}"
    dup_count = sum(1 for r in rows if r["is_duplicate"])
    anomaly_count = sum(1 for r in rows if r["is_anomaly_actuals"])
    zero_count = sum(1 for r in rows if r["actuals_total_h"] == 0.0)
    empty_rid = sum(1 for r in rows if r["resource_id_norm"] == UNKNOWN_RESOURCE)

    # ---- 落库段（健壮性修复）：整段 try/except 包裹 ----
    # 一旦 INSERT import_batch / _insert_records / commit / person 维护任一失败，
    # 回滚本次写入并把该文件记入 failed_files，然后 return（不 raise），
    # 由 import_files 循环继续处理其余文件，避免“部分库”中断整批导入。
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO import_batch (id, source_file, parsed_month, imported_at, "
            "row_count, anomaly_count, duplicate_count, status) "
            "VALUES (?,?,?,?,?,?,?, 'done')",
            (
                batch_id,
                name,
                month,
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
                len(rows),
                anomaly_count,
                dup_count,
            ),
        )
        _insert_records(cur, rows, batch_id, name, loc["sheet"])
        conn.commit()

        # 维护 person 表（新增/补别名/重算 canonical）
        person_service.ensure_persons_for_batch(conn, rows, batch_id)
    except Exception as exc:  # noqa: BLE001 - 落库失败不得中断整批
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001 - 回滚失败不影响继续处理
            pass
        report.files_failed += 1
        report.failed_files.append((name, f"落库失败: {exc!r}"))
        report.per_file.append({"file": name, "status": "failed", "reason": "db_write"})
        return

    # ---- 成功路径：统计与 per_file 记录（行为保持不变）----
    report.files_imported += 1
    report.new_rows += len(rows)
    report.duplicate_rows += dup_count
    report.anomaly_rows += anomaly_count
    report.zero_rows += zero_count
    report.empty_rid_rows += empty_rid
    report.per_file.append(
        {
            "file": name,
            "status": "imported",
            "rows": len(rows),
            "month": month,
            "version": loc["version"],
            "duplicates": dup_count,
            "anomalies": anomaly_count,
            "zeros": zero_count,
            "empty_rid": empty_rid,
        }
    )


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _expand_paths(paths) -> list[Path]:
    """展开路径列表（目录递归收集 .xlsx，文件直收），并过滤跳过项。"""
    result: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            for f in sorted(pp.rglob("*.xlsx")):
                if not should_skip(f.name):
                    result.append(f)
        elif pp.is_file():
            if not should_skip(pp.name):
                result.append(pp)
        # 不存在的路径忽略
    return result


def _find_existing_batch(conn, source_file: str):
    cur = conn.cursor()
    cur.execute("SELECT id FROM import_batch WHERE source_file=?", (source_file,))
    return cur.fetchone()


def _delete_batch(conn, source_file: str) -> None:
    cur = conn.cursor()
    cur.execute("SELECT id FROM import_batch WHERE source_file=?", (source_file,))
    ids = [r["id"] for r in cur.fetchall()]
    for bid in ids:
        cur.execute("DELETE FROM timesheet_record WHERE import_batch_id=?", (bid,))
    cur.execute("DELETE FROM import_batch WHERE source_file=?", (source_file,))
    conn.commit()


def _is_blank_row(raw) -> bool:
    """整行全空（None 或仅空白字符串）视为空行，跳过。"""
    for v in raw:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return False
    return True


def _extract_rows(ws, header_row: int, column_map: dict, source_file: str, month: str) -> list[dict]:
    """从 header_row 之后读取数据行并构建明细 dict 列表。"""
    rows: list[dict] = []
    start = header_row + 2  # openpyxl 1-based 行号：表头在 header_row+1，数据从 +2 起
    for i, raw in enumerate(ws.iter_rows(min_row=start, values_only=True)):
        sheet_row = start + i
        if _is_blank_row(raw):
            continue
        rows.append(_build_record(raw, column_map, source_file, ws.title, sheet_row, month))
    return rows


def _build_record(raw, column_map: dict, source_file: str, sheet_name: str,
                  sheet_row: int, month: str) -> dict:
    def g(field_name: str):
        idx = column_map.get(field_name)
        if idx is None or idx >= len(raw):
            return None
        return raw[idx]

    resource_id_raw = normalizer.to_str(g("resource_id"))
    name_snapshot = normalizer.normalize_name(g("name"))
    organization = normalizer.to_str(g("organization"))
    cost_center = normalizer.to_str(g("cost_center"))
    wh_cost_center = normalizer.to_str(g("wh_cost_center"))
    project_id_raw = normalizer.to_str(g("project_id"))
    project_name = normalizer.to_str(g("project_name"))
    task = normalizer.to_str(g("task"))
    wbs_nr = normalizer.to_str(g("wbs_nr"))
    to_wbs_no = normalizer.to_str(g("to_wbs_no"))
    to_cost_center = normalizer.to_str(g("to_cost_center"))
    to_internal_order = normalizer.to_str(g("to_internal_order"))
    to_reference_proj_no = normalizer.to_str(g("to_reference_proj_no"))
    reference_proj_name = normalizer.to_str(g("reference_proj_name"))
    transaction_group = normalizer.to_str(g("transaction_group"))
    site_type = normalizer.to_str(g("site_type"))

    hours, raw_text, is_anomaly = normalizer.parse_actuals(g("actuals_total_h"))

    resource_id_norm = normalizer.normalize_resource_id(resource_id_raw)
    project_id_norm = normalizer.normalize_project_id(project_id_raw)

    return {
        "resource_id_norm": resource_id_norm,
        "resource_id_raw": resource_id_raw,
        "name_snapshot": name_snapshot,
        "organization": organization,
        "cost_center": cost_center,
        "wh_cost_center": wh_cost_center,
        "project_id_norm": project_id_norm,
        "project_id_raw": project_id_raw,
        "project_name": project_name,
        "task": task,
        "wbs_nr": wbs_nr,
        "to_wbs_no": to_wbs_no,
        "to_cost_center": to_cost_center,
        "to_internal_order": to_internal_order,
        "to_reference_proj_no": to_reference_proj_no,
        "reference_proj_name": reference_proj_name,
        "actuals_total_h": hours,
        "actuals_raw_text": raw_text,
        "transaction_group": transaction_group,
        "site_type": site_type,
        "report_month": month,
        "source_file": source_file,
        "source_sheet": sheet_name,
        "source_row": sheet_row,
        "is_duplicate": 0,
        "dup_group_key": None,
        "is_anomaly_actuals": 1 if is_anomaly else 0,
    }


def _mark_duplicates(rows: list[dict], source_file: str) -> None:
    """按文件内整行指纹标记重复：首行保留，其余 is_duplicate=1。"""
    groups: dict[str, list[dict]] = {}
    for rec in rows:
        fp = normalizer.row_fingerprint(
            rec["resource_id_raw"],
            rec["project_id_raw"],
            rec["name_snapshot"],
            rec["organization"],
            rec["cost_center"],
            rec["task"],
            rec["wbs_nr"],
            rec["to_wbs_no"],
            rec["actuals_raw_text"],
            rec["report_month"],
        )
        groups.setdefault(fp, []).append(rec)
    for fp, recs in groups.items():
        if len(recs) > 1:
            key = f"{source_file}#{fp[:12]}"
            for rec in recs[1:]:
                rec["is_duplicate"] = 1
                rec["dup_group_key"] = key


def _insert_records(cur, rows: list[dict], batch_id: str, source_file: str,
                    sheet_name: str) -> None:
    data = []
    for r in rows:
        data.append(
            (
                batch_id,
                r["resource_id_norm"],
                r["resource_id_raw"],
                r["name_snapshot"],
                r["organization"],
                r["cost_center"],
                r["wh_cost_center"],
                r["project_id_norm"],
                r["project_id_raw"],
                r["project_name"],
                r["task"],
                r["wbs_nr"],
                r["to_wbs_no"],
                r["to_cost_center"],
                r["to_internal_order"],
                r["to_reference_proj_no"],
                r["reference_proj_name"],
                r["actuals_total_h"],
                r["actuals_raw_text"],
                r["transaction_group"],
                r["site_type"],
                r["report_month"],
                source_file,
                sheet_name,
                r["source_row"],
                r["is_duplicate"],
                r["dup_group_key"],
                r["is_anomaly_actuals"],
            )
        )
    placeholders = ",".join(["?"] * _N_COLS)
    sql = f"INSERT INTO timesheet_record ({','.join(_COLUMNS)}) VALUES ({placeholders})"
    cur.executemany(sql, data)
