# M5 验收报告

## 1. 基本信息
- 验收日期：2026-03-26
- 代码路径：`d:\cursor_git\dlt-evolution-lab`
- 调度环境：Windows 任务计划 + `jobs/scheduler_service.py`（本地 Python）

## 2. 验收范围
- 定时任务与状态机（`scheduler_audit_service` + `transition_task`）
- 幂等与重试（`scheduler_logs.json` → `idempotency`）
- 开奖回填（`ingest_official_draw`）与奖级/复盘（`postmortem_service`）
- 复盘后自动优化触发（`optimization_service.should_trigger_optimize`）
- 晋升评估（`model_registry_service.evaluate_promotion_after_optimize`）
- API：`POST /api/sync`（`scheduler_context`）、`POST /api/postmortem/{issue}`、`GET /api/runs`（`postmortem_ref`）
- 审计日志字段契约测试

## 3. 验收项与结果
| 项 | 结果 |
|----|------|
| 状态机 queued/running/succeeded/failed/skipped | 通过 |
| 幂等键成功后 skip | 通过 |
| 奖级映射 1–9 + no_prize | 通过 |
| 回填冲突 data_conflict 不覆盖 | 通过 |
| 复盘落盘 + 预测 `prize_summary` / `postmortem_status` | 通过 |
| 复盘触发优化条件（滚动均值/连续无奖/漂移/信用） | 通过 |
| 晋升仅门禁通过 + 信用优势 | 通过 |
| 任务日志必填字段（含 `task_id`…`created_at`） | 通过 |

## 4. 测试命令与摘要
```text
python -m pytest -q apps/api/tests/test_scheduler_state_machine.py
python -m pytest -q apps/api/tests/test_task_idempotency.py
python -m pytest -q apps/api/tests/test_prize_rules.py
python -m pytest -q apps/api/tests/test_draw_ingestion.py
python -m pytest -q apps/api/tests/test_postmortem_service.py
python -m pytest -q apps/api/tests/test_postmortem_trigger_optimize.py
python -m pytest -q apps/api/tests/test_auto_promotion_eval.py
python -m pytest -q apps/api/tests/test_m5_api_contract.py
python -m pytest -q apps/api/tests/test_scheduler_logs_contract.py
python -m pytest -q apps/api/tests/test_draw_to_postmortem_pipeline.py
python -m pytest -q apps/api
```
- 全量：`55 passed`（约 3m40s，含 Optuna 相关用例）

## 5. 风险与遗留
- `jobs/register_tasks.ps1` 为模板：周一/三/六 20:30 / 21:45 需在「任务计划程序」中按实际开奖期号与路径微调。
- `ingest_official_draw` 的调用方需保证与 `JsonStore` 使用同一 `storage_dir`（测试中已对 `official_sync_service` 内绑定路径做双补丁）。

## 6. 结论
- **M5 准入**：功能与契约测试通过；可在配置好计划任务与期号参数后接入生产调度。

## 7. 回滚预案
- 回滚：恢复 `apps/api/app/routers/api.py`、`optimization_service.py`、`model_registry_service.py`、`official_sync_service.py` 及新增 `services/*`、`tests/test_m5*.py` 等到 M5 前版本；清空或还原 `storage/scheduler_logs.json` 中 `idempotency` 结构（若需重跑任务）。
