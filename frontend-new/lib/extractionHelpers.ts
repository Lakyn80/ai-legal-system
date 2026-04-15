/**
 * Helpers to transform BackendExtractionOutput into BFF response shapes.
 */

import type {
  BackendDocumentItem,
  BackendExtractionOutput,
  CaseDocument,
  CaseInfo,
  CaseTreeNode,
} from "./types";

const GROUP_LABELS: Record<string, string> = {
  judgments: "Rozhodnutí",
  appeals: "Odvolání",
  claims: "Návrhy / Žaloby",
  party_submissions: "Podání stran",
  orders: "Usnesení",
  evidence: "Důkazy",
  procedural_documents: "Procesní dokumenty",
  translations: "Překlady",
  service_documents: "Doručovací dokumenty",
  other_relevant_documents: "Ostatní",
};

function extractDecisionMarker(text: string): string {
  const low = normalizeWs(text).toLowerCase();
  if (low.includes("определение")) return "opredelenie";
  if (low.includes("решение")) return "reshenie";
  if (low.includes("постановление")) return "postanovlenie";
  if (low.includes("апелляц")) return "appeal";
  return "generic";
}

const DOC_TYPE_LABELS: Record<string, string> = {
  judgment: "Rozhodnutí",
  appeal: "Odvolání",
  claim: "Žaloba",
  party_submission: "Podání",
  order: "Usnesení",
  evidence: "Důkaz",
  procedural_document: "Procesní dokument",
  translation: "Překlad",
  service_document: "Doručení",
  other_relevant_document: "Dokument",
};

