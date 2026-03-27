import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlanTicketPanel } from "./PlanTicketPanel";
import type { Ticket } from "../types";

describe("PlanTicketPanel", () => {
  it("renders ticket balls", () => {
    const tickets: Ticket[] = [
      { front: [1, 12, 23, 30, 35], back: [3, 11], score: 0.5, tags: [] },
    ];
    render(<PlanTicketPanel title="方案 1" tickets={tickets} />);
    expect(screen.getByText("01")).toBeInTheDocument();
    expect(screen.getByText("35")).toBeInTheDocument();
  });

  it("shows plan3 group labels when tags present", () => {
    const tickets: Ticket[] = [
      {
        front: [2, 4, 6, 8, 10],
        back: [1, 2],
        score: 0.7,
        tags: ["stats_aesthetic", "xuanxue_light"],
      },
    ];
    render(<PlanTicketPanel title="方案 3" tickets={tickets} />);
    expect(screen.getByText(/· 统计结构 \//)).toBeInTheDocument();
    expect(screen.getByText(/玄学轻优化/)).toBeInTheDocument();
    expect(screen.getByText(/摘要：结构统计组/)).toBeInTheDocument();
  });
});
