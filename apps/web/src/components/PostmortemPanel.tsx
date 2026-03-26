import type { PostmortemSummary } from "../types";
import { postmortemStatus } from "../lib/formatters";

type Props = {
  items: PostmortemSummary[];
  targetIssue: string;
};

export function PostmortemPanel({ items, targetIssue }: Props) {
  const filtered =
    targetIssue && targetIssue !== "next"
      ? items.filter((p) => p.issue === targetIssue)
      : items.slice(-8).reverse();
  const display = filtered.length ? filtered : items.slice(-8).reverse();

  return (
    <section className="panel postmortem-panel m3-card-enter" style={{ animationDelay: "140ms" }}>
      <div className="panel-title">开奖复盘</div>
      <div className="runlog-list">
        {display.length === 0 ? (
          <p className="muted">待开奖 / 待回填 — 暂无复盘条目</p>
        ) : (
          display.map((p) => {
            const st = postmortemStatus(p);
            return (
              <div key={`${p.issue}-${p.created_at}`} className="runlog-item">
                <div className="issue-meta">
                  <strong className="mono">期号 {p.issue}</strong>
                  <span className={`pm-status pm-${st}`}>{st === "pending" ? "待开奖" : "已记录"}</span>
                </div>
                <div className="muted small">{p.model_version}</div>
                <div>{p.hit_summary}</div>
                <div className="mono small">加权回报 {p.weighted_return.toFixed(4)}</div>
                {p.feature_changes && p.feature_changes.length > 0 ? (
                  <ul className="factor-list">
                    {p.feature_changes.map((c, i) => (
                      <li key={i} className="factor-item small">
                        {c}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
