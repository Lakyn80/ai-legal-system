/**
 * Browser-side typed API client.
 * Calls Next.js BFF route handlers — never calls the backend directly.
 */

import type {
  AgentRun,
  AnalysisOutput,
  CaseDocument,
  CaseInfo,
  CaseTreeNode,
  RunMode,
} from "./types";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(input, { ...init, cache: "no-store" });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.error) message = body.error;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

// ─── Cases ────────────────────────────────────────────────────────────────────

export function getCaseInfo(caseId: string): Promise<CaseInfo> {
  return apiFetch(`/api/cases/${caseId}`);
}

export function getCaseTree(caseId: string): Promise<CaseTreeNode[]> {
  return apiFetch(`/api/cases/${caseId}/tree`);
}

export function getDocument(
  caseId: string,
  documentId: string,
): Promise<CaseDocument> {
  return apiFetch(`/api/cases/${caseId}/documents/${documentId}`);
}

export function getFullCase(caseId: string): Promise<CaseDocument[]> {
  return apiFetch(`/api/cases/${caseId}/full-case`);
}

// ─── Legal agent ──────────────────────────────────────────────────────────────

export function startRun(
  caseId: string,
  payload: {
    userInput?: string;
    mode?: RunMode;
    facts?: string[];
    issueFlags?: string[];
  },
): Promise<AgentRun> {
  return apiFetch(`/api/cases/${caseId}/legal-agent/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getRunStatus(caseId: string, runId: string): Promise<AgentRun> {
  return apiFetch(`/api/cases/${caseId}/legal-agent/${runId}`);
}

export function getRunResult(
  caseId: string,
  runId: string,
): Promise<AnalysisOutput> {
  return apiFetch(`/api/cases/${caseId}/legal-agent/${runId}/result`);
}

// ─── Polling helper ───────────────────────────────────────────────────────────

/**
 * Polls run status until completed or failed, then returns the result.
 * onStatusChange is called each poll tick so the UI can show progress.
 */
export async function pollRunUntilDone(
  caseId: string,
  runId: string,
  opts: {
    intervalMs?: number;
    timeoutMs?: number;
    onStatusChange?: (status: AgentRun) => void;
  } = {},
): Promise<AnalysisOutput> {
  const { intervalMs = 3000, timeoutMs = 180_000, onStatusChange } = opts;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const run = await getRunStatus(caseId, runId);
    onStatusChange?.(run);

    if (run.status === "completed") {
      return getRunResult(caseId, runId);
    }
    if (run.status === "failed") {
      throw new ApiError(500, run.error ?? "Run failed");
    }

    await new Promise((r) => setTimeout(r, intervalMs));
  }

  throw new ApiError(408, "Analysis timed out");
}

export { ApiError };
