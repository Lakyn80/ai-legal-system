import { PageHeader } from "@/components/page-header";
import { UploadForm } from "@/features/upload/upload-form";

export default function UploadPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Ingestion"
        title="Upload právních dokumentů"
        description="Frontend posílá soubory do FastAPI upload endpointu, ukládá metadata a může okamžitě spustit ingest do Qdrant."
      />
      <UploadForm />
    </div>
  );
}
