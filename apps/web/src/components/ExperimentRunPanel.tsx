import { summarizeDrift } from "../lib/formatters";
import type { PredictionRun } from "../types";

type Props = {
  runs: PredictionRun[];
  targetIssue: string;
};

export function ExperimentRunPanel({ runs, targetIssue }: Props) {
  const scoped = runs.filter((r) => r.target_issue === targetIssue);
  const list = scoped.length ? scoped : runs;
  const latest = list.slice(-12).reverse();
  return (
    <section className="panel experiment-run-panel m3-card-enter" style={{ animationDelay: "160ms" }}>
      <div className="panel-title">实验 Run 列表</div>
      <div className="runlog-list">
        {latest.length === 0 ? <p className="muted">暂无实验记录</p> : null}
        {latest.map((r) => (
          <div key={r.run_id} className="runlog-item" data-testid={`run-row-${r.run_id}`}>
            <div className="issue-meta">
              <strong className="mono">{r.run_id}</strong>
              <span>{r.created_at}</span>
            </div>
            <div className="mono small">
              {r.model_version} · seed {r.seed} · {r.target_issue}
              {r.snapshot_hash ? ` · ${r.snapshot_hash.slice(0, 10)}…` : ""}
            </div>
            <div className="muted small">{summarizeDrift(r.drift ?? null)}</div>
            <div className="balls-row compact">
              {(r.plan1[0]?.front ?? []).map((n) => (
                <span key={n} className="ball ball-red">
                  {String(n).padStart(2, "0")}
                </span>
              ))}
              {(r.plan1[0]?.back ?? []).map((n) => (
                <span key={n} className="ball ball-blue">
                  {String(n).padStart(2, "0")}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
