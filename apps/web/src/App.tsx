import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";

import { ContributionPanel } from "./components/ContributionPanel";
import { ControlPanel } from "./components/ControlPanel";
import { DataStatusPanel } from "./components/DataStatusPanel";
import { ExperimentRunPanel } from "./components/ExperimentRunPanel";
import { HistoryPane } from "./components/HistoryPane";
import { ModelMetaPanel } from "./components/ModelMetaPanel";
import { OptimizationPanel } from "./components/OptimizationPanel";
import { PlanTicketPanel } from "./components/PlanTicketPanel";
import { PostmortemPanel } from "./components/PostmortemPanel";
import { RunLogPanel } from "./components/RunLogPanel";
import {
  fetchAnalysis,
  fetchIssueStatus,
  fetchIssues,
  fetchModels,
  fetchRuns,
  runPredict,
  runPublish,
  syncOfficialData,
} from "./lib/api";
import type {
  AnalysisResponse,
  DrawIssue,
  IssueStatus,
  ModelRegistryItem,
  PredictionRun,
  SyncSummary,
} from "./types";

const PositionHeatPanel = lazy(() =>
  import("./components/PositionHeatPanel").then((mod) => ({ default: mod.PositionHeatPanel })),
);
const DriftTrendPanel = lazy(() =>
  import("./components/DriftTrendPanel").then((mod) => ({ default: mod.DriftTrendPanel })),
);

type SyncDialogState = {
  open: boolean;
  title: string;
  lines: string[];
};

const defaultStatus = (): IssueStatus => ({
  issueCount: 0,
  modelCount: 0,
  latestSyncAt: null,
  latestIssue: null,
  logCount: 0,
  schedulerLogs: [],
  postmortems: [],
  optimizationRuns: [],
});

const defaultSyncDialog = (): SyncDialogState => ({
  open: false,
  title: "",
  lines: [],
});

