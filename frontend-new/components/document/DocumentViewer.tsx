"use client";

import { useState } from "react";
import { CaseDocument } from "@/lib/types";
import { documentTypeLabels } from "@/lib/documentTypeLabels";
import { PageNavigation } from "./PageNavigation";
import { CalendarDays, Tag } from "lucide-react";

interface DocumentViewerProps {
  document: CaseDocument;
}

export function DocumentViewer({ document }: DocumentViewerProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const pageIndex = currentPage - 1;
  const pageText = document.content[pageIndex] ?? "";

  return (
    <div className="flex flex-col h-full">
      {/* Document header */}
      <div className="px-6 py-4 border-b border-border bg-surface-0 shrink-0">
        <h1 className="text-base font-semibold text-text-primary mb-2">
          {document.title}
        </h1>
        <div className="flex items-center gap-4 flex-wrap">
          <span className="flex items-center gap-1.5 text-xs text-text-muted">
            <Tag className="w-3.5 h-3.5" />
            {documentTypeLabels[document.type] ?? document.type}
          </span>
          <span className="flex items-center gap-1.5 text-xs text-text-muted">
            <CalendarDays className="w-3.5 h-3.5" />
            {document.date}
          </span>
          {document.metadata.caseNumber && (
            <span className="text-xs text-text-muted font-mono">
              sp. zn. {document.metadata.caseNumber}
            </span>
          )}
        </div>
      </div>

      {/* Page content */}
      <div className="flex-1 overflow-y-auto px-6 py-5 bg-surface-1">
        <div className="max-w-3xl mx-auto">
          <div className="bg-surface-0 border border-border rounded p-6 panel-shadow min-h-64">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-surface-2">
              <span className="text-xs text-text-muted font-mono">
                Strana {currentPage} / {document.pageCount}
              </span>
            </div>
            <pre className="text-sm text-text-primary leading-relaxed font-sans whitespace-pre-wrap">
              {pageText}
            </pre>
          </div>
        </div>
      </div>

      {/* Page navigation */}
      {document.pageCount > 1 && (
        <div className="px-6 py-3 border-t border-border bg-surface-0 shrink-0">
          <PageNavigation
            pageCount={document.pageCount}
            currentPage={currentPage}
            onPageChange={setCurrentPage}
          />
        </div>
      )}
    </div>
  );
}
