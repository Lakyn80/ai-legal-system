"use client";

import { useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { RightPanel } from "@/components/layout/RightPanel";
import { DocumentViewer } from "@/components/document/DocumentViewer";
import { FullCaseView } from "@/components/case/FullCaseView";
import { ObjectionWorkspace } from "@/components/objection/ObjectionWorkspace";
import { caseDocuments, caseTree } from "@/lib/mockData";
import { CenterView } from "@/lib/types";
import { FileQuestion, BookOpen, PenLine } from "lucide-react";

export default function CasePage() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [centerView, setCenterView] = useState<CenterView>({ kind: "full_case" });

  const activeDocument =
    centerView.kind === "document"
      ? caseDocuments.find((d) => d.id === centerView.documentId) ?? null
      : null;

  const activeDocumentId =
    centerView.kind === "document"
      ? centerView.documentId
      : centerView.kind === "full_case"
      ? "__full_case__"
      : undefined;

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-surface-1">
      <Topbar caseNumber="12 C 45/2023" />

      {/* View mode switcher */}
      <div className="flex items-center gap-1 px-4 py-2 bg-surface-0 border-b border-border shrink-0">
        <ViewTab
          active={centerView.kind === "full_case"}
          icon={<BookOpen className="w-3.5 h-3.5" />}
          label="Celý spis"
          onClick={() => setCenterView({ kind: "full_case" })}
        />
        <ViewTab
          active={centerView.kind === "document"}
          icon={<FileQuestion className="w-3.5 h-3.5" />}
          label="Dokument"
          onClick={() => {
            const first = caseDocuments[0];
            if (first) setCenterView({ kind: "document", documentId: first.id });
          }}
        />
        <ViewTab
          active={centerView.kind === "objection"}
          icon={<PenLine className="w-3.5 h-3.5" />}
          label="Analýza obrany"
          onClick={() => setCenterView({ kind: "objection" })}
        />
      </div>

      {/* Main 3-panel layout */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          tree={caseTree}
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          activeDocumentId={activeDocumentId}
          onNavigate={(view) => {
            if (view.kind === "document") {
              setCenterView(view);
            } else if (view.kind === "full_case") {
              setCenterView({ kind: "full_case" });
            }
          }}
        />

        {/* Center panel */}
        <main className="flex-1 overflow-hidden flex flex-col">
          {centerView.kind === "document" && activeDocument && (
            <DocumentViewer document={activeDocument} />
          )}
          {centerView.kind === "document" && !activeDocument && (
            <EmptyState message="Dokument nenalezen." />
          )}
          {centerView.kind === "full_case" && (
            <FullCaseView documents={caseDocuments} />
          )}
          {centerView.kind === "objection" && <ObjectionWorkspace />}
        </main>

        <RightPanel document={activeDocument} />
      </div>
    </div>
  );
}

function ViewTab({
  active,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors
        ${
          active
            ? "bg-accent text-white"
            : "text-text-secondary hover:bg-surface-2 hover:text-text-primary"
        }
      `}
    >
      {icon}
      {label}
    </button>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex-1 flex items-center justify-center text-sm text-text-muted">
      {message}
    </div>
  );
}
