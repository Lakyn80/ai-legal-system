"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmationModal } from "./ConfirmationModal";
import { startRun, pollRunUntilDone, ApiError } from "@/lib/api";
import type { AnalysisOutput } from "@/lib/types";
import {
  FileText,
  FolderOpen,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  AlertCircle,
  Scale,
  ListOrdered,
  ShieldAlert,
  Loader2,
} from "lucide-react";

type ContextScope = "current_document" | "full_case";

interface ObjectionWorkspaceProps {
  caseId: string;
}

export function ObjectionWorkspace({ caseId }: ObjectionWorkspaceProps) {
  const [text, setText] = useState("");
  const [scope, setScope] = useState<ContextScope>("full_case");
  const [modalOpen, setModalOpen] = useState(false);
  const [output, setOutput] = useState<AnalysisOutput | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState("Analyzuji…");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit() {
    if (!text.trim()) return;
    setModalOpen(true);
  }

  async function handleConfirm() {
    setModalOpen(false);
    setLoading(true);
    setError(null);
    setOutput(null);
    setLoadingMessage("Spouštím analýzu…");

    try {
      const run = await startRun(caseId, {
        mode: "analyze",
        userInput: text.trim(),
      });

      setLoadingMessage("Agent analyzuje případ… (30–60 s)");

      const result = await pollRunUntilDone(caseId, run.runId, {
        intervalMs: 4000,
        timeoutMs: 180_000,
        onStatusChange: (status) => {
          if (status.status === "running") {
            setLoadingMessage("Agent zpracovává dokumenty a připravuje obrannou strategii…");
          }
        },
      });

      setOutput(result);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Neznámá chyba";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-4 border-b border-border bg-surface-0 shrink-0">
        <h1 className="text-base font-semibold text-text-primary">Obranná analýza</h1>
        <p className="text-xs text-text-muted mt-0.5">
          Popište, co chcete napadnout nebo obhájit. Agent analyzuje dokumenty a připraví právní strategii.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4 bg-surface-1">
        {/* Input area */}
        <div className="bg-surface-0 border border-border rounded panel-shadow p-4 space-y-3">
          <label className="block text-xs font-medium text-text-secondary">
            Popis problému / otázky
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Popiste, co chcete napadnout nebo obhajit -- napr. Soud neprihlédl k legislativni zmene. Chci zpochybnit vysi priznane skody."
            rows={6}
            disabled={loading}
            className="w-full resize-none rounded border border-border bg-surface-1 px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent transition-colors disabled:opacity-50"
          />

          <div className="flex items-center gap-1.5">
            <span className="text-xs text-text-muted mr-1">Kontext:</span>
            <ContextToggle
              active={scope === "current_document"}
              icon={<FileText className="w-3.5 h-3.5" />}
              label="Aktuální dokument"
              onClick={() => setScope("current_document")}
            />
            <ContextToggle
              active={scope === "full_case"}
              icon={<FolderOpen className="w-3.5 h-3.5" />}
              label="Celý spis"
              onClick={() => setScope("full_case")}
            />
          </div>

          <div className="flex justify-end pt-1">
            <Button
              variant="primary"
              size="lg"
              onClick={handleSubmit}
              disabled={!text.trim() || loading}
            >
              {loading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  {loadingMessage}
                </>
              ) : (
                "Připravit právní analýzu"
              )}
            </Button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-danger-light border border-danger/20 rounded p-4 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-danger shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-danger">Analýza selhala</p>
              <p className="text-xs text-text-secondary mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Loading spinner */}
        {loading && (
          <div className="bg-surface-0 border border-border rounded panel-shadow p-5">
            <div className="flex items-center gap-3">
              <Loader2 className="w-4 h-4 text-accent animate-spin shrink-0" />
              <span className="text-sm text-text-muted">{loadingMessage}</span>
            </div>
          </div>
        )}

        {/* Output */}
        {output && !loading && <AnalysisOutputPanel output={output} />}
      </div>

      <ConfirmationModal
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onConfirm={handleConfirm}
      />
    </div>
  );
}

// ─── Context toggle ───────────────────────────────────────────────────────────

