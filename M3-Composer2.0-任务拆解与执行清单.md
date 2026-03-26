# M3 Composer2.0 任务拆解与执行清单

## 1. 使用方式
- 本清单是 `M3-首版预测引擎-详细技术规范.md` 的执行拆解版。
- Composer2.0 必须按任务编号顺序执行；同层可并行，跨层必须满足依赖。
- 每个任务完成后提交 4 项：
  - 代码变更列表
  - 接口或数据结构变更
  - 自测结果
  - 风险与遗留

## 2. 执行角色与泳道
- 泳道 A：后端 API 与持久化
- 泳道 B：算法引擎
- 泳道 C：前端页面与交互质感
- 泳道 D：测试与验收自动化

## 3. 全局完成定义（DoD）
- 所有新增字段在类型层定义，禁止“裸 dict 拼接”漂移。
- `publish/predict/analysis` 三接口字段完整且稳定。
- 同 `snapshot_hash + model_version + seed` 输出完全一致。
- 单测、集成测试、前端构建全部通过。
- 文档更新到 `README.md` 与 M3 专项文档。

## 4. 依赖图（必须遵守）
- B1-B4 完成后，A2/A3 才能稳定对接。
- A3 完成后，C2/C3 才能接真实数据渲染。
- A2/B5 完成后，D2/D3 才能做复现与接口回归。
- D4 是 M3 里程碑收口任务，必须最后执行。

## 5. 任务清单

## A 泳道（后端 API / 持久化）

### A1. 扩展数据模型与存储契约
- 目标：
  - 为 M3 增加 `snapshot_hash`, `engine_version`, `feature_summary`, `position_summary`, `search_meta`。
- 实现文件：
  - `apps/api/app/models/schemas.py`
  - `apps/api/app/services/json_store.py`
- 必须结果：
  - `OfficialPrediction` 和 `PredictionRun` 字段齐全。
  - JSON 序列化后字段顺序稳定（便于 hash 与对比）。
- 自测命令：
  - `python -m pytest -q tests/test_schema_contract.py`

### A2. 重构 publish/predict 路由到 pipeline
- 目标：
  - 路由层不含算法逻辑，仅负责编排与错误码。
- 实现文件：
  - `apps/api/app/routers/api.py`
  - `apps/api/app/services/predict_pipeline.py`
- 必须结果：
  - `POST /api/publish/{targetIssue}` 幂等。
  - `POST /api/predict/{targetIssue}` 每次新 run_id。
  - 错误码统一：`INSUFFICIENT_HISTORY`, `MODEL_NOT_FOUND`, `PIPELINE_FAILED`。
- 自测命令：
  - `python -m pytest -q tests/test_publish_predict_api.py`

### A3. analysis 接口增强
- 目标：
  - 返回位置 TopN、贡献因子、结构分解。
- 实现文件：
  - `apps/api/app/routers/api.py`
  - `apps/api/app/services/predict_pipeline.py`
- 必须结果：
  - `GET /api/analysis/{targetIssue}` 返回可直接前端渲染结构。
- 自测命令：
  - `python -m pytest -q tests/test_analysis_api.py`

### A4. M3 日志与审计补齐
- 目标：
  - publish/predict 每次写入 scheduler log，记录耗时与关键输入。
- 实现文件：
  - `apps/api/app/services/json_store.py`
  - `apps/api/app/services/predict_pipeline.py`
- 必须结果：
  - 日志含 `action`, `result`, `target_issue`, `snapshot_hash`, `model_version`, `duration_ms`。

## B 泳道（算法引擎）

### B1. 可复现底座
- 目标：
  - 实现 snapshot hash、确定性 seed 混合、统一 RNG。
- 实现文件：
  - `apps/api/app/engine/reproducibility.py`
- 必须结果：
  - `build_snapshot_hash(history, config, rule_version)`。
  - `build_rng(snapshot_hash, model_version, seed)`。
  - 任何采样只能用该 RNG。
- 自测命令：
  - `python -m pytest -q tests/test_reproducibility.py`

### B2. 特征工程实现
- 目标：
  - 完整实现 M3 规范中的全量特征与标准化。
- 实现文件：
  - `apps/api/app/engine/features.py`
- 必须结果：
  - 前区 35 个号、后区 12 个号均生成完整 `feature_vector`。
  - 产出 `feature_summary`（全局特征统计）供 run 存储。
- 自测命令：
  - `python -m pytest -q tests/test_features.py`

### B3. 位置评分模型实现
- 目标：
  - 前 5 后 2 位置模型评分，输出 raw 与 calibrated 前的概率。
- 实现文件：
  - `apps/api/app/engine/position_model.py`
- 必须结果：
  - `score_positions(features, history)` 返回结构化位置分布。
  - 返回 TopN 与贡献因子前 3。
- 自测命令：
  - `python -m pytest -q tests/test_position_model.py`

### B4. 校准模块实现
- 目标：
  - Platt scaling 校准与指标落盘。
- 实现文件：
  - `apps/api/app/engine/calibration.py`
  - `artifacts/backtests/*.json`
