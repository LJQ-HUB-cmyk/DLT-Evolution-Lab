import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PostmortemPanel } from "./PostmortemPanel";
import type { PostmortemSummary } from "../types";

describe("PostmortemPanel", () => {
  it("shows pending copy when empty", () => {
    render(<PostmortemPanel items={[]} targetIssue="next" />);
    expect(screen.getByText(/待开奖/)).toBeInTheDocument();
  });

  it("renders item status", () => {
    const items: PostmortemSummary[] = [
      {
        issue: "25100",
        model_version: "m",
        hit_summary: "done",
        weighted_return: 1.2,
        created_at: "t",
      },
    ];
    render(<PostmortemPanel items={items} targetIssue="25100" />);
    expect(screen.getByText(/25100/)).toBeInTheDocument();
    expect(screen.getByText("已记录")).toBeInTheDocument();
  });

  it("shows pending for pending summary", () => {
    const items: PostmortemSummary[] = [
      {
        issue: "25101",
        model_version: "m",
        hit_summary: "待开奖",
        weighted_return: 0,
        created_at: "t",
      },
    ];
    render(<PostmortemPanel items={items} targetIssue="25101" />);
    expect(screen.getAllByText("待开奖").length).toBeGreaterThanOrEqual(1);
  });
});
