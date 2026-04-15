import { HTMLAttributes } from "react";
import { clsx } from "clsx";

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  title?: string;
  padded?: boolean;
}

export function Panel({ title, padded = true, className, children, ...props }: PanelProps) {
  return (
    <div
      className={clsx(
        "bg-surface-0 border border-border rounded panel-shadow",
        className
      )}
      {...props}
    >
      {title && (
        <div className="px-4 py-2.5 border-b border-border">
          <span className="text-xs font-semibold text-text-muted uppercase tracking-wide">
            {title}
          </span>
        </div>
      )}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </div>
  );
}