- 必须结果：
  - 位置概率都在 `[0, 1]`。
  - 输出 `brier_score` 和 `ece`。
- 自测命令：
  - `python -m pytest -q tests/test_calibration.py`

### B5. 组合搜索与出票实现
- 目标：
  - Beam Search + 约束 + 多样性 + 方案1/方案2组票。
- 实现文件：
  - `apps/api/app/engine/search.py`
  - `apps/api/app/engine/ticketing.py`
- 必须结果：
  - 永不输出非法票。
  - 方案1=5组（含 anchor 1 组），方案2=5组。
  - 返回 `search_meta`（beam width、候选数、剪枝数）。
- 自测命令：
  - `python -m pytest -q tests/test_search_ticketing.py`

### B6. 引擎流程编排
- 目标：
  - 串起 `B1-B5` 形成可调用 pipeline。
- 实现文件：
  - `apps/api/app/services/predict_pipeline.py`
- 必须结果：
  - `run_prediction(target_issue, mode, seed)` 统一输出协议。
  - mode=`official` 时可冻结，mode=`experimental` 时每次新 run。

## C 泳道（前端页面与质感）

### C1. 视觉系统升级
- 目标：
  - 建立 M3 主题变量、字重层级、卡片和球体样式。
- 实现文件：
  - `apps/web/src/styles.css`
- 必须结果：
  - 米白纸感背景、深蓝面板、金属边、红蓝球高光阴影。
  - 页面视觉不扁平，保留留白与层次。
- 验收点：
  - 桌面和移动端均不出现拥挤或色块堆叠。

### C2. 分析面板组件化
- 目标：
  - 新增 M3 必需组件并对接 analysis API。
- 实现文件：
  - `apps/web/src/components/PositionHeatPanel.tsx`
  - `apps/web/src/components/ContributionPanel.tsx`
  - `apps/web/src/components/ModelMetaPanel.tsx`
  - `apps/web/src/lib/api.ts`
- 必须结果：
  - 展示每位置 TopN、概率、贡献因子。
  - 展示 model_version、snapshot_hash、seed。

### C3. 出票与实验日志面板
- 目标：
  - 展示方案1/2票面、实验 run 列表和关键元信息。
- 实现文件：
  - `apps/web/src/components/PlanTicketPanel.tsx`
  - `apps/web/src/components/ExperimentRunPanel.tsx`
  - `apps/web/src/App.tsx`
- 必须结果：
  - 点击实验后 run 即时新增。
  - 票面渲染合法、球号格式统一（两位数）。

### C4. 动效与状态体验
- 目标：
  - 卡片入场、球号刷新、图表切换都平滑。
- 实现文件：
  - `apps/web/src/styles.css`
  - 相关组件文件
- 必须结果：
  - 无跳闪、无明显布局抖动。
  - 加载态、空态、错误态均可见。

## D 泳道（测试与验收）

### D1. 后端单测补齐
- 目标：
  - 覆盖特征、位置、校准、搜索、路由契约。
- 实现文件：
  - `apps/api/tests/*.py`
- 必须结果：
  - 覆盖率目标：M3 新增代码 `>=85%`。

### D2. 复现性回归测试
- 目标：
  - 固定输入连跑 20 次输出一致。
- 实现文件：
  - `apps/api/tests/test_reproducibility_regression.py`
- 必须结果：
  - 每次响应 JSON 哈希一致。

### D3. 前端测试补齐
- 目标：
  - 布局、组件渲染、关键交互可自动回归。
- 实现文件：
  - `apps/web/src/**/*.test.tsx`
- 必须结果：
  - 桌面/移动布局断点测试通过。
  - “实验计算”交互测试通过。

### D4. 里程碑收口验收
- 目标：
  - 出具 M3 验收报告。
- 交付文件：
  - `artifacts/backtests/m3_acceptance_report.md`
- 必须结果：
  - 列出所有验收点、测试命令、结果摘要、已知风险。

## 6. 阻塞处理规则（强制）
- 数据不足阻塞：
  - 使用最近可用快照做最小样本回归，标注 `degraded_test_data=true`。
- 算法输出不稳定阻塞：
  - 优先排查 RNG 与排序稳定性，禁止先改阈值掩盖问题。
- 前端渲染性能阻塞：
  - 先减重图表数据，再做渲染节流，不允许删除核心面板。

## 7. 每日同步格式（Composer2.0 必填）
- 今日完成任务编号
- 进行中任务编号
- 阻塞与影响
- 明日计划
- 是否偏离规范（是/否，若是必须说明）

## 8. 交付顺序建议（并行最大化）
1. 并行启动：A1 + B1 + C1
2. 并行推进：B2/B3/B4 与 A2
3. 合流阶段：B5 + B6 + A3
4. 前端对接：C2 + C3 + C4
5. 测试收口：D1 + D2 + D3
6. 最终验收：D4

---

本清单用于执行，不用于讨论。若执行与规范冲突，先报告差异，再继续实现。

