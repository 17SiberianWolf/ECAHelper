"""审计日志服务（第二轮 T07 / 增量设计书 §6.2 / §6.3 / §6.4）。

对外提供：
    - write_audit()     写 1 条 audit_log；**整体 try/except，任何失败只
                        logger.warning，绝不抛出**（审计失败不得影响 HTTP 响应）；
    - query_logs()      时间范围 / 级别 / 类别 / 关键词 / 成败 筛选 + 服务端分页，
                        返回 (total, items)；
    - export_logs_csv() 导出全部命中记录为 CSV（utf-8-sig，中英双语表头），
                        返回 (path, filename)。

隐私红线（AC-07-5）：仅落本机 SQLite 与本机导出目录，**无任何远程上报/同步**。
"""

from __future__ import annotations

import calendar
import csv
import datetime
import io
import logging
import re
from typing import Optional

from config import EXPORT_DIR, EXPORT_PREFIX
from eca_helper.db import get_connection

_LOGGER = logging.getLogger("eca.audit")

_MAX_MESSAGE = 500
_MAX_DETAIL = 4000
_MAX_TARGET = 200
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200

# audit_log 输出字段顺序（与表定义一致）
AUDIT_FIELDS = (
    "id",
    "ts",
    "level",
    "category",
    "action",
    "target",
    "result",
    "status_code",
    "duration_ms",
    "request_id",
    "message",
    "detail",
)

# 中英双语表头（audit_log 字段不在 config.BILINGUAL 中，本模块自带一份）
_AUDIT_BILINGUAL = {
    "id": ("ID", "序号"),
    "ts": ("Timestamp", "时间"),
    "level": ("Level", "级别"),
    "category": ("Category", "类别"),
    "action": ("Action", "操作"),
    "target": ("Target", "对象"),
    "result": ("Result", "结果"),
    "status_code": ("Status Code", "状态码"),
    "duration_ms": ("Duration (ms)", "耗时(毫秒)"),
    "request_id": ("Request ID", "请求ID"),
    "message": ("Message", "消息"),
    "detail": ("Detail", "详情"),
}

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def _now_str() -> str:
    """本地时间字符串 'YYYY-MM-DD HH:MM:SS'。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clip(value, limit: int) -> Optional[str]:
    """截断为不超过 limit 个字符；None 原样返回。"""
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= limit else s[:limit]


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符（\\ % _），配合 ESCAPE '\\' 使用。"""
    return str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------
