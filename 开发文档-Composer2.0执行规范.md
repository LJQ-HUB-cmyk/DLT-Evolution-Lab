# dlt-evolution-lab 开发文档（Composer2.0 执行规范）

## 1. 文档目的
- 本文档是给 `Composer2.0` 的强约束开发规范，目标是“按里程碑稳定交付，不返工”。
- 你（执行方）负责实现；我（需求方）负责验收与 bug 修复判定。
- 若出现“实现方便但偏离需求”的冲突，必须以本文档为准，不得自行改口径。

## 2. 技术栈与版本基线
- 前端：`React 18 + Vite 5 + TypeScript 5`
- 后端：`FastAPI + Pydantic v2 + Python 3.11+`
- 持久化：JSON（首版固定），路径见第 4 节
- 调度：`Windows Task Scheduler + 本地 Python 服务`
- 算法组件：
  - 特征与计算：`numpy`, `pandas`
  - 校准与基础模型：`scikit-learn`
  - 超参优化：`optuna`
  - 图表：前端 `ECharts` 或 `Recharts`（二选一，统一全站）
- 测试：`pytest`（后端）、`vitest` + `@testing-library/react`（前端）

## 3. 统一工程规则（必须遵守）
- API 不允许随意增删，核心接口固定：
  - `GET /api/issues`
  - `POST /api/sync`
  - `GET /api/analysis/{targetIssue}`
  - `POST /api/publish/{targetIssue}`
  - `POST /api/predict/{targetIssue}`
  - `POST /api/anchor/recompute`
  - `POST /api/postmortem/{issue}`
  - `POST /api/optimize`
  - `GET /api/models`
  - `GET /api/runs`
- 任意写入动作必须记录到 `scheduler_logs.json`（手动触发也算）。
- 同一历史快照 + 同一模型版本 + 同一 seed，结果必须完全一致（可复现是硬要求）。
- 已发布正式预测不可修改（append-only + freeze）。
- 数据源只允许官方来源，抓取异常必须降级，禁止污染历史数据。

## 4. 目录与数据契约

### 4.1 目录固定
- `apps/web`
- `apps/api`
- `jobs`
- `data/raw`
- `data/normalized`
- `storage`
- `artifacts/backtests`

### 4.2 核心 JSON（必须存在）
- `storage/issues.json`
- `storage/predictions.json`
- `storage/anchor_ticket.json`
- `storage/model_registry.json`
- `storage/optimization_runs.json`
- `storage/postmortems.json`
- `storage/scheduler_logs.json`

### 4.3 对外类型（必须保留）
- `DrawIssue`
- `Ticket`
- `PredictionRun`
- `OfficialPrediction`
- `DriftReport`
- `ModelVersion`
- `BacktestReport`
- `PostmortemReport`
- `AnchorTicketState`

## 5. 里程碑开发规范

## M1 基础工程（已完成，禁止破坏）

### 开发目标
- 前后端可启动、核心 API 有稳定空壳返回、存储层可读写。

### 必须结果
- 能启动 `FastAPI` 与 `Vite`
- `GET /api/issues`、`GET /api/models` 返回结构完整 JSON
- 7 个核心 JSON 已初始化

### 注意事项
- M1 是后续里程碑的稳定地基，不允许为了“快速实现”删除现有接口字段。

## M2 数据同步闭环（已完成，继续增强但不改契约）

### 开发目标
- 官方页面抓取、原始快照、标准化入库、规则版本管理、降级告警。

### 必须结果
- `POST /api/sync` 可返回 `ok/degraded/warnings/snapshots`
- 原始快照写入 `data/raw`
- 标准化数据写入 `data/normalized/issues.json`
- 规则版本写入 `data/normalized/rule_versions.json`

### 注意事项
- 当前环境可能无法直连官方站点，必须支持 degraded mode。
- degraded 模式下不得覆盖已有有效历史数据。

## M3 首版预测引擎（重点）

### 开发目标
- 建立可解释预测引擎：透明特征层、位置评分、基础校准、组合搜索、方案1/方案2出票、正式发布冻结、实验 run 记录。

### 开发计划（执行顺序）
1. 建立引擎模块目录：
   - `apps/api/app/engine/features.py`
   - `apps/api/app/engine/position_model.py`
   - `apps/api/app/engine/calibration.py`
   - `apps/api/app/engine/search.py`
   - `apps/api/app/engine/ticketing.py`
   - `apps/api/app/engine/reproducibility.py`
