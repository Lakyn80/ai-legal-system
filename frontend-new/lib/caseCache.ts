/**
 * In-memory cache for extraction results keyed by case_id.
 * Populated when a 'load' run completes; used by GET /api/cases/[caseId]/...
 */

import type { BackendExtractionOutput } from "./types";

declare global {
  // eslint-disable-next-line no-var
  var __caseCache: Map<string, BackendExtractionOutput> | undefined;
}

const cache: Map<string, BackendExtractionOutput> =
  globalThis.__caseCache ?? (globalThis.__caseCache = new Map());

export const caseCache = {
  set(caseId: string, output: BackendExtractionOutput): void {
    cache.set(caseId, output);
  },

  get(caseId: string): BackendExtractionOutput | undefined {
    return cache.get(caseId);
  },

  has(caseId: string): boolean {
    return cache.has(caseId);
  },
};
