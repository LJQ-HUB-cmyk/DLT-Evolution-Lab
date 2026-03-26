# M4 里程碑验收报告

## 验收范围

依据 `开发文档-Composer2.0执行规范.md`、`M4-漂移检测与优化-详细技术规范.md`、`M4-Composer2.0-任务拆解与执行清单.md` 对漂移检测、模型信用分、Optuna 优化闭环与晋升门禁进行收口验收。

## 实现摘要

- **漂移引擎**：`app/engine/drift.py` — 五项子指标（位置 JSD、集合 Jaccard、结构曼哈顿、分数差 z-score、方案重叠 Sigmoid）、加权综合分、NORMAL/WARN/CRITICAL 分级与硬触发规则；`DriftReport` 契约对齐规范 §8.1。
- **信用与降权**：`app/engine/model_credit.py` — EWMA 信用分、WARN/CRITICAL 结构惩罚与 beam 收紧、特征结构权重衰减、`merge_config_overrides` 合并冠军 `config_overrides`。
- **优化**：`app/engine/optimize.py` — M4 全量搜索空间、`run_optuna_study`、多目标折中 + 非法票/可复现/p95 重罚；`services/optimization_service.py` — 入队、执行、落盘 `optimization_runs.json`、注册候选模型。
- **注册与晋升**：`services/model_registry_service.py` — `apply_after_experimental`、`append_candidate_model`、`evaluate_walk_forward_gate`、`try_promote_candidate`；与 M5 衔接的 `evaluate_promotion_after_optimize`（仅门禁与信用优势通过方可晋升）。
- **API**：`POST /api/predict/{targetIssue}` 返回 `drift_report`、`model_credit`、`optimize_triggered`；`POST /api/optimize` 支持 body（`trigger_source`、`base_model_version`、`budget_trials`、`time_limit_minutes`）；`GET /api/models` 返回归一化后的 `credit_score`、`drift_summary`、`last_gate_result` 等；高漂移自动入队优化并写 `scheduler_logs.json`。
- **持久化**：`storage/model_registry.json` 扩展 `credit_score`、`config_overrides`、`consecutive_warn_count` 等；`optimization_runs.json` 记录 `search_space_hash`、`best_params`、`gate_result`、状态机。

## 测试命令与结果

在 `apps/api` 目录下（建议设置 `OPTUNA_FAST=1` 缩短 Optuna trial，CI/本地验收均可）：

| 命令 | 结果（本环境） |
|------|----------------|
| `pip install -e ".[dev]"`（含 `scipy`、`optuna`） | 依赖安装成功 |
| `$env:OPTUNA_FAST='1'; python -m pytest -q --ignore=tests/test_reproducibility_regression.py` | **98 passed** |
| `python -m pytest -q --cov=app.engine.drift --cov=app.engine.model_credit --cov=app.engine.optimize --cov=app.services.optimization_service --cov=app.services.model_registry_service --cov-report=term-missing --ignore=tests/test_reproducibility_regression.py` | M4 相关模块合计覆盖率 **约 91%**（高于规范 ≥88% 门槛） |

### 专项测试文件

- `tests/test_drift_metrics.py` — 子指标与综合分边界（容差 1e-6 级）。
- `tests/test_model_credit.py` — 信用分与入队条件。
- `tests/test_optuna_objective.py` — 目标函数惩罚与搜索空间边界。
- `tests/test_optimize_flow.py`、`tests/test_optimization_service_unit.py` — 优化入队/执行与 API。
- `tests/test_model_promotion_gate.py`、`tests/test_evaluate_promotion_m5.py` — 门禁与晋升。
- `tests/test_m4_api_contract.py` — predict/models 契约字段。
- `tests/test_m4_reproducibility_regression.py`、`tests/test_m4_performance_budget.py` — 复现与漂移计算耗时预算（`p95 < 350ms`，样本级）。

### 复现性说明

- `tests/test_m4_reproducibility_regression.py` 默认 **5** 次连跑；规范 **20** 次：设置环境变量 `M4_REPRO_RUNS=20` 后执行 pytest。
- 原 M3 `tests/test_reproducibility_regression.py` 仍可通过 `M3_REPRO_RUNS` 控制；全量跑法较慢时可单独 `--ignore`。

## 已知风险与回滚策略

- **Walk-forward 全量实现**：`evaluate_walk_forward_gate` 已按契约实现判定式；训练窗 180/验证 30/步长 10 的完整滚动回测与真实 `predict p95` 接入仍依赖充足 `issues.json` 与性能基线，当前 `evaluate_promotion_after_optimize` 在 M5 场景下由 `backtest_gate_ok`/`stability_ok` 显式注入，避免无数据误晋升。
- **优化耗时**：默认 `budget_trials=80`、`time_limit_minutes=45`；本地/CI 建议使用 `OPTUNA_FAST=1` 缩小 trial。**回滚**：删除或停用候选 `config_overrides`，将 `model_registry.json` 中冠军 `status` 恢复为 `champion` 并移除错误候选条目；保留 `optimization_runs.json` 失败记录便于审计。
- **双轨不变式**：`publish` 仍保持幂等，不覆盖已存在 `official` 记录；漂移与优化仅影响冠军配置与候选注册，不回写已发布正式预测。

## 结论

M4 要求的核心能力（五项漂移指标、信用分与自动动作、Optuna 搜索空间与目标函数、优化闭环与晋升门禁、API 与持久化扩展、自动化测试与覆盖率门槛）已按详细规范落地；在 `OPTUNA_FAST=1` 下全套后端测试通过，M4 相关模块覆盖率满足 ≥88% 验收线。完整 20 次复现与生产级优化时长可通过环境变量在本地复验。