function normalizeWs(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function isGenericDocumentTitle(title: string): boolean {
  return /^dokument\s+\d+$/i.test(title.trim());
}

function inferTitleFromSummary(summary: string): string | null {
  const lines = summary
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (!lines.length) return null;
  const line =
    lines.find((l) => /^((определение|решение|постановление|приговор)\b)/i.test(l))
    ?? lines[0];
  const cleaned = normalizeWs(line);
  const hasLetters = /[A-Za-zА-Яа-яЁё]/.test(cleaned);
  if (!hasLetters || cleaned.length < 6) return null;
  return cleaned.length > 120 ? `${cleaned.slice(0, 117)}...` : cleaned;
}

function extractCaseNumber(text: string): string | null {
  const m = text.match(/дело\s*№\s*([^\n,;]+)/i);
  if (!m) return null;
  return normalizeWs(m[1]).slice(0, 60);
}

function extractCaseNumberFromTitle(title: string): string | null {
  const m = title.match(/[čч]\.j\.\s*([A-Za-zА-Яа-я0-9\-/]+)/i);
  if (m) return normalizeWs(m[1]);
  const m2 = title.match(/дело\s*№\s*([A-Za-zА-Яа-я0-9\-/]+)/i);
  if (m2) return normalizeWs(m2[1]);
  return null;
}

function buildDisplayTitle(doc: BackendDocumentItem): string {
  const summary = doc.summary?.trim() ?? "";
  const rawTitle = doc.title?.trim() || `Dokument ${doc.logical_index}`;
  const fallbackType = DOC_TYPE_LABELS[doc.document_type || ""] ?? "Dokument";
  const fallbackTitle = `${fallbackType} #${doc.logical_index}`;
  const baseTitle =
    isGenericDocumentTitle(rawTitle) && summary
      ? inferTitleFromSummary(summary) ?? fallbackTitle
      : rawTitle;
  const caseNo = summary ? extractCaseNumber(summary) : null;
  const withCaseNo =
    caseNo && !baseTitle.toLowerCase().includes(caseNo.toLowerCase())
      ? `${baseTitle} · č.j. ${caseNo}`
      : baseTitle;
  if (doc.document_date?.trim()) {
    return `${withCaseNo} (${doc.document_date.trim()})`;
  }
  return withCaseNo;
}

function looksLikeBadTitle(title: string): boolean {
  const t = normalizeWs(title);
  if (t.length < 5) return true;
  if (/^\d+$/.test(t)) return true;
  if (!/[A-Za-zА-Яа-яЁё]/.test(t)) return true;
  return false;
}

function buildGroupBucketLabel(doc: BackendDocumentItem): string {
  const title = buildDisplayTitle(doc);
  const byTitle = extractCaseNumberFromTitle(title);
  if (byTitle) return `Č.j. ${byTitle}`;
  if (doc.document_date?.trim()) return `Bez č.j. (${doc.document_date.trim()})`;
  return "Bez č.j.";
}

function mergeKeyForDoc(doc: BackendDocumentItem): string {
  const normalizedType = (doc.document_type || "").trim().toLowerCase();
  const date = normalizeWs(doc.document_date || "");
  const title = buildDisplayTitle(doc);
  const summary = normalizeWs(doc.summary || "");
  const caseNo =
    extractCaseNumberFromTitle(title) ??
    extractCaseNumber(summary) ??
    "";

  const shouldMerge =
    normalizedType === "judgment" ||
    normalizedType === "appeal" ||
    normalizedType === "order";
  if (!shouldMerge) {
    return `doc:${doc.doc_id}`;
  }
  const marker = extractDecisionMarker(`${title}\n${summary}`);
  return `merge:${normalizedType}|${caseNo}|${date}|${marker}`;
}

function mergeDocs(docs: BackendDocumentItem[]): BackendDocumentItem[] {
  const sorted = [...docs].sort((a, b) => a.logical_index - b.logical_index);
  const buckets = new Map<string, BackendDocumentItem[]>();
  for (const d of sorted) {
    const key = mergeKeyForDoc(d);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key)!.push(d);
  }

  const merged: BackendDocumentItem[] = [];
  let syntheticCounter = 0;
  for (const [key, items] of buckets.entries()) {
    if (!key.startsWith("merge:") || items.length === 1) {
      merged.push(items[0]);
      continue;
    }
    const first = items[0];
    const sourcePages = [...new Set(items.flatMap((x) => x.source_pages || []))];
    const keyPoints = [...new Set(items.flatMap((x) => x.key_points || []).map((x) => x.trim()).filter(Boolean))];
    const summaries = items.map((x) => normalizeWs(x.summary || "")).filter(Boolean);
    const summary = summaries.join("\n\n");
    const evidenceValue = items.map((x) => normalizeWs(x.evidence_value || "")).filter(Boolean).join("\n\n");
    const proceduralValue = items.map((x) => normalizeWs(x.procedural_value || "")).filter(Boolean).join("\n\n");
    syntheticCounter += 1;
    merged.push({
      ...first,
      doc_id: `${first.doc_id}::merged::${syntheticCounter}`,
      source_pages: sourcePages,
      key_points: keyPoints,
      summary,
      evidence_value: evidenceValue,
      procedural_value: proceduralValue,
      logical_index: Math.min(...items.map((x) => x.logical_index)),
    });
  }
  merged.sort((a, b) => a.logical_index - b.logical_index);
  return merged;
}

function splitIntoPages(text: string, targetPages: number): string[] {
  const clean = text.trim();
  if (!clean) return ["Obsah není k dispozici."];
  if (targetPages <= 1) return [clean];

  const paragraphs = clean.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  if (!paragraphs.length) return [clean];

  const totalChars = paragraphs.reduce((sum, p) => sum + p.length, 0);
  const idealPageChars = Math.max(1, Math.floor(totalChars / targetPages));

  const pages: string[] = [];
  let current: string[] = [];
  let currentChars = 0;

  for (const paragraph of paragraphs) {
    const nextChars = currentChars + paragraph.length;
    const shouldFlush = pages.length < targetPages - 1 && current.length > 0 && nextChars > idealPageChars;
    if (shouldFlush) {
      pages.push(current.join("\n\n"));
      current = [];
      currentChars = 0;
    }
    current.push(paragraph);
    currentChars += paragraph.length;
  }
  if (current.length) pages.push(current.join("\n\n"));
  return pages;
}

