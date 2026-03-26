import type { IssueStatus, SyncSummary } from "../types";

type DataStatusPanelProps = {
  status: IssueStatus;
  syncSummary: SyncSummary | null;
  syncing: boolean;
  onSync: () => void;
};

export function DataStatusPanel({ status, syncSummary, syncing, onSync }: DataStatusPanelProps) {
  return (
    <section className="panel status-pane">
      <header className="panel-title">Data Status</header>
      <div className="status-content">
        <div className="stats-grid">
          <div className="stat-card">
            <span>Issues</span>
            <strong>{status.issueCount}</strong>
          </div>
          <div className="stat-card">
            <span>Latest Issue</span>
            <strong>{status.latestIssue ?? "--"}</strong>
          </div>
          <div className="stat-card">
            <span>Model Records</span>
            <strong>{status.modelCount}</strong>
          </div>
        </div>
        <p className="muted sync-info">Last sync: {status.latestSyncAt ?? "never"}</p>
        <button className="primary-btn" disabled={syncing} onClick={onSync} type="button">
          {syncing ? "Syncing..." : "Sync Official Data"}
        </button>
        {syncSummary ? (
          <div className={`sync-summary ${syncSummary.degraded ? "warn" : "ok"}`}>
            <div>
              {syncSummary.degraded ? "Degraded mode" : "Sync ok"} ({syncSummary.mode}) at{" "}
              {syncSummary.syncedAt}
            </div>
            <div>
              +{syncSummary.newIssueCount} new, total {syncSummary.issueCount}, rule versions{" "}
              {syncSummary.ruleVersionCount}
            </div>
            {syncSummary.warnings.length > 0 ? (
              <div className="muted">Warnings: {syncSummary.warnings.join(" | ")}</div>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
