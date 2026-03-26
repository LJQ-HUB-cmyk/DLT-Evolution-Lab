import type { SchedulerLogEntry } from "../types";

type RunLogPanelProps = {
  logs: SchedulerLogEntry[];
  onRetry?: () => void;
  errorMessage?: string | null;
};

export function RunLogPanel({ logs, onRetry, errorMessage }: RunLogPanelProps) {
  const latest = [...logs].slice(-24).reverse();
  return (
    <section className="panel runlog-pane" data-testid="run-log-panel">
      <header className="panel-title">自动任务 / 调度日志</header>
      <div className="runlog-list">
        {errorMessage ? (
          <div className="error-banner">
            <span>{errorMessage}</span>
            {onRetry ? (
              <button type="button" className="ghost-btn" onClick={onRetry}>
                重试刷新
              </button>
            ) : null}
          </div>
        ) : null}
        {latest.length === 0 && !errorMessage ? (
          <div className="empty">暂无调度日志</div>
        ) : null}
        {latest.map((log, idx) => (
          <article key={`${log.timestamp}-${idx}`} className="runlog-item">
            <div className="issue-meta">
              <strong>{log.action}</strong>
              <span>{log.timestamp}</span>
            </div>
            <div className="muted small">
              {log.result}
              {log.detail ? ` · ${log.detail}` : ""}
            </div>
            {log.target_issue ? <div className="mono small">期号 {log.target_issue}</div> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
