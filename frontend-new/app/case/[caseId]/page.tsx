"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { RightPanel } from "@/components/layout/RightPanel";
import { DocumentViewer } from "@/components/document/DocumentViewer";
import { FullCaseView } from "@/components/case/FullCaseView";
import { ObjectionWorkspace } from "@/components/objection/ObjectionWorkspace";
import {
  getCaseInfo,
  getCaseTree,
  getDocument,
  getFullCase,
  startRun,
  getRunStatus,
} from "@/lib/api";
import type { CaseDocument, CaseInfo, CaseTreeNode, CenterView } from "@/lib/types";
import { BookOpen, FileQuestion, PenLine, Loader2, AlertCircle } from "lucide-react";

type LoadState =
  | { phase: "checking" }
  | { phase: "loading"; runId: string }
  | { phase: "ready" }
  | { phase: "error"; message: string };

export default function CasePage() {
  const params = useParams();
  const caseId = params.caseId as string;

  const [loadState, setLoadState] = useState<LoadState>({ phase: "checking" });
  const [caseInfo, setCaseInfo] = useState<CaseInfo | null>(null);
  const [tree, setTree] = useState<CaseTreeNode[]>([]);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [centerView, setCenterView] = useState<CenterView>({ kind: "full_case" });
  const [activeDocument, setActiveDocument] = useState<CaseDocument | null>(null);
  const [docLoading, setDocLoading] = useState(false);
  const [fullCaseDocs, setFullCaseDocs] = useState<CaseDocument[]>([]);
  const [fullCaseLoading, setFullCaseLoading] = useState(false);

  const activeDocumentId =
    centerView.kind === "document"
      ? centerView.documentId
      : centerView.kind === "full_case"
        ? "__full_case__"
        : undefined;

  // ─── Initial case load ───────────────────────────────────────────────────────

  const loadCase = useCallback(async () => {
    try {
      const info = await getCaseInfo(caseId);
      if (info.status === "ready") {
        setCaseInfo(info);
        const treeData = await getCaseTree(caseId);
        setTree(treeData);
        setLoadState({ phase: "ready" });
        return;
      }

      const run = await startRun(caseId, { mode: "load" });
      setLoadState({ phase: "loading", runId: run.runId });

      const poll = async () => {
        const status = await getRunStatus(caseId, run.runId);
        if (status.status === "completed") {
          const [updatedInfo, treeData] = await Promise.all([
            getCaseInfo(caseId),
            getCaseTree(caseId),
          ]);
          setCaseInfo(updatedInfo);
          setTree(treeData);
          setLoadState({ phase: "ready" });
        } else if (status.status === "failed") {
          setLoadState({ phase: "error", message: status.error ?? "Načtení selhalo." });
        } else {
          setTimeout(poll, 4000);
        }
      };
      setTimeout(poll, 4000);
    } catch (err) {
      setLoadState({
        phase: "error",
        message: err instanceof Error ? err.message : "Chyba při načítání.",
      });
    }
  }, [caseId]);

  useEffect(() => {
    loadCase();
  }, [loadCase]);

  // ─── Document fetch on selection ─────────────────────────────────────────────

  useEffect(() => {
    if (centerView.kind !== "document") return;
    setDocLoading(true);
    setActiveDocument(null);
    getDocument(caseId, centerView.documentId)
      .then(setActiveDocument)
      .catch(() => setActiveDocument(null))
      .finally(() => setDocLoading(false));
  }, [caseId, centerView]);

  // ─── Full-case fetch ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (centerView.kind !== "full_case" || loadState.phase !== "ready") return;
    if (fullCaseDocs.length > 0) return;
    setFullCaseLoading(true);
    getFullCase(caseId)
      .then(setFullCaseDocs)
      .catch(() => setFullCaseDocs([]))
      .finally(() => setFullCaseLoading(false));
  }, [caseId, centerView.kind, loadState.phase, fullCaseDocs.length]);

  // ─── Loading / error screens ──────────────────────────────────────────────────

  if (loadState.phase === "checking" || loadState.phase === "loading") {
    return (
      <div className="flex flex-col h-screen bg-surface-1">
        <Topbar caseNumber={caseId.slice(0, 8) + "…"} />
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <Loader2 className="w-8 h-8 text-accent animate-spin" />
          <p className="text-sm text-text-secondary font-medium">
            {loadState.phase === "checking"
              ? "Kontrola stavu spisu…"
              : "Načítám a zpracovávám spis… (30–60 s)"}
          </p>
          {loadState.phase === "loading" && (
            <p className="text-xs text-text-muted max-w-xs text-center">
              Agent rekonstruuje dokumenty z databáze a analyzuje případ. Prosím čekejte.
            </p>
          )}
        </div>
      </div>
    );
  }

  if (loadState.phase === "error") {
    return (
      <div className="flex flex-col h-screen bg-surface-1">
        <Topbar />
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <AlertCircle className="w-8 h-8 text-danger" />
          <p className="text-sm font-medium text-text-primary">Chyba při načítání spisu</p>
          <p className="text-xs text-text-muted max-w-sm text-center">{loadState.message}</p>
          <button
            onClick={() => { setLoadState({ phase: "checking" }); loadCase(); }}
            className="text-xs text-accent hover:underline"
          >
            Zkusit znovu
          </button>
        </div>
      </div>
    );
  }

  // ─── Main layout ──────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-surface-1">
      <Topbar
        caseNumber={
          caseInfo
            ? `${caseId.slice(0, 8)}… · ${caseInfo.documentCount} dok. · ${caseInfo.issueCount} problémů`
            : undefined
        }
      />

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
            if (centerView.kind !== "document") {
              const firstLeaf = findFirstLeaf(tree);
              if (firstLeaf) setCenterView({ kind: "document", documentId: firstLeaf });
            }
          }}
        />
        <ViewTab
          active={centerView.kind === "objection"}
          icon={<PenLine className="w-3.5 h-3.5" />}
          label="Analýza obrany"
          onClick={() => setCenterView({ kind: "objection" })}
        />
      </div>

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          tree={tree}
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          activeDocumentId={activeDocumentId}
          onNavigate={(view) => {
            if (view.kind === "document" || view.kind === "full_case") setCenterView(view);
          }}
        />

        <main className="flex-1 overflow-hidden flex flex-col">
          {centerView.kind === "document" && (
            docLoading ? (
              <Centered><Loader2 className="w-5 h-5 animate-spin text-accent" /></Centered>
            ) : activeDocument ? (
              <DocumentViewer document={activeDocument} />
            ) : (
              <Centered><span className="text-sm text-text-muted">Dokument nenalezen.</span></Centered>
            )
          )}

          {centerView.kind === "full_case" && (
            fullCaseLoading ? (
              <Centered><Loader2 className="w-5 h-5 animate-spin text-accent" /></Centered>
            ) : (
              <FullCaseView documents={fullCaseDocs} />
            )
          )}

          {centerView.kind === "objection" && (
            <ObjectionWorkspace caseId={caseId} />
          )}
        </main>

        <RightPanel document={activeDocument} />
      </div>
    </div>
  );
}

function findFirstLeaf(nodes: CaseTreeNode[]): string | null {
  for (const n of nodes) {
    if (n.documentId && n.documentId !== "__full_case__") return n.documentId;
    if (n.children) {
      const found = findFirstLeaf(n.children);
      if (found) return found;
    }
  }
  return null;
}

function ViewTab({
  active, icon, label, onClick,
}: { active: boolean; icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors
        ${active ? "bg-accent text-white" : "text-text-secondary hover:bg-surface-2 hover:text-text-primary"}`}
    >
      {icon}{label}
    </button>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="flex-1 flex items-center justify-center">{children}</div>;
}