function ContextToggle({
  active, icon, label, onClick,
}: { active: boolean; icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded border text-xs font-medium transition-colors
        ${active
          ? "bg-accent-light border-accent/30 text-accent"
          : "bg-surface-0 border-border text-text-secondary hover:bg-surface-2"}`}
    >
      {icon}{label}
    </button>
  );
}

// ─── Analysis output ──────────────────────────────────────────────────────────

function AnalysisOutputPanel({ output }: { output: AnalysisOutput }) {
  return (
    <div className="bg-surface-0 border border-border rounded panel-shadow divide-y divide-border">
      <OutputSection
        icon={<Scale className="w-4 h-4 text-accent" />}
        title="Shrnutí problematiky"
        defaultOpen
      >
        <p className="text-sm text-text-primary leading-relaxed">{output.issueSummary}</p>
      </OutputSection>

      <OutputSection
        icon={<ListOrdered className="w-4 h-4 text-accent" />}
        title="Právní možnosti"
        defaultOpen
      >
        {output.legalOptions.length === 0 ? (
          <p className="text-sm text-text-muted">Žádné právní možnosti nebyly identifikovány.</p>
        ) : (
          <ul className="space-y-1.5">
            {output.legalOptions.map((opt, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-primary">
                <CheckCircle2 className="w-3.5 h-3.5 text-success mt-0.5 shrink-0" />
                {opt}
              </li>
            ))}
          </ul>
        )}
      </OutputSection>

      <OutputSection
        icon={<FileText className="w-4 h-4 text-accent" />}
        title="Aplikovatelné právní předpisy"
      >
        {output.applicableLaws.length === 0 ? (
          <p className="text-sm text-text-muted">Žádné konkrétní předpisy nebyly identifikovány.</p>
        ) : (
          <ul className="space-y-1.5">
            {output.applicableLaws.map((law, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-secondary font-mono text-xs">
                <span className="text-text-muted">—</span>{law}
              </li>
            ))}
          </ul>
        )}
      </OutputSection>

      {output.risks.length > 0 && (
        <OutputSection
          icon={<ShieldAlert className="w-4 h-4 text-amber-500" />}
          title="Rizika a slabiny"
        >
          <ul className="space-y-1.5">
            {output.risks.map((risk, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-text-primary">
                <AlertCircle className="w-3.5 h-3.5 text-amber-500 mt-0.5 shrink-0" />
                {risk}
              </li>
            ))}
          </ul>
        </OutputSection>
      )}

      {output.nextSteps.length > 0 && (
        <OutputSection
          icon={<ListOrdered className="w-4 h-4 text-accent" />}
          title="Doporučené kroky"
          defaultOpen
        >
          <ol className="space-y-1.5 list-decimal list-inside">
            {output.nextSteps.map((step, i) => (
              <li key={i} className="text-sm text-text-primary leading-relaxed">{step}</li>
            ))}
          </ol>
        </OutputSection>
      )}

      {output.defenseBlocks.length > 0 && (
        <OutputSection
          icon={<Scale className="w-4 h-4 text-accent" />}
          title={`Detailní obranné argumenty (${output.defenseBlocks.length})`}
        >
          <div className="space-y-4">
            {output.defenseBlocks.map((block, i) => (
              <div key={i} className="border border-border rounded p-3 bg-surface-1">
                <p className="text-xs font-semibold text-text-secondary mb-2">{block.title || `Argument ${i + 1}`}</p>
                <pre className="text-xs text-text-primary whitespace-pre-wrap font-sans leading-relaxed">
                  {block.argument_markdown}
                </pre>
                {block.legal_basis_refs.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {block.legal_basis_refs.map((ref, j) => (
                      <span key={j} className="text-xs px-1.5 py-0.5 bg-accent-light text-accent rounded border border-accent/20 font-mono">
                        {ref}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </OutputSection>
      )}
    </div>
  );
}

function OutputSection({
  icon, title, children, defaultOpen = false,
}: { icon: React.ReactNode; title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-surface-1 transition-colors text-left"
      >
        {icon}
        <span className="text-sm font-semibold text-text-primary flex-1">{title}</span>
        {open ? <ChevronDown className="w-4 h-4 text-text-muted" /> : <ChevronRight className="w-4 h-4 text-text-muted" />}
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
}
