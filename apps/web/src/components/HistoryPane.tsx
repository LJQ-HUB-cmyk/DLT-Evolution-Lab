import { useMemo, useState } from "react";

import type { DrawIssue } from "../types";
import { Ball } from "./Ball";

type HistoryPaneProps = {
  issues: DrawIssue[];
  selectedIssue: string;
  onSelectIssue: (issue: string) => void;
};

export function HistoryPane({ issues, selectedIssue, onSelectIssue }: HistoryPaneProps) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) {
      return issues;
    }
    return issues.filter((i) => i.issue.toLowerCase().includes(t));
  }, [issues, q]);

  return (
    <section className="panel history-pane" data-testid="history-pane">
      <header className="panel-title">历史开奖</header>
      <div className="history-toolbar">
        <input
          aria-label="筛选期号"
          className="history-filter"
          placeholder="筛选期号…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button className="ghost-btn" type="button" onClick={() => onSelectIssue("next")}>
          目标：下一期
        </button>
      </div>
      <div className="history-list">
        {filtered.length === 0 ? (
          <div className="empty">暂无同步数据或筛选无结果</div>
        ) : (
          filtered.map((issue) => {
            const active = issue.issue === selectedIssue;
            return (
              <article
                className={`history-item ${active ? "history-item-active" : ""}`}
                key={issue.issue}
                data-testid={`history-item-${issue.issue}`}
              >
                <button type="button" className="history-select-btn" onClick={() => onSelectIssue(issue.issue)}>
                  <div className="issue-meta">
                    <strong>期号 {issue.issue}</strong>
                    <span>{issue.draw_date ?? "--"}</span>
                  </div>
                  <div className="balls-row">
                    {issue.front.map((n) => (
                      <Ball key={`f-${issue.issue}-${n}`} value={n} color="red" />
                    ))}
                    {issue.back.map((n) => (
                      <Ball key={`b-${issue.issue}-${n}`} value={n} color="blue" />
                    ))}
                  </div>
                </button>
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}
