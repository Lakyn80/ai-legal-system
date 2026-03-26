import { PageHeader } from "@/components/page-header";
import { DocumentsList } from "@/features/documents/documents-list";

export default function DocumentsPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Registry"
        title="Přehled nahraných dokumentů"
        description="Centrální přehled dokumentů a ingest stavu nad oběma jurisdikcemi s možností opětovného zpracování."
      />
      <DocumentsList />
    </div>
  );
}
