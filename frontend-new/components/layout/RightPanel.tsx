import { CaseDocument } from "@/lib/types";
import { documentTypeLabels } from "@/lib/mockData";
import { Panel } from "@/components/ui/Panel";
import { CalendarDays, FileText, Gavel, Users } from "lucide-react";

interface RightPanelProps {
  document?: CaseDocument | null;
}

export function RightPanel({ document }: RightPanelProps) {
  return (
    <aside className="w-64 shrink-0 flex flex-col gap-3 overflow-y-auto p-3 border-l border-border bg-surface-1">
      <Panel title="Metadata dokumentu" padded={false}>
        {document ? (
          <ul className="divide-y divide-border">
            <MetaRow
              icon={<FileText className="w-3.5 h-3.5" />}
              label="Typ"
              value={documentTypeLabels[document.type] ?? document.type}
            />
            <MetaRow
              icon={<CalendarDays className="w-3.5 h-3.5" />}
              label="Datum"
              value={document.date}
            />
            {document.metadata.court && (
              <MetaRow
                icon={<Gavel className="w-3.5 h-3.5" />}
                label="Soud"
                value={document.metadata.court}
              />
            )}
            {document.metadata.caseNumber && (
              <MetaRow
                icon={<FileText className="w-3.5 h-3.5" />}
                label="Sp. zn."
                value={document.metadata.caseNumber}
              />
            )}
            {document.metadata.judge && (
              <MetaRow
                icon={<Users className="w-3.5 h-3.5" />}
                label="Soudce"
                value={document.metadata.judge}
              />
            )}
            {document.metadata.parties && (
              <MetaRow
                icon={<Users className="w-3.5 h-3.5" />}
                label="Strany"
                value={document.metadata.parties}
              />
            )}
            <MetaRow
              icon={<FileText className="w-3.5 h-3.5" />}
              label="Stran"
              value={String(document.pageCount)}
            />
          </ul>
        ) : (
          <p className="px-4 py-3 text-xs text-text-muted">
            Vyberte dokument pro zobrazení metadat.
          </p>
        )}
      </Panel>

      <Panel title="Související dokumenty" padded={false}>
        <p className="px-4 py-3 text-xs text-text-muted">
          Propojené dokumenty budou zobrazeny po aktivaci vyhledávání.
        </p>
      </Panel>

      <Panel title="Analytické poznámky" padded={false}>
        <p className="px-4 py-3 text-xs text-text-muted">
          Zde se zobrazí poznámky AI po spuštění analýzy.
        </p>
      </Panel>
    </aside>
  );
}

function MetaRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <li className="px-4 py-2.5 flex flex-col gap-0.5">
      <span className="flex items-center gap-1.5 text-xs text-text-muted">
        {icon}
        {label}
      </span>
      <span className="text-xs font-medium text-text-primary leading-snug">{value}</span>
    </li>
  );
}
