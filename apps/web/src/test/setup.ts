import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// @ts-expect-error jsdom
global.ResizeObserver = ResizeObserverStub;

/** Avoid zrender/canvas in jsdom while still exercising panel useEffect + setOption paths. */
vi.mock("echarts/core", async () => {
  const actual = await vi.importActual<typeof import("echarts/core")>("echarts/core");
  return {
    ...actual,
    init: vi.fn(() => ({
      setOption: vi.fn(),
      dispose: vi.fn(),
      resize: vi.fn(),
    })),
  };
});
