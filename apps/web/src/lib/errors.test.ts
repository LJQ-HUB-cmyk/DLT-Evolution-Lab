import { describe, expect, it } from "vitest";

import { ApiError, mapHttpStatusToUserMessage, parseFastApiDetail } from "./errors";

describe("errors", () => {
  it("parseFastApiDetail reads error_code", () => {
    expect(parseFastApiDetail({ error_code: "X", message: "m" })).toEqual({ code: "X", message: "m" });
    expect(parseFastApiDetail("raw")).toEqual({ code: "HTTP_ERROR", message: "raw" });
  });

  it("mapHttpStatusToUserMessage", () => {
    expect(mapHttpStatusToUserMessage(422)).toContain("同步");
    expect(mapHttpStatusToUserMessage(404)).toContain("不存在");
    expect(mapHttpStatusToUserMessage(500)).toContain("不可用");
    expect(mapHttpStatusToUserMessage(400)).toContain("400");
  });

  it("parseFastApiDetail handles unknown object", () => {
    expect(parseFastApiDetail({ foo: 1 })).toEqual({ code: "HTTP_ERROR", message: "Request failed" });
  });

  it("ApiError carries code", () => {
    const e = new ApiError("m", "C", 400);
    expect(e.code).toBe("C");
    expect(e.httpStatus).toBe(400);
  });
});
