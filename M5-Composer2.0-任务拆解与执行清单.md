# M5 Composer2.0 任务拆解与执行清单

## 1. 使用方式
- 本清单是 `M5-开奖复盘与自动任务-详细技术规范.md` 的执行拆解版。
- Composer2.0 必须按编号执行；跨层任务需满足依赖。
- 每任务提交：
  - 代码变更列表
  - 接口/数据结构变更
  - 自测结果
  - 风险与遗留

## 2. 执行泳道
- 泳道 A：调度与状态机
- 泳道 B：开奖回填与复盘
- 泳道 C：自动触发优化与晋升
- 泳道 D：测试与验收

## 3. 全局完成定义（DoD）
- 定时任务、手动触发、重试触发都走统一状态机。
- 幂等键生效，重复执行不污染 `issues/predictions/postmortems`。
- 奖级计算与复盘得分可追溯。
- 任务日志全字段完整，失败可定位。

## 4. 依赖图（必须遵守）
- A1/A2 完成后 B1/B2 才能稳定落库。
- B2 完成后 C1 才能基于复盘触发优化。
- C1 完成后 C2 才能做晋升评估。
- D3 必须最后执行。

## 5. 任务清单

## A 泳道（调度与状态机）

### A1. 统一任务状态机
- 目标：
  - 落地 `queued/running/succeeded/failed/skipped/compensated`。
- 实现文件：
  - `jobs/scheduler_service.py`
  - `apps/api/app/services/scheduler_audit_service.py`
- 必须结果：
  - 状态流转可审计，异常中断可恢复。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_scheduler_state_machine.py`

### A2. 幂等与重试策略
- 目标：
  - 统一幂等键与退避重试。
- 实现文件：
  - `jobs/scheduler_service.py`
  - `apps/api/app/services/json_store.py`
- 必须结果：
  - 同 key 成功后重复执行自动 `skipped`。
  - 失败重试保留 `attempt_no`。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_task_idempotency.py`

### A3. 注册任务脚本升级
- 目标：
  - 固化 09:00/20:30/21:45 任务策略。
- 实现文件：
  - `jobs/register_tasks.ps1`
- 必须结果：
  - 重复运行脚本不会创建重复任务。
  - 任务参数（路径、Python、环境）可配置。

## B 泳道（开奖回填与复盘）

### B1. 开奖回填与校验
- 目标：
  - 检测官方开奖并安全回填。
- 实现文件：
  - `apps/api/app/services/official_sync_service.py`
  - `apps/api/app/services/automation_pipeline.py`
- 必须结果：
  - 数据冲突不覆盖，转人工确认。
  - 回填成功后触发复盘流水。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_draw_ingestion.py`

### B2. 奖级计算与复盘报告
- 目标：
  - 完成奖级映射、命中矩阵、复盘评分。
- 实现文件：
  - `apps/api/app/services/postmortem_service.py`
  - `storage/postmortems.json`
- 必须结果：
  - 奖级映射覆盖 1-9 级与无奖。
  - 复盘结果可按 issue/run 查询。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_prize_rules.py`
  - `python -m pytest -q apps/api/tests/test_postmortem_service.py`

## C 泳道（自动触发优化与晋升）

### C1. 复盘触发优化
- 目标：
  - 按复盘阈值触发 `optimize_job`。
- 实现文件：
  - `apps/api/app/services/automation_pipeline.py`
  - `apps/api/app/services/optimization_service.py`
- 必须结果：
  - 低分或连续无命中时自动触发优化并记录原因。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_postmortem_trigger_optimize.py`

### C2. 自动晋升评估
- 目标：
  - 优化后自动做候选晋升评估，不直接切换 champion。
- 实现文件：
  - `apps/api/app/services/model_registry_service.py`
- 必须结果：
  - 仅门禁通过才可晋升。
  - 晋升证据写入模型注册表。
- 自测命令：
  - `python -m pytest -q apps/api/tests/test_auto_promotion_eval.py`

## D 泳道（测试与验收）

### D1. API 契约与日志契约
- 目标：
  - 校验 `postmortem/runs/sync` 返回契约与日志字段完整性。
- 实现文件：
  - `apps/api/tests/test_m5_api_contract.py`
  - `apps/api/tests/test_scheduler_logs_contract.py`
- 必须结果：
  - 日志关键字段缺失率 `=0`。

### D2. 端到端自动化回归
- 目标：
  - 模拟开奖后自动完成：回填 -> 复盘 -> 优化 -> 晋升评估。
- 实现文件：
  - `apps/api/tests/test_draw_to_postmortem_pipeline.py`
- 必须结果：
  - 全链路在模拟环境稳定通过。

### D3. 验收报告收口
- 目标：
  - 产出 M5 验收报告。
- 交付文件：
  - `artifacts/backtests/m5_acceptance_report.md`
- 必须结果：
  - 记录验收点、命令、结果、失败复盘与回滚预案。

## 6. 阻塞处理规则（强制）
- 官方数据异常：
  - 允许降级但不得覆盖已有有效开奖。
- 连续任务失败：
  - 进入退避重试，超过阈值发告警并人工接管。
- 复盘计算异常：
  - 保留原始输入快照，禁止直接跳过产出“成功”状态。

## 7. 每日同步格式（Composer2.0 必填）
- 今日完成任务编号
- 进行中任务编号
- 阻塞与影响
- 明日计划
- 是否偏离规范（是/否，若是必须说明）

## 8. 交付顺序建议（并行最大化）
1. 并行启动：A1 + A3
2. 并行推进：A2 + B1
3. 合流阶段：B2 + C1
4. 晋升联调：C2
5. 测试收口：D1 + D2
6. 最终验收：D3

---

本清单用于 M5 执行，不用于讨论。若执行与规范冲突，先报告差异，再继续实现。