2. 实现透明特征层（前区 1-35、后区 1-12）。
3. 实现位置评分模型（前区 1-5 位、后区 1-2 位）。
4. 实现基础校准（先用 Platt scaling，后续可扩展 isotonic）。
5. 实现组合搜索（beam search + 多样性约束）。
6. 实现方案1/方案2出票策略。
7. 对接 `POST /api/publish/{targetIssue}` 与 `POST /api/predict/{targetIssue}`。
8. 落地可复现控制（seed、snapshot_hash、model_version 三元绑定）。

### 透明特征层（必须实现）
- 每个号码必须输出以下特征（缺一不可）：
  - `freq_10`, `freq_30`, `freq_50`, `freq_100`
  - `miss_current`（当前遗漏）
  - `ewma_hotness`（指数滑动热度）
  - `adjacent_last`（是否为上期邻号）
  - `repeat_last`（是否为上期重号）
  - `tail_bucket`（尾号分桶 one-hot）
  - `zone_bucket`（区间分桶 one-hot）
  - `sum_contrib_proxy`（对和值目标区间的贡献评分）
  - `span_contrib_proxy`（对跨度目标区间的贡献评分）
  - `hot_cold_tag`（冷热标签）
  - `last_issue_interference`（上期干扰项）
- 输出要求：
  - 每个号码有 `feature_vector`
  - 每个特征可追溯（可在分析页展示贡献）

### 位置评分（必须实现）
- 任务定义：
  - 前区排序后建模 `pos1~pos5`
  - 后区排序后建模 `pos1~pos2`
- 评分公式（首版）：
  - `raw_score = sum(weight_i * feature_i)`
  - `position_prob = sigmoid(raw_score)`（或 softmax 归一）
- 输出：
  - 每个位置每个号码的 `raw_score`、`calibrated_prob`
  - TopN 号码及主要贡献因子

### 基础校准（必须实现）
- 先实现 `Platt scaling`：
  - 输入：历史回测中的 raw score 与是否命中标签
  - 输出：校准后的概率
- 校准指标必须落盘：
  - `brier_score`
  - `ece`（expected calibration error）
- 校准参数写入 `artifacts/backtests/calibration_*.json`

### 组合搜索（必须实现）
- 算法：`Beam Search`
- 搜索对象：从位置概率池组合候选票
- 硬约束：
  - 前区 5 个不重复，范围 1-35
  - 后区 2 个不重复，范围 1-12
  - 禁止非法结构（全奇/全偶、全大/全小、极端连号）
- 软约束（可调权重）：
  - 奇偶比、大小比、三区均衡、和值区间、跨度区间、冷热搭配
- 排序分：
  - `ticket_score = position_score + structure_score + diversity_bonus`

### 方案出票（必须实现）
- 方案1（5组）：
  - 1 组永久跟买号（单独目标函数，强调跨窗口稳定性）
  - 4 组结构化模型号
- 方案2（5组）：
  - 轻结构美化，约束弱于方案1
  - 同模型版本同 seed 必须复现

### 正式发布冻结（必须实现）
- `POST /api/publish/{targetIssue}`：
  - 若该期已发布，返回已发布结果，不重新计算
  - 发布写入 `predictions.json.official[]`
  - 字段必须包含：
    - `target_issue`
    - `run_id`
    - `model_version`
    - `snapshot_hash`
    - `seed`
    - `plan1`, `plan2`
    - `published_at`

### 实验 run 记录（必须实现）
- `POST /api/predict/{targetIssue}`：
  - 每次请求都生成新 `run_id`
  - 写入 `predictions.json.experimental[]`
  - 必须记录：
    - `run_id`, `target_issue`, `model_version`
    - `snapshot_hash`, `seed`
    - `plan1`, `plan2`
    - `feature_summary`, `position_summary`
    - `created_at`

### M3 验收标准（必须全部通过）
- 20 次连续实验请求全部生成独立 run
- 所有票合法
- 同快照 + 同版本 + 同 seed 结果 bit-level 一致
- `publish` 与 `predict` 接口稳定返回且字段齐全
- 前端可展示位置 TopN、方案票面、run 列表

## M4 漂移检测与优化

### 开发目标
- 实现漂移分、自动降权、候选模型优化与回测门禁。

### 必须实现
- `DriftReport` 五项组成：
  - 位置差异
  - 号码集合差异
  - 结构差异
  - 综合分差异
  - 方案重叠差异
- 漂移触发策略：
  - 与正式结果比
  - 与近 N 次实验均值比
- 超阈值动作：
  - 降低对应特征权重或模型信用分
  - 标记 `unstable`
  - 自动入队 `POST /api/optimize`
- `Optuna` 搜索空间必须包含：
  - 特征权重
  - 窗口长度
  - 冷热阈值
  - 结构惩罚强度
  - beam width
  - 多样性系数
  - 方案2 seed 策略

