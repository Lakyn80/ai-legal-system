// ─── Backend extraction output types (mirrors Python schemas) ─────────────────

export interface BackendLegalBasisRef {
  law: string;
  provision: string;
  why_applicable: string;
  legal_effect: string;
}

export interface BackendEvidenceRef {
  doc_id: string;
  page: number;
  quote: string;
}

export interface BackendDocumentItem {
  doc_id: string;
  logical_index: number;
  primary_document_id: string;
  document_type: string;
  document_date: string;
  document_role: string;
  title: string;
  is_core_document: boolean;
  source_pages: string[];
  full_text_reference: string;
  summary: string;
  key_points: string[];
  evidence_value: string;
  procedural_value: string;
}

export interface BackendDocumentGroup {
  group_id: string;
  group_name: string;
  documents: BackendDocumentItem[];
}

export interface BackendIssueItem {
  issue_id: string;
  issue_slug: string;
  issue_title: string;
  factual_basis: string[];
  supporting_doc_ids: string[];
  court_or_opponent_position: string;
  problem_description: string;
  defense_argument: string;
  legal_basis: BackendLegalBasisRef[];
  requested_consequence: string;
  evidence_gaps: string[];
  evidence_refs: BackendEvidenceRef[];
  requires_evidence: boolean;
}

export interface BackendDefenseBlock {
  defense_id: string;
  issue_id: string;
  title: string;
  argument_markdown: string;
  supporting_doc_ids: string[];
  legal_basis_refs: string[];
  evidence_refs: BackendEvidenceRef[];
}

export interface BackendExtractionOutput {
  schema_version: string;
  case_id: string;
  source_artifact: string;
  groups: BackendDocumentGroup[];
  issues: BackendIssueItem[];
  defense_blocks: BackendDefenseBlock[];
}

// ─── BFF response types (what the browser receives) ──────────────────────────

export interface CaseInfo {
  caseId: string;
  status: "ready" | "not_loaded";
  groupCount: number;
  documentCount: number;
  issueCount: number;
}

export interface CaseTreeNode {
  id: string;
  label: string;
  documentId?: string;
  children?: CaseTreeNode[];
}

export interface CaseDocument {
  id: string;
  title: string;
  type: string;
  date: string;
  pageCount: number;
  /** Each item is one rendered page */
  content: string[];
  metadata: {
    court?: string;
    judge?: string;
    caseNumber?: string;
    parties?: string;
    filed?: string;
    groupName?: string;
    role?: string;
  };
}

// ─── Legal agent run ──────────────────────────────────────────────────────────

export type RunMode = "load" | "analyze";
export type RunStatus = "running" | "completed" | "failed";

export interface AgentRun {
  runId: string;
  caseId: string;
  mode: RunMode;
  status: RunStatus;
  createdAt: string;
  completedAt?: string;
  error?: string;
}

export interface AnalysisOutput {
  runId: string;
  caseId: string;
  issueSummary: string;
  legalOptions: string[];
  applicableLaws: string[];
  risks: string[];
  nextSteps: string[];
  defenseBlocks: BackendDefenseBlock[];
}

// ─── UI state ─────────────────────────────────────────────────────────────────

export type CenterView =
  | { kind: "document"; documentId: string }
  | { kind: "full_case" }
  | { kind: "objection" };
