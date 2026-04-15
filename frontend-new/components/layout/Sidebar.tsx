"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { CaseTree } from "@/components/case/CaseTree";
import { CaseTreeNode, CenterView } from "@/lib/types";

interface SidebarProps {
  tree: CaseTreeNode[];
  collapsed: boolean;
  onToggle: () => void;
  activeDocumentId?: string;
  onNavigate: (view: CenterView) => void;
}

export function Sidebar({
  tree,
  collapsed,
  onToggle,
  activeDocumentId,
  onNavigate,
}: SidebarProps) {
  return (
    <aside
      className={`
        relative flex flex-col shrink-0 border-r border-border bg-surface-0
        transition-all duration-200
        ${collapsed ? "w-10" : "w-60"}
      `}
    >
      {/* Collapse toggle */}
      <button
        onClick={onToggle}
        className="absolute -right-3 top-4 z-20 w-6 h-6 rounded-full bg-surface-0 border border-border flex items-center justify-center hover:bg-surface-2 transition-colors"
        title={collapsed ? "Rozbalit panel" : "Sbalit panel"}
      >
        {collapsed ? (
          <ChevronRight className="w-3.5 h-3.5 text-text-muted" />
        ) : (
          <ChevronLeft className="w-3.5 h-3.5 text-text-muted" />
        )}
      </button>

      {!collapsed && (
        <div className="flex flex-col h-full overflow-hidden">
          <div className="px-4 py-3 border-b border-border shrink-0">
            <span className="text-xs font-semibold text-text-muted uppercase tracking-wide">
              Spis
            </span>
          </div>
          <div className="flex-1 overflow-y-auto py-2">
            <CaseTree
              nodes={tree}
              activeDocumentId={activeDocumentId}
              onNavigate={onNavigate}
            />
          </div>
        </div>
      )}

      {collapsed && (
        <div className="flex-1 flex items-start justify-center pt-4">
          <span
            className="text-xs text-text-muted"
            style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
          >
            Spis
          </span>
        </div>
      )}
    </aside>
  );
}