export default function App() {
  const [issues, setIssues] = useState<DrawIssue[]>([]);
  const [runs, setRuns] = useState<PredictionRun[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [status, setStatus] = useState<IssueStatus>(defaultStatus);
  const [models, setModels] = useState<ModelRegistryItem[]>([]);
  const [syncSummary, setSyncSummary] = useState<SyncSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [targetIssue, setTargetIssue] = useState("next");
  const [apiError, setApiError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [syncDialog, setSyncDialog] = useState<SyncDialogState>(defaultSyncDialog);

  const openSyncDialog = useCallback((title: string, lines: string[]) => {
    setSyncDialog({ open: true, title, lines });
  }, []);

  const champion = useMemo(
    () => models.find((m) => m.status === "champion") ?? models[0] ?? null,
    [models],
  );

  const scopedRuns = useMemo(() => runs.filter((r) => r.target_issue === targetIssue), [runs, targetIssue]);
  const latest = scopedRuns.length ? scopedRuns[scopedRuns.length - 1] : runs.length ? runs[runs.length - 1] : null;
  const plan1 = latest?.plan1 ?? [];
  const plan2 = latest?.plan2 ?? [];

  const refreshCore = useCallback(async () => {
    setAnalysisLoading(true);
    setStatusError(null);
    try {
      const [issueData, runData, issueStatus, an, reg] = await Promise.all([
        fetchIssues(),
        fetchRuns(80),
        fetchIssueStatus(),
        fetchAnalysis(targetIssue),
        fetchModels(),
      ]);
      setIssues(issueData);
      setRuns(runData);
      setStatus(issueStatus);
      setAnalysis(an);
      setModels(reg?.items ?? []);
      if (issueStatus.issueCount === 0 && issueStatus.logCount === 0 && issueData.length === 0 && runData.length === 0) {
        setStatusError("无法连接后端或状态为空，请确认 API 已启动。");
      }
    } finally {
      setAnalysisLoading(false);
    }
  }, [targetIssue]);

  const refreshAfterMutation = useCallback(async () => {
    try {
      const [runData, issueStatus] = await Promise.all([fetchRuns(80), fetchIssueStatus()]);
      setRuns(runData);
      setStatus(issueStatus);
    } catch {
      setStatusError("局部刷新失败，请重试。");
    }
  }, []);

  useEffect(() => {
    void refreshCore();
  }, [refreshCore]);

  async function onExperiment() {
    setLoading(true);
    setApiError(null);
    try {
      await runPredict(targetIssue);
      await refreshAfterMutation();
    } catch (e) {
      setApiError(e instanceof Error ? e.message : "实验失败");
    } finally {
      setLoading(false);
    }
  }

  async function onPublish() {
    setPublishing(true);
    setApiError(null);
    try {
      await runPublish(targetIssue);
      await refreshAfterMutation();
    } catch (e) {
      setApiError(e instanceof Error ? e.message : "发布失败");
    } finally {
      setPublishing(false);
    }
  }

  async function onSync() {
    setSyncing(true);
    setApiError(null);
    const prevIssueCount = status.issueCount;
    try {
      const summary = await syncOfficialData();
      setSyncSummary(summary);
      await refreshCore();

      const lines: string[] = [];
      const warnings = summary.warnings ?? [];
      const newIssueCount = Number(summary.newIssueCount ?? 0);
      const mode = String(summary.mode ?? "unknown");
      const taskStatus = summary.scheduler_context?.task_status;

      if (mode === "skipped" || taskStatus === "skipped") {
        lines.push("本次同步被系统跳过，通常是短时间重复触发或当前无需增量更新。");
      }
      if (summary.degraded) {
        lines.push("同步处于降级模式，可能使用了缓存或部分数据源失败。");
      }
      if (warnings.length > 0) {
        lines.push(`告警：${warnings.join(" | ")}`);
      }
      const historyWarnings = summary.historySync?.warnings ?? [];
      if (historyWarnings.length > 0) {
        lines.push(`历史拉取告警：${historyWarnings.join(" | ")}`);
      }
      if (newIssueCount <= 0) {
        lines.push("本次没有新增历史期号，可能是已最新或源端未返回新数据。");
      }
      if (prevIssueCount > 0 && Number(summary.issueCount ?? 0) < prevIssueCount) {
        lines.push("检测到历史期数减少，请检查同步源或本地数据文件是否被覆盖。");
      }
      if (lines.length > 0) {
        openSyncDialog("同步完成，但有提示", lines);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "同步失败";
      setApiError(msg);
      openSyncDialog("同步失败", [msg]);
    } finally {
      setSyncing(false);
    }
  }

  const degradedBanner =
    syncSummary?.degraded || (syncSummary?.warnings && syncSummary.warnings.length > 0) ? (
      <div className="degraded-banner" role="status">
        同步降级或告警：
        {syncSummary?.degraded ? " 已降级 " : ""}
        {syncSummary?.warnings?.length ? syncSummary.warnings.join(" | ") : ""}
      </div>
    ) : null;

  const stickyMeta = (
    <div className="sticky-meta" data-testid="sticky-meta">
      <div className="sticky-chip mono">{analysis?.modelVersion ?? champion?.version ?? "—"}</div>
      <div className="sticky-chip">{champion ? `信用分 ${champion.credit.toFixed(2)}` : "信用分 —"}</div>
    </div>
  );

  return (
    <main className="app-shell" data-testid="app-root">
      <header className="topbar m3-card-enter">
        <div className="topbar-row">
          <div>
            <h1>DLT Evolution Lab</h1>
            <p>透明预测引擎</p>
          </div>
          {stickyMeta}
        </div>
      </header>
      {degradedBanner}
      <button type="button" className="drawer-toggle" onClick={() => setDrawerOpen((v) => !v)}>
        历史开奖
      </button>
      <section className={`layout-grid ${drawerOpen ? "drawer-open" : ""}`}>
        <div className="left-col">
          <HistoryPane
            issues={issues}
            selectedIssue={targetIssue}
            onSelectIssue={setTargetIssue}
            onSync={onSync}
            syncing={syncing}
          />
        </div>
        <div className="right-col">
          <div className="right-upper">
            <DataStatusPanel status={status} syncSummary={syncSummary} syncing={syncing} onSync={onSync} />
            <div className="analysis-grid upper-analysis">
              <ModelMetaPanel
                analysis={analysis}
                loading={analysisLoading}
                champion={champion}
                latestDrift={latest?.drift ?? null}
              />
              <Suspense
                fallback={
                  <section className="panel m3-card-enter" style={{ animationDelay: "80ms" }}>
                    <div className="panel-title">位置热力</div>
                    <div className="pad muted">加载图表...</div>
                  </section>
                }
              >
                <PositionHeatPanel analysis={analysis} />
              </Suspense>
            </div>
            <ControlPanel
              runs={runs}
              targetIssue={targetIssue}
              onTargetIssueChange={setTargetIssue}
              onExperiment={onExperiment}
              onPublish={onPublish}
              loading={loading}
              publishing={publishing}
              apiError={apiError}
            />
            {loading ? <div className="loading-mask">正在实验计算...</div> : null}
          </div>
          <div className="right-mid">
            <PlanTicketPanel title="方案 1（结构化）" tickets={plan1} />
            <PlanTicketPanel title="方案 2（轻结构）" tickets={plan2} />
            <ContributionPanel analysis={analysis} />
          </div>
          <div className="right-lower">
            <ExperimentRunPanel runs={runs} targetIssue={targetIssue} />
            <RunLogPanel logs={status.schedulerLogs} errorMessage={statusError} onRetry={() => void refreshCore()} />
            <Suspense
              fallback={
                <section className="panel">
                  <div className="panel-title">漂移趋势</div>
                  <div className="pad muted">加载图表...</div>
                </section>
              }
            >
              <DriftTrendPanel runs={runs} />
            </Suspense>
            <OptimizationPanel runs={status.optimizationRuns} />
            <PostmortemPanel items={status.postmortems} targetIssue={targetIssue} />
          </div>
        </div>
      </section>

      {syncDialog.open ? (
        <div className="sync-modal-mask" role="presentation" onClick={() => setSyncDialog(defaultSyncDialog())}>
          <div
            className="sync-modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="sync-dialog-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="sync-dialog-title">{syncDialog.title}</h3>
            <ul>
              {syncDialog.lines.map((line, idx) => (
                <li key={idx}>{line}</li>
              ))}
            </ul>
            <div className="sync-modal-actions">
              <button type="button" className="primary-btn" onClick={() => setSyncDialog(defaultSyncDialog())}>
                我知道了
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
