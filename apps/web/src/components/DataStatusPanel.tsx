import type { IssueStatus, SyncSummary } from "../types";

type DataStatusPanelProps = {
  status: IssueStatus;
  syncSummary: SyncSummary | null;
  syncing: boolean;
  onSync: () => void;
};

export function DataStatusPanel({ status, syncSummary, syncing, onSync }: DataStatusPanelProps) {
  const modeLabel = (mode?: string) => {
    if (!mode) {
      return "未知";
    }
    if (mode === "live") {
      return "在线";
    }
    if (mode === "cache") {
      return "缓存";
    }
    if (mode === "skipped") {
      return "跳过";
    }
    return mode;
  };

  return (
    <section className="panel status-pane">
      <header className="panel-title">数据状态</header>
      <div className="status-content">
        <div className="stats-grid">
          <div className="stat-card">
            <span>历史期数</span>
            <strong>{status.issueCount}</strong>
          </div>
          <div className="stat-card">
            <span>最新期号</span>
            <strong>{status.latestIssue ?? "--"}</strong>
          </div>
          <div className="stat-card">
            <span>模型记录</span>
            <strong>{status.modelCount}</strong>
          </div>
        </div>
        <p className="muted sync-info">最近同步：{status.latestSyncAt ?? "从未同步"}</p>
        <button className="primary-btn" disabled={syncing} onClick={onSync} type="button">
          {syncing ? "同步中..." : "同步官方数据"}
        </button>
        {syncSummary ? (
          <div className={`sync-summary ${syncSummary.degraded ? "warn" : "ok"}`}>
            <div>
              {syncSummary.degraded ? "同步降级" : "同步成功"}（{modeLabel(syncSummary.mode)}）于{" "}
              {syncSummary.syncedAt}
            </div>
            <div>
              新增 {syncSummary.newIssueCount} 期，累计 {syncSummary.issueCount} 期，规则版本{" "}
              {syncSummary.ruleVersionCount}
            </div>
            {syncSummary.warnings.length > 0 ? (
              <div className="muted">告警：{syncSummary.warnings.join(" | ")}</div>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
