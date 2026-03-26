import { PageHeader } from "@/components/page-header";
import { SearchPanel } from "@/features/search/search-panel";

export default function SearchPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Retrieval"
        title="Vyhledávání v dokumentech"
        description="Podobnostní search nad Qdrant se strategickým filtrováním podle jurisdiction, domain, case ID a konkrétních dokumentů."
      />
      <SearchPanel />
    </div>
  );
}
