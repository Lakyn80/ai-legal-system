"use client";

import { clsx } from "clsx";

interface PageNavigationProps {
  pageCount: number;
  currentPage: number;
  onPageChange: (page: number) => void;
}

export function PageNavigation({
  pageCount,
  currentPage,
  onPageChange,
}: PageNavigationProps) {
  if (pageCount <= 1) return null;

  return (
    <div className="flex items-center gap-1 flex-wrap">
      <span className="text-xs text-text-muted mr-1">Strana:</span>
      {Array.from({ length: pageCount }, (_, i) => i + 1).map((page) => (
        <button
          key={page}
          onClick={() => onPageChange(page)}
          className={clsx(
            "w-7 h-7 rounded text-xs font-medium transition-colors",
            page === currentPage
              ? "bg-accent text-white"
              : "bg-surface-2 text-text-secondary hover:bg-surface-3 border border-border"
          )}
        >
          {page}
        </button>
      ))}
    </div>
  );
}
