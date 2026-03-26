import { ApiError, mapHttpStatusToUserMessage, parseFastApiDetail } from "./errors";
import type {
  AnalysisResponse,
  DrawIssue,
  IssueStatus,
  ModelsResponse,
  PredictionRun,
  SyncSummary,
} from "../types";

const envApiBase = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();
export const API_BASE = envApiBase && envApiBase.length > 0 ? envApiBase.replace(/\/+$/, "") : "http://127.0.0.1:8000/api";

const DEFAULT_TIMEOUT_MS = 12_000;

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<Response> {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(id);
  }
}

async function fetchJsonRetryGet<T>(path: string): Promise<T | null> {
  const url = `${API_BASE}${path}`;
  let lastErr: unknown;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const resp = await fetchWithTimeout(url, { method: "GET" });
      if (!resp.ok) {
        return null;
      }
      return (await resp.json()) as T;
    } catch (e) {
      lastErr = e;
      if (attempt === 0) {
        continue;
      }
    }
  }
  void lastErr;
  return null;
}

function emptyIssueStatus(): IssueStatus {
  return {
    issueCount: 0,
    modelCount: 0,
    latestSyncAt: null,
    latestIssue: null,
    logCount: 0,
    schedulerLogs: [],
    postmortems: [],
    optimizationRuns: [],
  };
}

function normalizeIssueStatus(raw: Record<string, unknown> | null): IssueStatus {
  if (!raw) {
    return emptyIssueStatus();
  }
  return {
    issueCount: Number(raw.issueCount ?? 0),
    modelCount: Number(raw.modelCount ?? 0),
    latestSyncAt: (raw.latestSyncAt as string | null) ?? null,
    latestIssue: (raw.latestIssue as string | null) ?? null,
    logCount: Number(raw.logCount ?? 0),
    schedulerLogs: Array.isArray(raw.schedulerLogs) ? (raw.schedulerLogs as IssueStatus["schedulerLogs"]) : [],
    postmortems: Array.isArray(raw.postmortems) ? (raw.postmortems as IssueStatus["postmortems"]) : [],
    optimizationRuns: Array.isArray(raw.optimizationRuns)
      ? (raw.optimizationRuns as IssueStatus["optimizationRuns"])
      : [],
  };
}

export async function fetchIssues(): Promise<DrawIssue[]> {
  const data = await fetchJsonRetryGet<{ items?: DrawIssue[] }>("/issues");
  return data?.items ?? [];
}

export async function fetchIssueStatus(): Promise<IssueStatus> {
  const raw = await fetchJsonRetryGet<Record<string, unknown>>("/issues/status");
  return normalizeIssueStatus(raw);
}

export async function fetchModels(): Promise<ModelsResponse | null> {
  return fetchJsonRetryGet<ModelsResponse>("/models");
}

export async function syncOfficialData(): Promise<SyncSummary> {
  const resp = await fetchWithTimeout(`${API_BASE}/sync`, { method: "POST" });
  if (!resp.ok) {
    let detail: unknown;
    try {
      detail = await resp.json();
    } catch {
      detail = null;
    }
    const inner = detail && typeof detail === "object" && detail !== null && "detail" in detail
      ? (detail as { detail: unknown }).detail
      : detail;
    const parsed = parseFastApiDetail(inner);
    throw new ApiError(parsed.message || mapHttpStatusToUserMessage(resp.status), parsed.code, resp.status);
  }
  return resp.json() as Promise<SyncSummary>;
}

export async function fetchRuns(limit = 50): Promise<PredictionRun[]> {
  const data = await fetchJsonRetryGet<{ items?: PredictionRun[] }>(`/runs?limit=${encodeURIComponent(String(limit))}`);
  return data?.items ?? [];
}

export async function fetchAnalysis(targetIssue: string): Promise<AnalysisResponse | null> {
  const path = `/analysis/${encodeURIComponent(targetIssue)}`;
  const data = await fetchJsonRetryGet<AnalysisResponse>(path);
  return data;
}

export async function runPredict(targetIssue: string, seed?: number): Promise<void> {
  const q = seed != null ? `?seed=${encodeURIComponent(String(seed))}` : "";
  const url = `${API_BASE}/predict/${encodeURIComponent(targetIssue)}${q}`;
  const resp = await fetchWithTimeout(url, { method: "POST" });
  if (!resp.ok) {
    let detail: unknown;
    try {
      detail = await resp.json();
    } catch {
      detail = null;
    }
    const inner = detail && typeof detail === "object" && detail !== null && "detail" in detail
      ? (detail as { detail: unknown }).detail
      : detail;
    const parsed = parseFastApiDetail(inner);
    throw new ApiError(parsed.message || mapHttpStatusToUserMessage(resp.status), parsed.code, resp.status);
  }
}

export async function runPublish(targetIssue: string, seed?: number): Promise<void> {
  const q = seed != null ? `?seed=${encodeURIComponent(String(seed))}` : "";
  const url = `${API_BASE}/publish/${encodeURIComponent(targetIssue)}${q}`;
  const resp = await fetchWithTimeout(url, { method: "POST" });
  if (!resp.ok) {
    let detail: unknown;
    try {
      detail = await resp.json();
    } catch {
      detail = null;
    }
    const inner = detail && typeof detail === "object" && detail !== null && "detail" in detail
      ? (detail as { detail: unknown }).detail
      : detail;
    const parsed = parseFastApiDetail(inner);
    throw new ApiError(parsed.message || mapHttpStatusToUserMessage(resp.status), parsed.code, resp.status);
  }
}
