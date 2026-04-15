// ─── Document types ──────────────────────────────────────────────────────────

export type DocumentType =
  | "judgment"
  | "appeal"
  | "petition"
  | "evidence"
  | "objection"
  | "motion"
  | "order"
  | "testimony"
  | "contract"
  | "correspondence";

export interface CaseDocument {
  id: string;
  title: string;
  type: DocumentType;
  date: string;
  pageCount: number;
  /** Array of page text — each item is one page */
  content: string[];
  metadata: {
    court?: string;
    judge?: string;
    caseNumber?: string;
    parties?: string;
    filed?: string;
  };
}

// ─── Case tree ───────────────────────────────────────────────────────────────

export interface CaseTreeNode {
  id: string;
  label: string;
  children?: CaseTreeNode[];
  /** "__full_case__" for full-case view, else a CaseDocument.id */
  documentId?: string;
  icon?: string;
}

// ─── UI state ────────────────────────────────────────────────────────────────

export type CenterView =
  | { kind: "document"; documentId: string }
  | { kind: "full_case" }
  | { kind: "objection" };

// ─── Analysis output (placeholder) ──────────────────────────────────────────

export interface AnalysisOutput {
  issueSummary: string;
  legalOptions: string[];
  applicableLaws: string[];
  risks: string[];
  nextSteps: string[];
}
