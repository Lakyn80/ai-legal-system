"use client";

import { useEffect, useState } from "react";

import { SectionCard } from "@/components/section-card";
import { formatDate } from "@/lib/utils";
import { backendApi } from "@/services/backend-api";
import { DocumentRecord } from "@/types";

export function DocumentsList() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  async function loadDocuments() {
    setLoading(true);
    try {
      const payload = await backendApi.listDocuments();
      setDocuments(payload);
      setMessage(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Nepodařilo se načíst dokumenty.");
    } finally {
      setLoading(false);
    }
  }

  async function ingestDocument(documentId: string) {
    setMessage("Spouštím ingest...");
    try {
      const [result] = await backendApi.ingestDocuments([documentId]);
      setMessage(`Ingest hotov: ${result.filename}, stav ${result.status}, chunků ${result.chunk_count}.`);
      await loadDocuments();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Ingest se nezdařil.");
    }
  }

  useEffect(() => {
    void loadDocuments();
  }, []);

  return (
    <SectionCard
      title="Uploaded Documents"
      description="Přehled lokálně uložených dokumentů včetně stavu ingestu, chunk countu a základních metadat."
    >
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <button className="secondary-button" onClick={() => void loadDocuments()} type="button">
          Refresh
        </button>
        {message ? <span className="text-sm text-slate-600">{message}</span> : null}
      </div>

      {loading ? (
        <p className="text-sm text-slate-500">Loading documents...</p>
      ) : documents.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {documents.map((document) => (
            <article key={document.id} className="rounded-3xl border border-slate-200 bg-white/80 p-5">
              <div className="mb-4 flex items-start justify-between gap-4">
                <div>
                  <p className="font-semibold text-ink">{document.filename}</p>
                  <p className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">
                    {document.country} / {document.domain}
                  </p>
                </div>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.15em] text-slate-600">
                  {document.status}
                </span>
              </div>

              <div className="space-y-1 text-sm text-slate-600">
                <p>Uploaded: {formatDate(document.uploaded_at)}</p>
                <p>Chunks: {document.chunk_count}</p>
                <p>Type: {document.document_type}</p>
                {document.case_id ? <p>Case: {document.case_id}</p> : null}
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {document.tags.map((tag) => (
                  <span key={`${document.id}-${tag}`} className="rounded-full bg-sand px-3 py-1 text-xs text-ink">
                    {tag}
                  </span>
                ))}
              </div>

              <div className="mt-5">
                <button className="secondary-button" onClick={() => void ingestDocument(document.id)} type="button">
                  Re-ingest Document
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="text-sm text-slate-500">Zatím tu nejsou žádné dokumenty.</p>
      )}
    </SectionCard>
  );
}
