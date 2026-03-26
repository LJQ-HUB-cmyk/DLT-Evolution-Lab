# M6 Composer2.0 任务拆解与执行清单

## 1. 使用方式
- 本清单是 `M6-前端体验与测试闭环-详细技术规范.md` 的执行拆解版。
- Composer2.0 必须按编号执行，跨层依赖必须满足。
- 每任务完成后提交：
  - 代码变更列表
  - 组件/API 契约变更
  - 自测证据
  - 风险与遗留

## 2. 执行泳道
- 泳道 A：API 契约与状态层
- 泳道 B：页面与组件实现
- 泳道 C：性能与响应式优化
- 泳道 D：测试闭环与验收

## 3. 全局完成定义（DoD）
- 前端可完整展示 M3/M4/M5 核心信息。
- 关键交互链路可用且有错误恢复。
- 桌面/移动端布局稳定，无关键视觉退化。
- 测试与构建全部通过。

## 4. 依赖图（必须遵守）
- A1 完成后 B1/B2 才能稳定渲染数据。
- B1 完成后 C1 才能做性能压测与优化。
- B2 完成后 D2 才能执行完整集成/E2E 测试。
- D3 必须最后执行。

## 5. 任务清单

## A 泳道（契约与状态）

### A1. API 类型与契约补齐
- 目标：
  - 对齐后端 M4/M5 响应字段，移除隐式 `any`。
- 实现文件：
  - `apps/web/src/types.ts`
  - `apps/web/src/lib/api.ts`
- 必须结果：
  - `DriftReport`, `OptimizationRun`, `PostmortemSummary` 类型完善。
  - 错误码映射与降级提示统一。
- 自测命令：
  - `npm run test -- --run`

### A2. 页面级状态管理规范化
- 目标：
  - 保证触发 predict/publish 后局部刷新，避免全页刷新。
- 实现文件：
  - `apps/web/src/App.tsx`
  - `apps/web/src/components/ControlPanel.tsx`
- 必须结果：
  - 期号切换、实验触发、日志刷新互不冲突。

## B 泳道（页面与组件）

### B1. 新增 M4/M5 业务面板
- 目标：
  - 增加漂移、优化、复盘三类核心面板。
- 实现文件：
  - `apps/web/src/components/DriftTrendPanel.tsx`（新增）
  - `apps/web/src/components/OptimizationPanel.tsx`（新增）
  - `apps/web/src/components/PostmortemPanel.tsx`（新增）
  - `apps/web/src/App.tsx`
- 必须结果：
  - 面板可独立渲染并能联动当前期号。
- 自测命令：
  - `npm run test -- --run`

### B2. 关键现有组件升级
- 目标：
  - 扩展元信息和日志可读性，支持 M4/M5 新字段。
- 实现文件：
  - `apps/web/src/components/ModelMetaPanel.tsx`
  - `apps/web/src/components/ExperimentRunPanel.tsx`
  - `apps/web/src/components/RunLogPanel.tsx`
- 必须结果：
  - 展示 `credit_score`、`drift_level`、`postmortem_status`。
  - 错误态和空态明确可读。

## C 泳道（性能与响应式）

### C1. 响应式布局优化
- 目标：
  - 桌面双栏、移动折叠布局一致稳定。
- 实现文件：
  - `apps/web/src/styles.css`
  - `apps/web/src/App.tsx`
- 必须结果：
  - 无横向滚动条，关键状态首屏可见。

### C2. 性能预算治理
- 目标：
  - 达到首屏与交互性能预算。
- 实现文件：
  - `apps/web/src/App.tsx`
  - `apps/web/src/components/*.tsx`
  - `apps/web/vite.config.ts`
- 必须结果：
  - 图表组件按需懒加载。
  - 重渲染受控，切换期号 `p95 < 400ms`。
- 自测命令：
  - `npm run build`

## D 泳道（测试与验收）

### D1. 单测与集成补齐
- 目标：
  - 覆盖新面板渲染、关键交互、错误恢复。
- 实现文件：
  - `apps/web/src/components/*.test.tsx`
  - `apps/web/src/App.test.tsx`
- 必须结果：
  - 前端新增代码覆盖率 `>=85%`。
- 自测命令：
  - `npm run test -- --run`

### D2. E2E 冒烟接入
- 目标：
  - 建立桌面/移动最小冒烟用例。
- 实现文件：
  - `apps/web/e2e/smoke.desktop.spec.ts`（新增）
  - `apps/web/e2e/smoke.mobile.spec.ts`（新增）
  - `apps/web/playwright.config.ts`（新增）
- 必须结果：
  - 两条冒烟用例稳定通过。

### D3. 验收报告收口
- 目标：
  - 输出 M6 验收报告。
- 交付文件：
  - `artifacts/backtests/m6_acceptance_report.md`
- 必须结果：
  - 验收项、性能结果、测试命令、风险清单完整。

## 6. 阻塞处理规则（强制）
- 后端字段变动阻塞：
  - 先补类型适配层，禁止组件直接硬编码容错。
- 图表性能阻塞：
  - 优先降采样与懒加载，禁止删除核心面板。
- 移动端拥挤阻塞：
  - 优先重排信息层级，禁止缩小字体到不可读。

## 7. 每日同步格式（Composer2.0 必填）
- 今日完成任务编号
- 进行中任务编号
- 阻塞与影响
- 明日计划
- 是否偏离规范（是/否，若是必须说明）

## 8. 交付顺序建议（并行最大化）
1. 并行启动：A1 + C1
2. 并行推进：A2 + B1
3. 合流阶段：B2 + C2
4. 测试收口：D1 + D2
5. 最终验收：D3

---

本清单用于 M6 执行，不用于讨论。若执行与规范冲突，先报告差异，再继续实现。
