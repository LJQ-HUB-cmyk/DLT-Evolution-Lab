export class ApiError extends Error {
  readonly code: string;

  readonly httpStatus?: number;

  constructor(message: string, code: string, httpStatus?: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

export function parseFastApiDetail(detail: unknown): { code: string; message: string } {
  if (detail && typeof detail === "object" && detail !== null && "error_code" in detail) {
    const o = detail as Record<string, unknown>;
    return {
      code: String(o.error_code ?? "UNKNOWN"),
      message: String(o.message ?? o.error_code ?? "Request failed"),
    };
  }
  if (typeof detail === "string") {
    return { code: "HTTP_ERROR", message: detail };
  }
  return { code: "HTTP_ERROR", message: "Request failed" };
}

export function mapHttpStatusToUserMessage(status: number): string {
  if (status === 422) {
    return "数据不足或参数无效，请同步历史后重试。";
  }
  if (status === 404) {
    return "资源不存在（模型或期号）。";
  }
  if (status >= 500) {
    return "服务暂时不可用，请稍后重试。";
  }
  return `请求失败（${status}）`;
}
