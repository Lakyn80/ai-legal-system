"use client";

import { useState } from "react";

import { SectionCard } from "@/components/section-card";
import { JurisdictionSelector } from "@/features/jurisdiction/jurisdiction-selector";
import { backendApi } from "@/services/backend-api";
import { Country, DocumentRecord, Domain } from "@/types";

export function UploadForm() {
  const [file, setFile] = useState<File | null>(null);
  const [country, setCountry] = useState<Country>("czechia");
  const [domain, setDomain] = useState<Domain>("courts");
  const [documentType, setDocumentType] = useState("court_filing");
  const [source, setSource] = useState("");
  const [caseId, setCaseId] = useState("");
  const [tags, setTags] = useState("");
  const [autoIngest, setAutoIngest] = useState(true);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [uploadedDocument, setUploadedDocument] = useState<DocumentRecord | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setMessage("Vyber soubor pro upload.");
      return;
    }

    setLoading(true);
    setMessage(null);
    try {
      const document = await backendApi.uploadDocument({
        file,
        country,
        domain,
        documentType,
        source,
        caseId,
        tags,
      });
      setUploadedDocument(document);

      if (autoIngest) {
        const [result] = await backendApi.ingestDocuments([document.id]);
        setMessage(`Upload i ingest hotov. Stav: ${result.status}, chunků: ${result.chunk_count}.`);
      } else {
        setMessage("Upload hotov. Dokument čeká na ingest.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload se nezdařil.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
      <SectionCard
        title="Document Upload"
        description="Nahraj PDF, DOCX nebo TXT, přiřaď jurisdikci a doménu a případně spusť ingest ihned po uploadu."
      >
        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700">Soubor</label>
            <input
              className="input-field"
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700">Jurisdikce</label>
            <JurisdictionSelector value={country} onChange={setCountry} />
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700">Modul</label>
              <select
                className="input-field"
                value={domain}
                onChange={(event) => setDomain(event.target.value as Domain)}
              >
                <option value="courts">Courts</option>
                <option value="law">Law</option>
              </select>
            </div>

            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700">Document Type</label>
              <input
                className="input-field"
                value={documentType}
                onChange={(event) => setDocumentType(event.target.value)}
                placeholder="court_filing / statute / decision"
              />
            </div>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700">Source</label>
              <input
                className="input-field"
                value={source}
                onChange={(event) => setSource(event.target.value)}
                placeholder="Court portal, internal archive..."
              />
            </div>

            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700">Case ID</label>
              <input
                className="input-field"
                value={caseId}
                onChange={(event) => setCaseId(event.target.value)}
                placeholder="Optional"
              />
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700">Tags</label>
            <input
              className="input-field"
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="contract, damages, appeal"
            />
          </div>

          <label className="flex items-center gap-3 text-sm text-slate-600">
            <input
              checked={autoIngest}
              onChange={(event) => setAutoIngest(event.target.checked)}
              type="checkbox"
            />
            Spustit ingest hned po uploadu
          </label>

          <button className="action-button" disabled={loading} type="submit">
            {loading ? "Processing..." : "Upload Document"}
          </button>
        </form>
      </SectionCard>

      <SectionCard
        title="Last Result"
        description="Okamžitý přehled posledního nahraného dokumentu a výsledku pipeline."
      >
        <div className="space-y-4 text-sm text-slate-700">
          {uploadedDocument ? (
            <div className="rounded-3xl border border-slate-200 bg-white/80 p-5">
              <p className="font-semibold text-ink">{uploadedDocument.filename}</p>
              <p className="mt-2">Jurisdikce: {uploadedDocument.country}</p>
              <p>Modul: {uploadedDocument.domain}</p>
              <p>Typ: {uploadedDocument.document_type}</p>
            </div>
          ) : (
            <p className="text-slate-500">Zatím nebyl nahrán žádný dokument v této relaci.</p>
          )}
          {message ? <div className="rounded-3xl bg-sand p-4 text-ink">{message}</div> : null}
        </div>
      </SectionCard>
    </div>
  );
}
