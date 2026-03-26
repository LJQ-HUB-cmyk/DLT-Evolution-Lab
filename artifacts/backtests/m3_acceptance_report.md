# M3 里程碑验收报告

## 验收范围

依据 `开发文档-Composer2.0执行规范.md`、`M3-首版预测引擎-详细技术规范.md`、`M3-Composer2.0-任务拆解与执行清单.md` 对首版预测引擎（M3）进行收口验收。

## 实现摘要

- **引擎模块**：`features.py`、`position_model.py`、`calibration.py`（Platt）、`search.py`（Beam Search + 硬/软约束）、`ticketing.py`（方案1/2）、`reproducibility.py`（snapshot hash、PCG64 RNG）。
- **编排**：`services/predict_pipeline.py` 串联训练/校准/组票；`publish` 幂等、`predict` 每次新 `run_id`。
- **持久化**：`OfficialPrediction` / `PredictionRun` 扩展 `snapshot_hash`、`seed`、`engine_version`、`feature_summary`、`position_summary`、`search_meta`；`scheduler_logs` 记录 `duration_ms` 等审计字段。
- **产物**：`artifacts/backtests/feature_stats_{model_version}.json`、`calibration_{model_version}_{hash8}.json`。
- **前端**：ECharts 热力图、`ModelMetaPanel`、`PositionHeatPanel`、`ContributionPanel`、`PlanTicketPanel`、`ExperimentRunPanel`；Noto Sans SC、卡片/球体动效。

## 测试命令与结果

| 命令 | 结果 |
|------|------|
| `cd apps/api && pip install -e ".[dev]" && python -m pytest -q` | 20 passed |
| `cd apps/web && npm test` | 2 passed（组件 + 交互 mock） |
| `cd apps/web && npm run build` | 成功 |

## 复现性测试说明

- 默认 CI：`tests/test_reproducibility_regression.py` 使用 `M3_REPRO_RUNS` 环境变量，默认 **5** 次连跑比对 `stable_response_hash`（剔除 `run_id`、`created_at`）。
- 规范要求的 **20 次**：执行 `set M3_REPRO_RUNS=20`（Windows）或 `export M3_REPRO_RUNS=20`（Unix）后运行上述 pytest。

## 已知风险与遗留

- **数据门槛**：`MIN_HISTORY_ISSUES = 100`，`data/normalized/issues.json` 不足时 `publish`/`predict`/`analysis` 返回 `422 INSUFFICIENT_HISTORY`。
- **性能**：全量 Beam + sklearn 在弱 CPU 上单次预测可能接近规范预算；测试通过缩小 `beam_width` / `N_hist` 加速（仅 `tests/conftest.py`）。
- **ECharts 包体**：生产构建 JS 较大，后续可按路由做 `import()` 懒加载。
- **M4+**：漂移、Optuna、冠军晋升、开奖自动化不在 M3 范围。

## 结论

M3 核心交付物（引擎、API 契约、持久化字段、前端 M3 面板与自动化测试）已落地并通过当前测试门禁；复现性在固定 `snapshot_hash + model_version + seed` 下对稳定子集哈希一致，完整 20 次验证可通过环境变量启用。
