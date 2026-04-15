"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  Folder,
  Gavel,
  ScrollText,
  BookOpen,
  AlertCircle,
  ClipboardList,
} from "lucide-react";
import { CaseTreeNode, CenterView } from "@/lib/types";
import { clsx } from "clsx";

interface CaseTreeProps {
  nodes: CaseTreeNode[];
  activeDocumentId?: string;
  onNavigate: (view: CenterView) => void;
}

const groupIconMap: Record<string, React.ReactNode> = {
  "court-decisions": <Gavel className="w-3.5 h-3.5 shrink-0" />,
  appeals: <ScrollText className="w-3.5 h-3.5 shrink-0" />,
  contracts: <BookOpen className="w-3.5 h-3.5 shrink-0" />,
  evidence: <ClipboardList className="w-3.5 h-3.5 shrink-0" />,
  objections: <AlertCircle className="w-3.5 h-3.5 shrink-0" />,
  "full-case": <FileText className="w-3.5 h-3.5 shrink-0" />,
};

interface TreeNodeProps {
  node: CaseTreeNode;
  depth: number;
  activeDocumentId?: string;
  onNavigate: (view: CenterView) => void;
  defaultOpen?: boolean;
}

function TreeNode({
  node,
  depth,
  activeDocumentId,
  onNavigate,
  defaultOpen = false,
}: TreeNodeProps) {
  const [open, setOpen] = useState(defaultOpen);
  const hasChildren = node.children && node.children.length > 0;
  const isLeaf = !hasChildren;
  const isActive =
    node.documentId === activeDocumentId ||
    (node.documentId === "__full_case__" && activeDocumentId === "__full_case__");

  const icon = groupIconMap[node.id] ?? (
    isLeaf ? (
      <FileText className="w-3.5 h-3.5 shrink-0 text-text-muted" />
    ) : open ? (
      <FolderOpen className="w-3.5 h-3.5 shrink-0 text-text-muted" />
    ) : (
      <Folder className="w-3.5 h-3.5 shrink-0 text-text-muted" />
    )
  );

  function handleClick() {
    if (hasChildren) {
      setOpen((v) => !v);
    }
    if (node.documentId) {
      if (node.documentId === "__full_case__") {
        onNavigate({ kind: "full_case" });
      } else {
        onNavigate({ kind: "document", documentId: node.documentId });
      }
    }
  }

  return (
    <div>
      <button
        onClick={handleClick}
        className={clsx(
          "w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-left",
          "transition-colors duration-75 group",
          isActive
            ? "bg-accent-light text-accent font-medium"
            : "text-text-secondary hover:bg-surface-2 hover:text-text-primary",
          depth === 0 && "font-semibold text-text-primary"
        )}
        style={{ paddingLeft: `${8 + depth * 14}px` }}
      >
        {hasChildren && (
          <span className="shrink-0 text-text-muted">
            {open ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
          </span>
        )}
        {!hasChildren && <span className="w-3 shrink-0" />}
        <span className={clsx(isActive ? "text-accent" : "text-text-muted")}>
          {icon}
        </span>
        <span className="truncate text-xs leading-relaxed">{node.label}</span>
      </button>

      {hasChildren && open && (
        <div>
          {node.children!.map((child) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              activeDocumentId={activeDocumentId}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function CaseTree({ nodes, activeDocumentId, onNavigate }: CaseTreeProps) {
  return (
    <nav className="px-1">
      {nodes.map((node) => (
        <TreeNode
          key={node.id}
          node={node}
          depth={0}
          activeDocumentId={activeDocumentId}
          onNavigate={onNavigate}
          defaultOpen
        />
      ))}
    </nav>
  );
}
