# dlt-evolution-lab

这是一个我自己做的超级大乐透量化实验项目。  
你可以把它理解成一套“会自己记账、会复盘、会持续优化”的预测实验工作台。

## 这个项目在解决什么问题

传统选号最大的痛点是：过程不透明、结果不可复盘、优化靠感觉。  
这个项目就是为了解决这三件事：

- 把预测过程拆开看清楚（不是黑箱）
- 每次预测都留痕，开奖后能对照复盘
- 发现漂移或效果下降时，自动触发优化

## 它能做什么

- 自动同步官方历史开奖数据（只用中国体彩网来源）
- 生成正式预测和实验预测（双轨制）
- 记录每次 run 的结果、漂移、模型版本和日志
- 开奖后自动回填命中、奖级和复盘报告
- 触发候选模型优化，并评估是否能晋升
- 前端提供桌面双栏 + 移动端折叠的可视化看板

## 项目截图

<img width="1920" height="945" alt="image" src="https://github.com/user-attachments/assets/6b89972d-c5af-4611-bb6e-2c00a343d182" />

## 技术栈

- 前端：React + Vite + TypeScript + ECharts
- 后端：FastAPI + Python
- 存储：JSON 文件
- 调度：Windows 任务计划 + 本地服务
- 测试：Vitest + Playwright + pytest

## 项目结构

```text
dlt-evolution-lab/
├─ apps/
│  ├─ api/                      # FastAPI backend
│  └─ web/                      # React frontend
├─ jobs/                        # 自动任务与调度脚本
├─ data/
│  ├─ raw/                      # 官方原始快照
│  └─ normalized/               # 标准化历史数据
├─ storage/                     # 运行态 JSON
├─ artifacts/backtests/         # 回测/校准/验收产物
└─ README.md
```

## 快速开始

### 启动后端

```powershell
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload --port 8000
```

### 启动前端

```powershell
cd apps/web
npm install
npm run dev
```

默认前端请求 `http://127.0.0.1:8000/api`。  
可通过 `VITE_API_BASE` 覆盖。

## 核心 API

- `GET /api/issues`
- `GET /api/issues/status`
- `POST /api/sync`
- `GET /api/analysis/{targetIssue}`
- `POST /api/publish/{targetIssue}`
- `POST /api/predict/{targetIssue}`
- `POST /api/anchor/recompute`
- `POST /api/postmortem/{issue}`
- `POST /api/optimize`
- `GET /api/models`
- `GET /api/runs`

## 开发命令

### 前端（apps/web）

```powershell
npm run test -- --run
npm run test:coverage
npm run build
npm run test:e2e
```

### 后端（apps/api）

```powershell
python -m pytest -q
```

## 自动任务（Windows）

```powershell
powershell -ExecutionPolicy Bypass -File jobs/register_tasks.ps1
```

默认策略：

- 每日 09:00 同步数据
- 周一/周三/周六 20:30 发布检查
- 周一/周三/周六 21:45 起每 5 分钟开奖轮询（2 小时）

## 免责声明

本项目用于算法实验与工程实践，不承诺中奖结果。  
请理性使用，遵守相关法律法规。
