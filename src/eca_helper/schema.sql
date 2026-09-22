-- ECAHelper 建表 SQL（与 eca_helper/db.py 同步，便于审阅）
-- SQLite 语法，含索引。CREATE TABLE IF NOT EXISTS 保证幂等。

-- 每次导入一批的元信息
CREATE TABLE IF NOT EXISTS import_batch (
  id             TEXT PRIMARY KEY,            -- e.g. <filename>-<timestamp>
  source_file    TEXT NOT NULL,
  parsed_month   TEXT NOT NULL,               -- YYYY-MM（来自文件名）
  imported_at    TEXT NOT NULL,               -- ISO 8601 UTC
  row_count      INTEGER NOT NULL DEFAULT 0,
  anomaly_count  INTEGER NOT NULL DEFAULT 0,
  duplicate_count INTEGER NOT NULL DEFAULT 0,
  status         TEXT NOT NULL DEFAULT 'done',
  note           TEXT
);
CREATE INDEX IF NOT EXISTS idx_batch_month ON import_batch(parsed_month);
CREATE INDEX IF NOT EXISTS idx_batch_file  ON import_batch(source_file);

-- 人员（Resource ID 主键）
CREATE TABLE IF NOT EXISTS person (
  resource_id_norm  TEXT PRIMARY KEY,         -- 归一化主键；空 ID = '__UNKNOWN__'
  canonical_name    TEXT,                     -- 规范显示名（出现最多写法）
  name_aliases      TEXT,                     -- JSON 数组：全部姓名写法
  first_organization TEXT,
  first_cost_center   TEXT,
  first_seen_batch    TEXT,
  merged_into       TEXT                      -- 若被合并到另一 ID（Q2）
);

-- 核心明细表（行级落库 + 审计标记）
CREATE TABLE IF NOT EXISTS timesheet_record (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id   TEXT NOT NULL,
  resource_id_norm  TEXT,                     -- FK person；空→'__UNKNOWN__'
  resource_id_raw   TEXT,
  name_snapshot     TEXT,
  organization      TEXT,
  cost_center       TEXT,
  wh_cost_center    TEXT,
  project_id_norm   TEXT,                     -- 归一化匹配键；NULL/空→非项目工时
  project_id_raw    TEXT,
  project_name      TEXT,
  task              TEXT,
  wbs_nr            TEXT,
  to_wbs_no         TEXT,
  to_cost_center    TEXT,
  to_internal_order TEXT,
  to_reference_proj_no TEXT,
  reference_proj_name   TEXT,
  actuals_total_h   REAL NOT NULL DEFAULT 0,  -- 异常行置 0，原值存 actuals_raw_text
  actuals_raw_text  TEXT,                     -- 日期型/异常原始值（质量面板溯源）
  transaction_group TEXT,
  site_type         TEXT,
  report_month      TEXT NOT NULL,            -- YYYY-MM（权威时间，文件名派生）
  source_file       TEXT NOT NULL,
  source_sheet      TEXT NOT NULL,
  source_row        INTEGER NOT NULL,
  is_duplicate      INTEGER NOT NULL DEFAULT 0,
  dup_group_key     TEXT,                     -- 同文件内重复组指纹（NULL=非重复）
  is_anomaly_actuals INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (import_batch_id) REFERENCES import_batch(id)
);
CREATE INDEX IF NOT EXISTS idx_ts_batch  ON timesheet_record(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_ts_proj   ON timesheet_record(project_id_norm);
CREATE INDEX IF NOT EXISTS idx_ts_person ON timesheet_record(resource_id_norm);
CREATE INDEX IF NOT EXISTS idx_ts_month  ON timesheet_record(report_month);
CREATE INDEX IF NOT EXISTS idx_ts_src    ON timesheet_record(source_file, source_row);
CREATE INDEX IF NOT EXISTS idx_ts_dup    ON timesheet_record(dup_group_key);

-- 统计排除规则（Q3：默认不排除，勾选后持久化）
CREATE TABLE IF NOT EXISTS exclusion (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  category    TEXT NOT NULL,   -- 'duplicate'|'anomaly'|'zero'|'empty_rid'
  target_key  TEXT NOT NULL,   -- duplicate: source_file+'#'+hash; 其余: source_file+'|'+source_row
  excluded    INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT,
  UNIQUE(category, target_key)
);

-- 人员合并映射（Q2：默认不自动，手动合并）
CREATE TABLE IF NOT EXISTS person_merge (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  from_resource_id_norm TEXT NOT NULL,
  to_resource_id_norm   TEXT NOT NULL,
  created_at  TEXT,
  note        TEXT
);

-- 查询快照（P2-3，预留）
CREATE TABLE IF NOT EXISTS saved_view (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  query_type  TEXT NOT NULL,
  params      TEXT NOT NULL,   -- JSON
  created_at  TEXT
);

-- ---------------------------------------------------------------------------
-- 第二轮新增：本机审计日志（独立新表，不动上述现有 6 张表）
--   ts         本地时间 'YYYY-MM-DD HH:MM:SS'
--   level      INFO | WARNING | ERROR
--   category   query | import | export | quality | system
--   action     端点名/操作名，如 'query.project'
--   target     对象：项目号 / 文件名 / 人员ID …（可空）
--   result     ok | fail
--   detail     异常堆栈（截断 ≤4000）/ 附加 JSON
-- 隐私红线（AC-07-5）：仅落本机 SQLite，无任何远程上报。
-- CREATE TABLE IF NOT EXISTS 保证幂等；ensure_db() 每次启动 executescript 即自动补建。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           TEXT NOT NULL,                 -- 本地时间 'YYYY-MM-DD HH:MM:SS'
  level        TEXT NOT NULL DEFAULT 'INFO',  -- INFO | WARNING | ERROR
  category     TEXT NOT NULL,                 -- query | import | export | quality | system
  action       TEXT NOT NULL,                 -- 端点名/操作名，如 'query.project'
  target       TEXT,                          -- 对象：项目号 / 文件名 / 人员ID …（可空）
  result       TEXT NOT NULL DEFAULT 'ok',    -- ok | fail
  status_code  INTEGER,                       -- HTTP 状态码
  duration_ms  INTEGER,                       -- 处理耗时
  request_id   TEXT,                          -- 贯穿一次请求（与文件日志一致）
  message      TEXT,                          -- 简述 / 错误信息（截断 ≤500）
  detail       TEXT                           -- 异常堆栈（截断 ≤4000）
);
CREATE INDEX IF NOT EXISTS idx_audit_ts  ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_cat ON audit_log(category);
CREATE INDEX IF NOT EXISTS idx_audit_lvl ON audit_log(level);
