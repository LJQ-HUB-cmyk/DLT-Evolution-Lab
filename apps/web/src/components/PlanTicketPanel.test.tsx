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
});
