# 附录 A：源数据实测报告

> 编写：主理人齐活林（交付总监）
> 数据来源：`C:\Users\Administrator\Desktop\ECAHelper\OriginSource\`（45 个文件全量解析，非抽样）
> 目的：为 PRD 与系统设计提供事实基线。本报告所有数字均来自脚本实测。

---

## A.1 文件盘点

| 类别 | 数量 | 说明 |
|------|------|------|
| 有效月度工时表 | 43 | 覆盖 2023.02 – 2026.09，中间无缺月 |
| 项目主数据 | 1 | `在管项目2026.08.xlsx`（本期未采用） |
| Excel 临时锁文件 | 1 | `~$Timesheet of 2023.4 including SC.xlsx`（须忽略） |

数据规模：**33,015 条明细行**，累积工时 **1,572,771.8 h**。

---

## A.2 陷阱一：数据表不能用「第 3 张 Sheet」定位

| 现象 | 实测证据 |
|------|----------|
| Sheet 数量不一致 | `2024.12` **只有 1 张** Sheet（即数据表）；`2024.10` 只有 2 张 |
| 数据表名不固定 | 在 `EA`、`SX`、`Timesheet of 2023.06` 之间变化 |
| 表头起始行漂移 | 第 1 行（2026.09）、第 2 行（2024.04、2024.07+）、第 3 行（大多 v1 文件） |

**结论**：定位策略必须是「扫描每张 Sheet 的前若干行，找到同时含 `Resourcename` 与 `Actuals Total in h` 的行作为表头」。前两张 Sheet 均为数据透视表，全部忽略。

---

## A.3 陷阱二：两代字段结构

### v1 旧版（2023.02 – 2024.06，17 个文件，9 列）
```
Resourcename | Resource ID | Organization | Project ID | Project |
Task | WBS Nr | Cost Center | Actuals Total in h
```
- 另含 1 个游离日期列（如 `2023-10-19`），无分析价值
- `2023.10` 额外多一列 `real CC`
- 姓名格式：`姓, 名`（如 `Li, Bo`）

### v2 新版（2024.07 – 2026.09，28 个文件，16–17 列）
```
Resourcename | Resource ID | Organization | Cost Center | WH Cost Center |
Project ID | Project | Task | WBS Nr | To WBS No. | To Cost Center |
To Internal Order | To Reference Proj.No. | Reference Proj.Name |
Actuals Total in h | Transaction Group | Site Type
```
- `Site Type` 并非所有文件都有
- 姓名格式：`名 姓`（如 `Li Bo`）

---

## A.4 陷阱三：四个会算错数的数据质量问题

### (1) 人名不能当主键
- 270 个 Resource ID 中，**192 个存在多种姓名写法**
- 变体示例：

| Resource ID | 姓名写法 |
|-------------|----------|
| `YIXL` | `Yin Xiaolin` / `Yin, Xiaolin` / `Yin,Xiaolin` / `Yin.Xiaolin` / `Yin，Xiaolin`（全角逗号） |
| `ZHCH` | `Zhang Chuan` / `Zhang, Chuan` / `Zhang,Chuan` |
| `WAXI` | `Wang, Xia` / `Wang，Xia` |
| `CAOZ` | `Cao, Zheng` / `Cao, zheng` |

- 两代人名字面重合的**只有 24 个** → 跨代检索必须靠 ID

### (2) Resource ID 本身也不干净
- 存在**空值**
- 大小写不一致：`waxi` / `WAXI`、`Caoz` / `CAOZ`
- 疑似同一人被拆成两个 ID：`WATA` / `WATA02`、`LIXI` / `LIXN`
- 17 个姓名对应多个 ID

### (3) Project ID 有 5 种形态
| 形态 | 示例 |
|------|------|
| 带空格前缀码 | `O 1900.008` |
| 带尾空格 | `E20067-000 ` |
| 纯数字 | `70463` |
| 浮点 | `0.0001` |
| WBS 形式 | `O 1341.176.01.01.0028` |

非归一化处理会导致查不全。同时 Excel 会把 `70463` 读成 `int`、把 `0.0001` 读成 `float`，必须统一转字符串后去空格。

### (4) 无项目号的行占 20%
共 **6,575 行**没有 Project ID：

| Task | 行数 |
|------|------|
| Leave | 3,293 |
| Procurement services | 2,523 |
| （完全空白） | 562 |
| SCF (Annual Leave) | 79 |
| SCF (Sick Leave) | 35 |
| 其他零散 | 83 |

### (5) 其他
- **重复行**：29 个文件存在完全重复的行，绝大多数仅 1 组、重复 2 次
- **异常值**：`2023.2` 文件有 **14 行**「Actuals Total in h」被 Excel 存成日期值（如 `1900-01-16`）
- **无负工时**：全量 0 条，不存在冲销净额问题 ✅

---

## A.5 陷阱四：时间依据只能用文件名

- 文件内部 `From ... to ...` 日期**不可信**：`Timesheet of 2023.6 including SC.xlsx` 内部写的是 `2022-06-01 – 2022-06-30`（年份错误）
- 多份文件的内部日期年份都错位（2024.02 / 2024.03 / 2024.05 / 2024.06 内部日期均为 2023 年）
- 表头右侧还挂着一个游离日期（如 `2023-10-19`），与所属月份无稳定关系

**结论**：只认文件名。解析 `YYYY.M` 或 `YYYY.MM`，注意 `2025.01including SC.xlsx` 这种月份与 `including` 之间**缺空格**的写法。

**粒度上限**：数据本身只有月度汇总，**没有每日明细** —— 这决定了系统最小时间粒度为「月」。

---

## A.6 组织维度现状

`Organization` 字段值分布（Top 8）：

| 值 | 行数 |
|----|------|
| SCF | 2,931 |
| EAR | 2,852 |
| IMM | 2,748 |
| （空） | 2,254 |
| EAI | 1,759 |
| EAP | 1,345 |
| EAM | 1,162 |
| EAL | 1,130 |

此外还有大量 `SX**` 形式的驻点/项目组编码：`SXSE32`、`SXSE31`、`SXPB32`、`SXSD3`、`SXLA32`、`SXMA61` 等（共 50+ 种）。

`Cost Center` 为数字型代码，常见值：`587`、`529`、`363`、`411`、`517`、`527`、`511`。

> ⚠️ **注意**：`Organization` 有 2,254 行为空，且 v1/v2 两代的 Organization 取值语义可能不同（v1 多为 `SCF`/`EAR`/`EAL`/`EAM`，v2 多为 `SX**` 编码）。组织维度统计需在 UI 上向用户明示口径，避免误读。

---

## A.7 附：未采用的文件

`在管项目2026.08.xlsx` 是一份**项目主数据**，字段为：
```
Contract No. | Company | Project Name | Customer | Country |
Contract Value(with VAT) | Order Type | Sales Person | Order ID
```
共 32 条在管项目。与工时表的 `Project ID` 格式一致（如 `O 1383.232`、`E50004-000`），**技术上可关联**，可作为二期「按客户/国家/合同额统计」的数据源。本期经用户确认**不引入**。

---

## A.8 复现方式

本报告由以下脚本生成，可持续复用于后续新增月份的数据体检：

| 脚本 | 用途 |
|------|------|
| `tools/probe_env.py` | 环境与依赖探测 |
| `tools/probe_sheets.py` | Sheet 结构与表头定位探测 |
| `tools/scan_all.py` | 全量文件表头/行数/字段扫描 |
| `tools/probe_deep.py` | 人员变体、重复行、工时合计校验 |
| `tools/probe_deep2.py` | 空项目号分类、负工时、异常值定位 |
