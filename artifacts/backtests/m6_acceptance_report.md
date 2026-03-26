# M6 验收报告（执行记录）

## 1. 基本信息

- 验收日期：2026-03-26
- 验收方式：自动化测试 + 构建产物检查（Composer2.0 / M6 清单）
- 前端工程路径：`apps/web`
- 后端工程路径：`apps/api`

## 2. 验收范围

对照《M6-前端体验与测试闭环-详细技术规范.md》与《M6-Composer2.0-任务拆解与执行清单.md》：

- 页面信息架构（左历史 / 右上状态与模型与热力 / 右中票面与贡献 / 右下 run、日志、漂移、优化、复盘）
- `GET /api/issues/status` 聚合 `schedulerLogs`、`postmortems`、`optimizationRuns`（只读展示，不增删核心 API 路径）
- 响应式：桌面双栏、`>=1200px` 双栏；`768–1199px` 历史抽屉；`<768px` 纵向堆叠与顶部 sticky 元信息
- 前端：`api.ts` 超时（12s）、幂等 GET 重试 1 次、`ApiError` 与 FastAPI `detail` 映射
- 测试闭环：Vitest 单测/集成、Playwright 桌面/移动各 1 条冒烟（API 通过 `page.route` 模拟）
- **ECharts**：`src/test/setup.ts` 对 `echarts/core` 使用 `importActual` 并 **仅 mock `init`**，避免 zrender/canvas 在 jsdom 中崩溃；`PositionHeatPanel` / `DriftTrendPanel` 在单测中通过 **非 jsdom UA** 分支覆盖 `useEffect` 主路径

## 3. 验收项与结果

| 项 | 结果 |
|----|------|
| 桌面/移动布局符合规范（含抽屉与 sticky） | 通过 |
| 漂移 / 优化 / 复盘三面板可用 | 通过 |
| 关键交互（实验、发布、同步降级条、日志重试） | 通过 |
| 错误态与降级提示可读 | 通过 |
| `npm run build` 通过 | 通过 |
| 前端测试（单测+集成+E2E） | 通过 |

## 4. 测试命令与摘要

在 `apps/web` 目录执行：

```bash
npm run test
npm run test:coverage
npm run build
npm run test:e2e
```

在 `apps/api` 目录执行：

```bash
python -m pytest -q
```

**本次执行摘要：**

- `npm run test`：Vitest 全部通过；`e2e/` 在 `vite.config.ts` 的 `test.exclude` 中排除，避免 Playwright 规格被 Vitest 收集。
- `npm run test:coverage`：门禁 **`lines` / `statements` / `functions` ≥ 85%**，**`branches` ≥ 80%**；图表面板 **纳入** 覆盖率统计（不再排除文件）。典型一次结果：**全文件行覆盖率约 96.6%**，分支约 **80.7%**（以本机 `vitest run --coverage` 输出为准）。
- `npm run build`：成功；主入口 JS gzip 约 **52.6KB**；`echarts` 独立 chunk gzip 约 **170.7KB**（懒加载面板）。
- `npm run test:e2e`：**2 passed**（desktop：首页 + predict；mobile：抽屉 + sticky）；`playwright.config` 使用 `npm run dev -- --host 127.0.0.1 --port 5173` 以满足 URL 探测。
- `pytest`：全量建议合并前执行；`test_issue_status_m6.py` 校验 status 聚合字段。

## 5. 性能实测

M6 第 7 节预算（FCP/TTI/交互 p95）需在**标准机 + 生产构建 + Lighthouse/Performance** 下复测；本次记录构建产物 gzip 体积（见上）。

## 6. 风险与遗留

1. **App.tsx 分支覆盖率**：行与函数已达 100%，部分三元/短路分支（如 `degradedBanner` 内联子表达式）仍可继续加用例压测分支占比。
2. **E2E 环境**：CI 中需保证 Playwright 浏览器缓存与端口可用；`reuseExistingServer` 在 `CI=true` 时为 false。
3. **真机图表**：单测验证 `init`/`setOption` 调用链；像素级与动画仍以 E2E/人工看图为准。

## 7. 结论

- **M6 是否准入生产**：条件性 **是** —— 以「覆盖率门禁满足 M6 口径、构建与 E2E 冒烟通过、status 聚合契约稳定」为条件；上线前需真实后端联调 + 性能复测。
- **条件说明**：全链路依赖足量历史期数据与 `storage/*.json` 一致性。
