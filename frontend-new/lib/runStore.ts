/**
 * In-memory store for agent run states.
 * Lives in the Next.js server process — persists across requests within the same instance.
 * For multi-instance deployments, replace with Redis.
 */

import type { BackendExtractionOutput, RunMode, RunStatus } from "./types";

export interface RunRecord {
  runId: string;
  caseId: string;
  mode: RunMode;
  status: RunStatus;
  createdAt: Date;
  completedAt?: Date;
  output?: BackendExtractionOutput;
  error?: string;
}

// Module-level singleton (survives hot-reload in dev via globalThis)
declare global {
  // eslint-disable-next-line no-var
  var __runStore: Map<string, RunRecord> | undefined;
}

const store: Map<string, RunRecord> =
  globalThis.__runStore ?? (globalThis.__runStore = new Map());

export const runStore = {
  set(record: RunRecord): void {
    store.set(record.runId, record);
  },

  get(runId: string): RunRecord | undefined {
    return store.get(runId);
  },

  update(runId: string, patch: Partial<RunRecord>): void {
    const existing = store.get(runId);
    if (existing) store.set(runId, { ...existing, ...patch });
  },

  listByCase(caseId: string): RunRecord[] {
    return [...store.values()].filter((r) => r.caseId === caseId);
  },
};
