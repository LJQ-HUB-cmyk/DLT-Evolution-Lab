# M4 Composer2.0 任务拆解与执行清单

## 1. 使用方式
- 本清单是 `M4-漂移检测与优化-详细技术规范.md` 的执行拆解版。
- Composer2.0 必须按任务编号推进；同层可并行，跨层必须满足依赖。
- 每个任务交付必须包含：
  - 代码变更列表
  - 接口/数据结构变更
  - 自测结果
  - 风险与遗留

## 2. 执行泳道
- 泳道 A：数据契约与 API
- 泳道 B：漂移与信用分引擎
- 泳道 C：优化与晋升门禁
- 泳道 D：测试与验收

## 3. 全局完成定义（DoD）
- 漂移报告包含 5 子指标、综合分、触发动作。
- WARN/CRITICAL 下自动动作符合规范且可审计。
- 自动优化任务闭环可执行，失败可追踪重试。
- 候选模型未通过门禁不得晋升。
- M4 回归测试与复现测试全部通过。

## 4. 依赖图（必须遵守）
- B1 完成后 A1 才能稳定对接 schema。
- B2 完成后 C1/C2 才能串起优化闭环。
- C2 完成后 A2 才能暴露完整 API 字段。
- D3 为最终收口任务，必须最后执行。

## 5. 任务清单

## A 泳道（API / 契约）

### A1. 扩展 schema 与存储结构
- 目标：
  - 扩展 `DriftReport`, `ModelVersion`, `OptimizationRun`。
- 实现文件：
  - `apps/api/app/models/schemas.py`
  - `apps/api/app/services/json_store.py`
  - `storage/model_registry.json`
  - `storage/optimization_runs.json`
- 必须结果：
  - 字段齐全并可向后兼容旧数据。
  - JSON 字段顺序稳定。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_schema_contract.py`

### A2. API 扩展与返回统一
- 目标：
  - 统一暴露 M4 扩展字段。
- 实现文件：
  - `apps/api/app/routers/api.py`
  - `apps/api/app/services/predict_pipeline.py`
- 必须结果：
  - `POST /api/predict/{targetIssue}` 返回 `drift_report`、`model_credit`、`optimize_triggered`。
  - `POST /api/optimize` 可入队并返回 run_id。
  - `GET /api/models` 可返回信用分与状态。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_m4_api_contract.py`

## B 泳道（漂移与信用分引擎）

### B1. 漂移指标引擎实现
- 目标：
  - 实现 5 子指标 + 综合漂移分 + 分级判定。
- 实现文件：
  - `apps/api/app/engine/drift.py`
- 必须结果：
  - 支持 baseline/current/history_ref 三输入。
  - 产出完整 `DriftReport`。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_drift_metrics.py`

### B2. 自动降权与信用分模块
- 目标：
  - WARN/CRITICAL 触发降权和信用分更新。
- 实现文件：
  - `apps/api/app/engine/model_credit.py`
  - `apps/api/app/services/predict_pipeline.py`
- 必须结果：
  - 降权参数可追溯、可回放。
  - 信用分更新具确定性。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_model_credit.py`

## C 泳道（优化与晋升）

### C1. Optuna 优化闭环
- 目标：
  - 完成入队、执行、最优参数产出、结果持久化。
- 实现文件：
  - `apps/api/app/engine/optimize.py`
  - `apps/api/app/services/optimization_service.py`
- 必须结果：
  - 支持预算与时限控制。
  - 优化失败状态可追踪并保留失败原因。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_optimize_flow.py`

### C2. 模型晋升门禁
- 目标：
  - 实现候选模型回测与门禁判定。
- 实现文件：
  - `apps/api/app/services/model_registry_service.py`
  - `apps/api/app/services/prediction_service.py`
- 必须结果：
  - 不满足门禁不得晋升 champion。
  - 晋升记录写入 `model_registry.json`。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_model_promotion_gate.py`

## D 泳道（测试与验收）

### D1. 单元与集成补齐
- 目标：
  - 覆盖漂移、信用分、优化目标函数、门禁状态流转。
- 实现文件：
  - `apps/api/tests/test_drift_metrics.py`
  - `apps/api/tests/test_model_credit.py`
  - `apps/api/tests/test_optuna_objective.py`
  - `apps/api/tests/test_optimize_flow.py`
- 必须结果：
  - M4 新增代码覆盖率 `>=88%`。

### D2. 复现与性能回归
- 目标：
  - 校验 M4 引入后仍满足可复现与性能预算。
- 实现文件：
  - `apps/api/tests/test_m4_reproducibility_regression.py`
  - `apps/api/tests/test_m4_performance_budget.py`
- 必须结果：
  - 固定输入 20 次输出一致。
  - 漂移附加开销 `p95 < 350ms`。

### D3. 验收报告收口
- 目标：
  - 输出 M4 验收文档并沉淀上线证据。
- 交付文件：
  - `artifacts/backtests/m4_acceptance_report.md`
- 必须结果：
  - 包含验收点、命令、结果摘要、风险与回滚策略。

## 6. 阻塞处理规则（强制）
- 浮点波动导致漂移边界抖动：
  - 统一四舍五入精度到 `1e-6` 后判级。
- 优化任务超时：
  - 先缩 trial，再缩搜索空间；禁止跳过门禁直接晋升。
- 数据样本不足：
  - 标注 `degraded_test_data=true`，不得产出误导性“通过”结论。

## 7. 每日同步格式（Composer2.0 必填）
- 今日完成任务编号
- 进行中任务编号
- 阻塞与影响
- 明日计划
- 是否偏离规范（是/否，若是必须说明）

## 8. 交付顺序建议（并行最大化）
1. 并行启动：A1 + B1
2. 并行推进：B2 + C1
3. 合流阶段：C2 + A2
4. 测试收口：D1 + D2
5. 最终验收：D3

---

本清单用于 M4 执行，不用于讨论。若执行与规范冲突，先报告差异，再继续实现。