def write_audit(
    category: str,
    action: str,
    level: str = "INFO",
    target: Optional[str] = None,
    result: str = "ok",
    status_code: Optional[int] = None,
    duration_ms: Optional[int] = None,
    request_id: Optional[str] = None,
    message: Optional[str] = None,
    detail: Optional[str] = None,
    db_path=None,
) -> int:
    """写 1 条审计记录，返回自增 id（失败返回 0）。

    **绝不抛出**：任何异常只在日志里警告一次，保证不影响 HTTP 响应。
    """
    sql = (
        "INSERT INTO audit_log (ts, level, category, action, target, result, "
        "status_code, duration_ms, request_id, message, detail) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    )
    params = (
        _now_str(),
        (level or "INFO").upper(),
        category or "system",
        action or "system.unknown",
        _clip(target, _MAX_TARGET),
        result or "ok",
        status_code,
        duration_ms,
        request_id,
        _clip(message, _MAX_MESSAGE),
        _clip(detail, _MAX_DETAIL),
    )
    try:
        conn = get_connection(db_path)
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return int(cur.lastrowid or 0)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - 审计写入失败绝不影响业务
        try:
            _LOGGER.warning("审计写入失败（不影响业务）：%r", exc)
        except Exception:  # noqa: BLE001 - 连日志都失败也只能静默
            pass
        return 0


# ---------------------------------------------------------------------------
# 筛选条件构造
# ---------------------------------------------------------------------------
def _expand_bound(value, kind: str) -> Optional[str]:
    """把筛选边界展开为 ts 比较用的字符串。

    同时兼容两种输入：
        'YYYY-MM'     -> 起始：该月 01 日 00:00:00；结束：该月最后一日 23:59:59
        'YYYY-MM-DD'  -> 起始：当日 00:00:00；结束：当日 23:59:59
    无法解析时返回 None（即不加该条件）。
    """
    if not value:
        return None
    v = str(value).strip()
    m = _MONTH_RE.match(v)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if not (1 <= month <= 12):
            return None
        if kind == "start":
            return f"{year:04d}-{month:02d}-01 00:00:00"
        last_day = calendar.monthrange(year, month)[1]
        return f"{year:04d}-{month:02d}-{last_day:02d} 23:59:59"
    m = _DATE_RE.match(v)
    if m:
        return v + (" 00:00:00" if kind == "start" else " 23:59:59")
    return None


def _build_where(filters: dict) -> tuple[str, list]:
    """由筛选字典构造 (WHERE 子句, 参数列表)。"""
    f = filters or {}
    conds: list[str] = []
    params: list = []

    start = _expand_bound(f.get("start"), "start")
    if start:
        conds.append("ts >= ?")
        params.append(start)
    end = _expand_bound(f.get("end"), "end")
    if end:
        conds.append("ts <= ?")
        params.append(end)

    level = (f.get("level") or "").strip()
    if level:
        conds.append("level = ?")
        params.append(level.upper())

    category = (f.get("category") or "").strip()
    if category:
        conds.append("category = ?")
        params.append(category)

    result = (f.get("result") or f.get("ok") or "").strip()
    if result:
        conds.append("result = ?")
        params.append(result)

    keyword = (f.get("keyword") or "").strip()
    if keyword:
        like = "%" + _escape_like(keyword) + "%"
        conds.append(
            "(message LIKE ? ESCAPE '\\' OR target LIKE ? ESCAPE '\\' "
            "OR action LIKE ? ESCAPE '\\' OR request_id LIKE ? ESCAPE '\\')"
        )
        params.extend([like, like, like, like])

    return (" WHERE " + " AND ".join(conds)) if conds else "", params


def page_of(filters: dict) -> tuple[int, int]:
    """解析分页参数，返回 (page, page_size)。page_size 上限 _MAX_PAGE_SIZE。"""
    f = filters or {}

    def _int(key: str, default: int) -> int:
        try:
            return int(str(f.get(key) or default).strip())
        except (TypeError, ValueError):
            return default

    page = max(1, _int("page", 1))
    page_size = min(_MAX_PAGE_SIZE, max(1, _int("page_size", _DEFAULT_PAGE_SIZE)))
    return page, page_size


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------
def query_logs(filters: dict, conn=None) -> tuple[int, list[dict]]:
    """筛选 + 服务端分页查询审计日志，返回 (total, items)。

    filters 键：start / end / level / category / keyword / result(或 ok) / page / page_size
    排序：ts DESC, id DESC。
    """
    where, params = _build_where(filters)
    page, page_size = page_of(filters)
    offset = (page - 1) * page_size

    own_conn = conn is None
    conn = conn or get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM audit_log" + where, params)
        row = cur.fetchone()
        total = int(row["n"]) if row else 0
        cur.execute(
            "SELECT " + ", ".join(AUDIT_FIELDS) + " FROM audit_log" + where
            + " ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )
        items = [dict(x) for x in cur.fetchall()]
        return total, items
    except Exception as exc:  # noqa: BLE001 - 查询失败按空结果处理并记警告
        _LOGGER.warning("审计查询失败：%r", exc)
        return 0, []
    finally:
        if own_conn:
            conn.close()


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------
def export_logs_csv(filters: dict, conn=None) -> tuple[str, str]:
    """导出全部命中记录为 CSV（utf-8-sig，中英双语表头），返回 (绝对路径, 文件名)。"""
    where, params = _build_where(filters)

    own_conn = conn is None
    conn = conn or get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT " + ", ".join(AUDIT_FIELDS) + " FROM audit_log" + where
            + " ORDER BY ts DESC, id DESC",
            params,
        )
        rows = [dict(x) for x in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001 - 导出失败按空数据集处理
        _LOGGER.warning("审计导出查询失败：%r", exc)
        rows = []
    finally:
        if own_conn:
            conn.close()

    headers = [f"{en} / {zh}" for en, zh in (_AUDIT_BILINGUAL[k] for k in AUDIT_FIELDS)]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for r in rows:
        writer.writerow(["" if r.get(k) is None else r.get(k) for k in AUDIT_FIELDS])
    content = buf.getvalue()

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{EXPORT_PREFIX}_系统日志_{ts}.csv"
    path = EXPORT_DIR / filename
    # 注意：不要用 write_text —— csv.writer 默认行尾 \r\n，write_text 在 Windows
    # 会二次转换导致空行。直接写 bytes，避免行尾被再次改写。
    path.write_bytes(content.encode("utf-8-sig"))
    return str(path), filename
