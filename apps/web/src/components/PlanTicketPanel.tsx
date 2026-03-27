import type { Ticket } from "../types";

type Props = {
  title: string;
  tickets: Ticket[];
};

function fmt(n: number) {
  return String(n).padStart(2, "0");
}

function tagLine(tags: string[] | undefined, title: string): string {
  const t = tags ?? [];
  const parts: string[] = [];
  if (t.includes("stats_aesthetic")) {
    parts.push("统计结构");
  }
  if (t.includes("xuanxue_light")) {
    parts.push("玄学轻优化");
  }
  if (title.includes("方案 3") && parts.length === 0) {
    parts.push("plan3");
  }
  return parts.length ? ` · ${parts.join(" / ")}` : "";
}

function factorHint(tags: string[] | undefined): string {
  const t = tags ?? [];
  if (t.includes("stats_aesthetic")) {
    return "结构统计组";
  }
  if (t.includes("xuanxue_light")) {
    return "玄学轻优化组";
  }
  return "综合筛选";
}

export function PlanTicketPanel({ title, tickets }: Props) {
  return (
    <section className="panel plan-ticket-panel m3-card-enter" style={{ animationDelay: "120ms" }}>
      <div className="panel-title">{title}</div>
      <div className="ticket-grid">
        {tickets.map((t, idx) => (
          <div key={idx} className="ticket-card">
            <div className="ticket-label">
              #{idx + 1}
              {t.tags?.includes("anchor") ? " · 永久跟买" : ""}
              {tagLine(t.tags, title)}
            </div>
            <div className="balls-row">
              {t.front.map((n) => (
                <span key={`f-${n}`} className="ball ball-red m3-ball-refresh">
                  {fmt(n)}
                </span>
              ))}
              {t.back.map((n) => (
                <span key={`b-${n}`} className="ball ball-blue m3-ball-refresh">
                  {fmt(n)}
                </span>
              ))}
            </div>
            <div className="ticket-meta mono small">评分 {t.score.toFixed(3)}</div>
            <div className="ticket-meta small muted">摘要：{factorHint(t.tags)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
