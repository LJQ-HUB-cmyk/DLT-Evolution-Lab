import type { OptimizationRun } from "../types";

type Props = {
  runs: OptimizationRun[];
};

export function OptimizationPanel({ runs }: Props) {
  const statusLabel = (status: string) => {
    const m: Record<string, string> = {
      queued: "排队中",
      running: "执行中",
      succeeded: "已成功",
      failed: "已失败",
      skipped: "已跳过",
      compensated: "已补偿",
    };
    return m[status] ?? status;
  };

  const latest = [...runs].slice(-12).reverse();
  return (
    <section className="panel optimization-panel m3-card-enter" style={{ animationDelay: "120ms" }}>
      <div className="panel-title">优化任务与门禁</div>
      <div className="runlog-list">
        {latest.length === 0 ? <p className="muted">暂无优化记录</p> : null}
        {latest.map((r) => (
          <div key={r.run_id} className="runlog-item">
            <div className="issue-meta">
              <strong className="mono">{r.run_id}</strong>
              <span>{r.created_at}</span>
            </div>
            <div className="mono small">
              状态：<span className={`opt-status opt-${r.status}`}>{statusLabel(r.status)}</span>
              {r.objective ? ` · ${r.objective}` : ""}
            </div>
            {r.failure_reason ? <div className="error-inline">失败：{r.failure_reason}</div> : null}
            {typeof r.gate_passed === "boolean" ? (
              <div className="muted small">门禁：{r.gate_passed ? "通过" : "未通过"}</div>
            ) : null}
            {r.candidate_version ? <div className="muted small">候选版本：{r.candidate_version}</div> : null}
          </div>
        ))}
      </div>
    </section>
  );
}