### 验收标准
- 构造高漂移实验可触发降权与优化入队
- 已发布正式结果不可被覆盖
- 候选模型需通过回测门禁后才能晋升

## M5 开奖复盘与自动任务

### 开发目标
- 开奖回填、奖级计算、复盘报告、模型晋升与任务自动化。

### 必须实现
- 周期任务：
  - 每日 09:00 同步
  - 周一/三/六 20:30 发布检查
  - 周一/三/六 21:45 开奖轮询
- 开奖后流水线：
  - 回填真实号码
  - 计算命中结构与奖级
  - 生成 `postmortems.json`
  - 触发优化并评估晋升
- 所有任务日志必须写入：
  - 输入快照 hash
  - 模型版本
  - 耗时
  - 结果摘要
  - 失败原因

### 验收标准
- 模拟开奖后可自动产出复盘与优化记录
- 任务失败可追踪，不会造成数据污染

## M6 前端体验与测试闭环

### 开发目标
- 完成可用可审计的业务界面与测试体系。

### 必须实现
- 页面结构：
  - 左 1/3 历史栏（滚动）
  - 右上：数据状态、模型说明、位置概率、方案票
  - 右下：实验 run、漂移记录、优化记录、复盘图表
- 视觉要求：
  - 米白纸感 + 深蓝面板 + 红蓝球 + 金属边
  - 桌面双栏，移动端上下折叠
- 测试覆盖：
  - API 契约测试
  - 引擎回归测试
  - 可复现性测试
  - 前端布局与关键组件渲染测试

### 验收标准
- 桌面/移动均稳定显示
- 图表、日志、复盘详情与模型演进可用
- 回归测试通过，无关键回退

## 6. 执行注意事项（避免返工）
- 禁止先写“简化版接口”再重构，直接按最终契约开发。
- 禁止把核心逻辑写在路由里，必须进入 `engine` 与 `services`。
- 每完成一个里程碑，必须提交：
  - 变更清单
  - 新增/变更数据结构
  - 验收证据（命令输出 + 示例 JSON）
- 任一里程碑验收未通过，不得进入下里程碑开发。

## 7. 交付清单模板（每个里程碑都要给）
- `实现内容`：本次新增了什么
- `接口变更`：请求/响应字段变化
- `数据变更`：新增 JSON 字段及兼容策略
- `验证结果`：测试命令和通过情况
- `风险与遗留`：还未解决的问题与下一步计划

---

本规范用于 Composer2.0 执行。实现过程如与本文档冲突，默认以本文档为准并先回报差异点，不得自行偏离。

## 附加强制说明（M3）
- M3 开发必须同时遵循：
  - 本文档 `M3` 章节
  - [M3-首版预测引擎-详细技术规范.md](./M3-首版预测引擎-详细技术规范.md)
  - [M3-Composer2.0-任务拆解与执行清单.md](./M3-Composer2.0-任务拆解与执行清单.md)
- 若两者出现细节冲突，以 `M3-首版预测引擎-详细技术规范.md` 为准。

## 附加强制说明（M4）
- M4 开发必须同时遵循：
  - 本文档 `M4` 章节
  - [M4-漂移检测与优化-详细技术规范.md](./M4-漂移检测与优化-详细技术规范.md)
  - [M4-Composer2.0-任务拆解与执行清单.md](./M4-Composer2.0-任务拆解与执行清单.md)
  - [m4_acceptance_report.md](./artifacts/backtests/m4_acceptance_report.md)
- 若出现细节冲突，以 `M4-漂移检测与优化-详细技术规范.md` 为准。

## 附加强制说明（M5）
- M5 开发必须同时遵循：
  - 本文档 `M5` 章节
  - [M5-开奖复盘与自动任务-详细技术规范.md](./M5-开奖复盘与自动任务-详细技术规范.md)
  - [M5-Composer2.0-任务拆解与执行清单.md](./M5-Composer2.0-任务拆解与执行清单.md)
  - [m5_acceptance_report.md](./artifacts/backtests/m5_acceptance_report.md)
- 若出现细节冲突，以 `M5-开奖复盘与自动任务-详细技术规范.md` 为准。

## 附加强制说明（M6）
- M6 开发必须同时遵循：
  - 本文档 `M6` 章节
  - [M6-前端体验与测试闭环-详细技术规范.md](./M6-前端体验与测试闭环-详细技术规范.md)
  - [M6-Composer2.0-任务拆解与执行清单.md](./M6-Composer2.0-任务拆解与执行清单.md)
  - [m6_acceptance_report.md](./artifacts/backtests/m6_acceptance_report.md)
- 若出现细节冲突，以 `M6-前端体验与测试闭环-详细技术规范.md` 为准。
