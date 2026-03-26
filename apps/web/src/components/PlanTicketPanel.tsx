import type { Ticket } from "../types";

type Props = {
  title: string;
  tickets: Ticket[];
};

function fmt(n: number) {
  return String(n).padStart(2, "0");
}

export function PlanTicketPanel({ title, tickets }: Props) {
  return (
    <section className="panel plan-ticket-panel m3-card-enter" style={{ animationDelay: "120ms" }}>
      <div className="panel-title">{title}</div>
      <div className="ticket-grid">
        {tickets.map((t, idx) => (
          <div key={idx} className="ticket-card">
            <div className="ticket-label">#{idx + 1}</div>
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
          </div>
        ))}
      </div>
    </section>
  );
}
