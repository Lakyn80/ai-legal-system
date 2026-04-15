"use client";

import { Scale } from "lucide-react";

interface TopbarProps {
  caseNumber?: string;
}

export function Topbar({ caseNumber }: TopbarProps) {
  return (
    <header className="h-12 bg-surface-0 border-b border-border flex items-center px-4 gap-3 shrink-0 z-10">
      <div className="flex items-center gap-2 text-text-primary">
        <Scale className="w-4 h-4 text-accent" strokeWidth={1.8} />
        <span className="text-sm font-semibold tracking-tight">LegalDesk</span>
      </div>

      {caseNumber && (
        <>
          <div className="h-4 w-px bg-border" />
          <span className="text-xs text-text-muted font-mono">{caseNumber}</span>
        </>
      )}

      <div className="ml-auto flex items-center gap-3">
        <span className="text-xs text-text-muted">Pracovní relace</span>
        <div className="w-7 h-7 rounded-full bg-accent-light border border-accent/20 flex items-center justify-center">
          <span className="text-xs font-semibold text-accent">LK</span>
        </div>
      </div>
    </header>
  );
}
