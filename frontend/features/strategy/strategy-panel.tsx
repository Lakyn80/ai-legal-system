"use client";

import { useState } from "react";

import { ChunkResults } from "@/components/chunk-results";
import { SectionCard } from "@/components/section-card";
import { StrategyView } from "@/components/strategy-view";
import { JurisdictionSelector } from "@/features/jurisdiction/jurisdiction-selector";
import { splitCommaValues } from "@/lib/utils";
import { backendApi } from "@/services/backend-api";
import { Country, Domain, SearchResultItem, StrategyResult } from "@/types";

export function StrategyPanel() {
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState<Country>("czechia");
  const [domain, setDomain] = useState<Domain>("courts");
  const [caseId, setCaseId] = useState("");
  const [documentIds, setDocumentIds] = useState("");
  const [topK, setTopK] = useState(8);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [strategy, setStrategy] = useState<StrategyResult | null>(null);
  const [chunks, setChunks] = useState<SearchResultItem[]>([]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      const response = await backendApi.generateStrategy({
        query,
        country,
        domain,
        case_id: caseId || undefined,
        document_ids: splitCommaValues(documentIds),
        top_k: topK,
      });
      setStrategy(response.strategy);
      setChunks(response.retrieved_chunks);
      setMessage("Strategie byla vygenerována.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Generování strategie selhalo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionCard
        title="Strategy Generator"
        description="LangGraph workflow provede intake, jurisdikční routing, retrieval, analýzu norem a judikatury a vrátí strukturovaný strategický JSON."
      >
        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700">Strategy Query</label>
            <textarea
              className="input-field min-h-40"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Popiš spor, procesní stav, zájmy klienta a očekávaný výsledek."
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700">Jurisdikce</label>
            <JurisdictionSelector value={country} onChange={setCountry} />
          </div>

          <div className="grid gap-5 md:grid-cols-3">
            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700">Preferovaný modul</label>
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
              <label className="mb-2 block text-sm font-semibold text-slate-700">Case ID</label>
              <input
                className="input-field"
                value={caseId}
                onChange={(event) => setCaseId(event.target.value)}
                placeholder="Optional"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-semibold text-slate-700">Top K</label>
              <input
                className="input-field"
                type="number"
                min={2}
                max={20}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
              />
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700">Document IDs</label>
            <input
              className="input-field"
              value={documentIds}
              onChange={(event) => setDocumentIds(event.target.value)}
              placeholder="Omez strategii na konkrétní dokumenty: id1, id2"
            />
          </div>

          <button className="action-button" disabled={loading || !query.trim()} type="submit">
            {loading ? "Generating..." : "Generate Strategy"}
          </button>
          {message ? <p className="text-sm text-slate-600">{message}</p> : null}
        </form>
      </SectionCard>

      <SectionCard
        title="Structured Output"
        description="Výstup je připraven jako JSON-friendly struktura pro další audit, export nebo rozšíření o další analyzátory."
      >
        <StrategyView strategy={strategy} />
      </SectionCard>

      <SectionCard
        title="Retrieved Context"
        description="Chunky použité při generování strategie. Slouží pro auditovatelnost a ruční kontrolu podkladů."
      >
        <ChunkResults items={chunks} />
      </SectionCard>
    </div>
  );
}
