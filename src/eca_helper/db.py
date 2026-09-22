"""SQLite 连接管理与 schema 初始化。

提供：
    get_connection(db_path=None) -> sqlite3.Connection
    init_schema(conn)                        -- 建表/索引（幂等）
    ensure_db()                             -- 确保库文件存在并建表，返回路径
    is_empty(db_path=None) -> bool          -- 库是否无明细数据（自举判定用）

连接统一开启 FOREIGN_KEYS 与行工厂（sqlite3.Row），便于按列名访问。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config import DB_PATH, SCHEMA_PATH

# schema 路径由 config 统一解析：非冻结 = <src>/eca_helper/schema.sql；
# 冻结 = _MEIPASS/eca_helper/schema.sql（由 PyInstaller --add-data 落到 bundle）。
_SCHEMA_PATH = Path(SCHEMA_PATH)


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """返回一个新的 SQLite 连接。

    db_path 为 None 时使用 config.DB_PATH（可写数据根下的 data/eca_helper.db）。
    连接开启外键约束，并使用 Row 工厂。
    """
    path = str(db_path) if db_path is not None else str(DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """执行 schema.sql 建表/索引（CREATE TABLE IF NOT EXISTS，幂等）。"""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def ensure_db(db_path: str | Path | None = None) -> Path:
    """确保数据库文件存在并完成建表，返回其路径。"""
    path = Path(db_path) if db_path is not None else DB_PATH
    path = path.resolve()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    conn = get_connection(path)
    try:
        init_schema(conn)
    finally:
        conn.close()
    return path


def reset_db(db_path: str | Path | None = None) -> Path:
    """删除并重建数据库（仅用于测试/重置）。"""
    path = Path(db_path) if db_path is not None else DB_PATH
    path = path.resolve()
    if path.exists():
        path.unlink()
    return ensure_db(path)


def is_empty(db_path: str | Path | None = None) -> bool:
    """判断数据库是否为空（无明细数据）。

    先 ``ensure_db`` 保证库文件与 schema 就绪（幂等），再统计核心明细表
    ``timesheet_record`` 的行数；为 0（或表缺失）即视为空库。
    供启动自举判定使用。
    """
    path = ensure_db(db_path)
    conn = get_connection(path)
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) AS n FROM timesheet_record")
            row = cur.fetchone()
        except sqlite3.OperationalError:
            # 极端情况下（schema 未建成）也按空库处理，交由自举流程重建
            return True
        return (row["n"] if row is not None else 0) == 0
    finally:
        conn.close()
