import { API_PREFIX } from "@/lib/config";
import {
  DocumentRecord,
  JurisdictionInfo,
  SearchRequestPayload,
  SearchResultItem,
  StrategyRequestPayload,
  StrategyResult,
} from "@/types";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const message = payload.detail || payload.message || "Unexpected API error";
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export class BackendApi {
  async getJurisdictions(): Promise<JurisdictionInfo[]> {
    const response = await fetch(`${API_PREFIX}/jurisdictions`, {
      cache: "no-store",
    });
    return parseResponse<JurisdictionInfo[]>(response);
  }

  async listDocuments(): Promise<DocumentRecord[]> {
    const response = await fetch(`${API_PREFIX}/documents`, {
      cache: "no-store",
    });
    const payload = await parseResponse<{ documents: DocumentRecord[] }>(response);
    return payload.documents;
  }

  async uploadDocument(payload: {
    file: File;
    country: string;
    domain: string;
    documentType: string;
    source?: string;
    caseId?: string;
    tags?: string;
  }): Promise<DocumentRecord> {
    const formData = new FormData();
    formData.append("file", payload.file);
    formData.append("country", payload.country);
    formData.append("domain", payload.domain);
    formData.append("document_type", payload.documentType);
    if (payload.source) {
      formData.append("source", payload.source);
    }
    if (payload.caseId) {
      formData.append("case_id", payload.caseId);
    }
    if (payload.tags) {
      formData.append("tags", payload.tags);
    }

    const response = await fetch(`${API_PREFIX}/documents/upload`, {
      method: "POST",
      body: formData,
    });
    const result = await parseResponse<{ document: DocumentRecord }>(response);
    return result.document;
  }

  async ingestDocuments(documentIds: string[]): Promise<
    Array<{
      document_id: string;
      filename: string;
      status: string;
      chunk_count: number;
      error?: string | null;
    }>
  > {
    const response = await fetch(`${API_PREFIX}/documents/ingest`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        document_ids: documentIds,
      }),
    });
    const result = await parseResponse<{
      results: Array<{
        document_id: string;
        filename: string;
        status: string;
        chunk_count: number;
        error?: string | null;
      }>;
    }>(response);
    return result.results;
  }

  async search(payload: SearchRequestPayload): Promise<SearchResultItem[]> {
    const response = await fetch(`${API_PREFIX}/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const result = await parseResponse<{ results: SearchResultItem[] }>(response);
    return result.results;
  }

  async generateStrategy(payload: StrategyRequestPayload): Promise<{
    strategy: StrategyResult;
    retrieved_chunks: SearchResultItem[];
  }> {
    const response = await fetch(`${API_PREFIX}/strategy/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    return parseResponse<{
      strategy: StrategyResult;
      retrieved_chunks: SearchResultItem[];
    }>(response);
  }
}

export const backendApi = new BackendApi();
