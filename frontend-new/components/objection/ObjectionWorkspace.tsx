"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmationModal } from "./ConfirmationModal";
import { AnalysisOutput } from "@/lib/types";
import { mockAnalysisOutput } from "@/lib/mockData";
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
} from "lucide-react";

type ContextScope = "current_document" | "full_case";

export function ObjectionWorkspace() {
  const [text, setText] = useState("");
  const [scope, setScope] = useState<ContextScope>("full_case");
  const [modalOpen, setModalOpen] = useState(false);
  const [output, setOutput] = useState<AnalysisOutput | null>(null);
  const [loading, setLoading] = useState(false);

  function handleSubmit() {
    if (!text.trim()) return;
    setModalOpen(true);
  }

  function handleConfirm() {
    setModalOpen(false);
    setLoading(true);
    // Simulate async analysis
    setTimeout(() => {
      setOutput(mockAnalysisOutput);
      setLoading(false);
    }, 1800);
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-border bg-surface-0 shrink-0">
        <h1 className="text-base font-semibold text-text-primary">Obranná analýza</h1>
        <p className="text-xs text-text-muted mt-0.5">
          Popište, co chcete napadnout nebo obhájit.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4 bg-surface-1">
        {/* Input area */}
        <div className="bg-surface-0 border border-border rounded panel-shadow p-4 space-y-3">
          <label className="block text-xs font-medium text-text-secondary mb-1">
            Popis problému / otázky
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Popiste, co chcete napadnout nebo obhajit -- napr. Soud neprihlédl k legislativni zmene. Chci zpochybnit vysi priznane skody."
            rows={6}
            className="w-full resize-none rounded border border-border bg-surface-1 px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent transition-colors"
          />

          {/* Context toggles */}
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
              {loading ? "Analyzuji…" : "Připravit právní analýzu"}
            </Button>
          </div>
        </div>

        {/* Output placeholder or result */}
        {(loading || output) && (
          <AnalysisOutputPanel output={output} loading={loading} />
        )}
      </div>

      <ConfirmationModal
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onConfirm={handleConfirm}
      />
    </div>
  );
}

// ─── Context toggle button ────────────────────────────────────────────────────

function ContextToggle({
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
        flex items-center gap-1.5 px-2.5 py-1.5 rounded border text-xs font-medium transition-colors
        ${
          active
            ? "bg-accent-light border-accent/30 text-accent"
            : "bg-surface-0 border-border text-text-secondary hover:bg-surface-2"
        }
      `}
    >
      {icon}
      {label}
    </button>
  );
}

// ─── Analysis output panel ────────────────────────────────────────────────────

function AnalysisOutputPanel({
  output,
  loading,
}: {
  output: AnalysisOutput | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="bg-surface-0 border border-border rounded panel-shadow p-5">
        <div className="flex items-center gap-3">
          <div className="w-4 h-4 rounded-full border-2 border-accent border-t-transparent animate-spin" />
          <span className="text-sm text-text-muted">Agent analyzuje případ…</span>
        </div>
      </div>
    );
  }

  if (!output) return null;

  return (
    <div className="bg-surface-0 border border-border rounded panel-shadow divide-y divide-border">
      <OutputSection
        icon={<Scale className="w-4 h-4 text-accent" />}
        title="Shrnutí problematiky"
      >
        <p className="text-sm text-text-primary leading-relaxed">{output.issueSummary}</p>
      </OutputSection>

      <OutputSection
        icon={<ListOrdered className="w-4 h-4 text-accent" />}
        title="Právní možnosti"
        defaultOpen
      >
        <ul className="space-y-1.5">
          {output.legalOptions.map((opt, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-text-primary">
              <CheckCircle2 className="w-3.5 h-3.5 text-success mt-0.5 shrink-0" />
              {opt}
            </li>
          ))}
        </ul>
      </OutputSection>

      <OutputSection
        icon={<FileText className="w-4 h-4 text-accent" />}
        title="Aplikovatelné právní předpisy"
      >
        <ul className="space-y-1.5">
          {output.applicableLaws.map((law, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-text-secondary font-mono">
              <span className="text-text-muted">—</span>
              {law}
            </li>
          ))}
        </ul>
      </OutputSection>

      <OutputSection
        icon={<ShieldAlert className="w-4 h-4 text-amber-500" />}
        title="Rizika"
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

      <OutputSection
        icon={<ListOrdered className="w-4 h-4 text-accent" />}
        title="Doporučené kroky"
        defaultOpen
      >
        <ol className="space-y-1.5 list-decimal list-inside">
          {output.nextSteps.map((step, i) => (
            <li key={i} className="text-sm text-text-primary leading-relaxed">
              {step}
            </li>
          ))}
        </ol>
      </OutputSection>
    </div>
  );
}

function OutputSection({
  icon,
  title,
  children,
  defaultOpen = false,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 hover:bg-surface-1 transition-colors text-left"
      >
        {icon}
        <span className="text-sm font-semibold text-text-primary flex-1">{title}</span>
        {open ? (
          <ChevronDown className="w-4 h-4 text-text-muted" />
        ) : (
          <ChevronRight className="w-4 h-4 text-text-muted" />
        )}
      </button>
      {open && <div className="px-4 pb-4 pt-0">{children}</div>}
    </div>
  );
}