/** Build the case tree from groups */
export function buildTree(output: BackendExtractionOutput): CaseTreeNode[] {
  const root: CaseTreeNode = {
    id: `case::${output.case_id}`,
    label: `Spis ${output.case_id.slice(0, 8)}…`,
    children: [
      {
        id: `case::${output.case_id}::full`,
        label: "Celý spis",
        documentId: "__full_case__",
      },
    ],
  };

  for (const group of output.groups) {
    if (group.documents.length === 0) continue;
    const docs = mergeDocs(group.documents);
    const shouldBucket =
      group.group_name === "judgments" ||
      group.group_name === "appeals" ||
      group.group_name === "orders";
    let children: CaseTreeNode[];
    if (shouldBucket) {
      const buckets = new Map<string, CaseTreeNode[]>();
      for (const doc of docs) {
        const label = buildGroupBucketLabel(doc);
        const title = buildDisplayTitle(doc);
        const fixedTitle = looksLikeBadTitle(title) ? `${DOC_TYPE_LABELS[doc.document_type] ?? "Dokument"} #${doc.logical_index}` : title;
        const node: CaseTreeNode = {
          id: doc.doc_id,
          label: fixedTitle,
          documentId: doc.doc_id,
        };
        if (!buckets.has(label)) buckets.set(label, []);
        buckets.get(label)!.push(node);
      }
      children = [...buckets.entries()].map(([label, bucketNodes]) => ({
        id: `${group.group_id}::bucket::${label}`,
        label,
        children: bucketNodes,
      }));
    } else {
      children = docs.map((doc) => ({
        id: doc.doc_id,
        label: buildDisplayTitle(doc),
        documentId: doc.doc_id,
      }));
    }
    const groupNode: CaseTreeNode = {
      id: group.group_id,
      label: GROUP_LABELS[group.group_name] ?? group.group_name,
      children,
    };
    root.children!.push(groupNode);
  }

  return [root];
}

/** Build paginated content from a DocumentItem */
function buildPages(doc: BackendDocumentItem): string[] {
  const summary = doc.summary?.trim() ?? "";
  const sourcePageCount = Math.max(1, doc.source_pages?.length ?? 1);
  if (summary) {
    return splitIntoPages(summary, sourcePageCount);
  }
  const uniquePoints = [...new Set((doc.key_points ?? []).map((x) => x.trim()).filter(Boolean))];
  if (uniquePoints.length) {
    return uniquePoints.map((x) => `• ${x}`);
  }
  return ["Obsah není k dispozici."];
}

/** Map a BackendDocumentItem to a CaseDocument */
export function mapDocument(
  doc: BackendDocumentItem,
  groupName: string,
): CaseDocument {
  const pages = buildPages(doc);
  return {
    id: doc.doc_id,
    title: buildDisplayTitle(doc),
    type: doc.document_type || "other_relevant_document",
    date: doc.document_date || "",
    pageCount: pages.length,
    content: pages,
    metadata: {
      groupName: GROUP_LABELS[groupName] ?? groupName,
      role: doc.document_role || undefined,
    },
  };
}

/** Get all CaseDocuments from an extraction output */
export function allDocuments(output: BackendExtractionOutput): CaseDocument[] {
  const docs: CaseDocument[] = [];
  const seen = new Set<string>();
  for (const g of output.groups) {
    const sorted = mergeDocs(g.documents);
    for (const d of sorted) {
      if (seen.has(d.doc_id)) continue;
      seen.add(d.doc_id);
      docs.push(mapDocument(d, g.group_name));
    }
  }
  docs.sort((a, b) => a.id.localeCompare(b.id));
  return docs;
}

/** Find a single document by doc_id */
export function findDocument(
  output: BackendExtractionOutput,
  docId: string,
): CaseDocument | null {
  for (const g of output.groups) {
    const d = mergeDocs(g.documents).find((d) => d.doc_id === docId);
    if (d) return mapDocument(d, g.group_name);
  }
  return null;
}

/** Build CaseInfo summary */
export function buildCaseInfo(
  caseId: string,
  output: BackendExtractionOutput,
): CaseInfo {
  const documentCount = output.groups.reduce((n, g) => n + g.documents.length, 0);
  return {
    caseId,
    status: "ready",
    groupCount: output.groups.length,
    documentCount,
    issueCount: output.issues.length,
  };
}
