import { CaseDocument } from "@/lib/types";
import { documentTypeLabels } from "@/lib/documentTypeLabels";
import { CalendarDays, Tag, Gavel } from "lucide-react";

interface FullCaseViewProps {
  documents: CaseDocument[];
}

export function FullCaseView({ documents }: FullCaseViewProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-surface-0 shrink-0">
        <h1 className="text-base font-semibold text-text-primary">Celý spis</h1>
        <p className="text-xs text-text-muted mt-0.5">
          {documents.length} dokumentů · chronologický přehled
        </p>
      </div>

      {/* Documents scroll */}
      <div className="flex-1 overflow-y-auto px-6 py-5 bg-surface-1 space-y-6">
        {documents.map((doc, idx) => (
          <article
            key={doc.id}
            className="bg-surface-0 border border-border rounded panel-shadow"
          >
            {/* Document header */}
            <div className="px-5 py-3.5 border-b border-border flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-text-muted">
                    #{String(idx + 1).padStart(2, "0")}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-surface-2 text-text-muted border border-border">
                    {documentTypeLabels[doc.type] ?? doc.type}
                  </span>
                </div>
                <h2 className="text-sm font-semibold text-text-primary">
                  {doc.title}
                </h2>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="flex items-center gap-1 text-xs text-text-muted">
                  <CalendarDays className="w-3.5 h-3.5" />
                  {doc.date}
                </span>
              </div>
            </div>

            {/* Metadata strip */}
            {(doc.metadata.court || doc.metadata.caseNumber || doc.metadata.judge) && (
              <div className="px-5 py-2 bg-surface-1 border-b border-border flex items-center gap-4 flex-wrap">
                {doc.metadata.court && (
                  <span className="flex items-center gap-1 text-xs text-text-muted">
                    <Gavel className="w-3 h-3" />
                    {doc.metadata.court}
                  </span>
                )}
                {doc.metadata.caseNumber && (
                  <span className="flex items-center gap-1 text-xs text-text-muted font-mono">
                    <Tag className="w-3 h-3" />
                    {doc.metadata.caseNumber}
                  </span>
                )}
                {doc.metadata.judge && (
                  <span className="text-xs text-text-muted">
                    {doc.metadata.judge}
                  </span>
                )}
              </div>
            )}

            {/* All pages */}
            <div className="divide-y divide-surface-2">
              {doc.content.map((page, pageIdx) => (
                <div key={pageIdx} className="px-5 py-4">
                  {doc.content.length > 1 && (
                    <div className="text-xs text-text-muted font-mono mb-3">
                      Strana {pageIdx + 1}
                    </div>
                  )}
                  <pre className="text-sm text-text-primary leading-relaxed font-sans whitespace-pre-wrap">
                    {page}
                  </pre>
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
