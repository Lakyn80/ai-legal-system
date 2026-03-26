export type Country = "russia" | "czechia";
export type Domain = "courts" | "law";
export type DocumentStatus = "uploaded" | "ingested" | "failed";

export interface DocumentRecord {
  id: string;
  filename: string;
  path: string;
  country: Country;
  domain: Domain;
  document_type: string;
  source?: string | null;
  uploaded_at: string;
  case_id?: string | null;
  tags: string[];
  status: DocumentStatus;
  size_bytes: number;
  chunk_count: number;
  ingested_at?: string | null;
  error_message?: string | null;
}

export interface SearchResultItem {
  chunk_id: string;
  document_id: string;
  filename: string;
  country: Country;
  domain: Domain;
  jurisdiction_module: string;
  text: string;
  chunk_index: number;
  source_type: string;
  source?: string | null;
  case_id?: string | null;
  tags: string[];
  score: number;
}

export interface StrategyResult {
  jurisdiction: Country;
  domain: string;
  summary: string;
  facts: string[];
  relevant_laws: string[];
  relevant_court_positions: string[];
  arguments_for_client: string[];
  arguments_against_client: string[];
  risks: string[];
  recommended_actions: string[];
  missing_documents: string[];
  confidence: number;
}

export interface JurisdictionInfo {
  country: Country;
  label: string;
  description: string;
  supported_domains: Domain[];
}

export interface SearchRequestPayload {
  query: string;
  country?: Country;
  domain?: Domain;
  document_ids?: string[];
  case_id?: string;
  top_k: number;
}

export interface StrategyRequestPayload extends SearchRequestPayload {}
