"use client";

import { useState } from "react";

import { ChunkResults } from "@/components/chunk-results";
import { SectionCard } from "@/components/section-card";
import { JurisdictionSelector } from "@/features/jurisdiction/jurisdiction-selector";
import { splitCommaValues } from "@/lib/utils";
import { backendApi } from "@/services/backend-api";
import { Country, Domain, SearchResultItem } from "@/types";

export function SearchPanel() {
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState<Country>("czechia");
  const [domain, setDomain] = useState<Domain>("courts");
  const [caseId, setCaseId] = useState("");
  const [documentIds, setDocumentIds] = useState("");
  const [topK, setTopK] = useState(6);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResultItem[]>([]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      const response = await backendApi.search({
        query,
        country,
        domain,
        case_id: caseId || undefined,
        document_ids: splitCommaValues(documentIds),
        top_k: topK,
      });
      setResults(response);
      setMessage(`Nalezeno ${response.length} relevantních chunků.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Search selhal.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <SectionCard
        title="Semantic Search"
        description="Vyhledávej nad chunkovanými dokumenty uloženými v Qdrant s filtrováním podle jurisdikce, modulu a case ID."
      >
        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-sm font-semibold text-slate-700">Search Query</label>
            <textarea
              className="input-field min-h-36"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Např. nárok na náhradu škody, neplatnost výpovědi, procesní obrana..."
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
              <label className="mb-2 block text-sm font-semibold text-slate-700">Top K</label>
              <input
                className="input-field"
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(event) => setTopK(Number(event.target.value))}
              />
            </div>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
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
              <label className="mb-2 block text-sm font-semibold text-slate-700">Document IDs</label>
              <input
                className="input-field"
                value={documentIds}
                onChange={(event) => setDocumentIds(event.target.value)}
                placeholder="id1, id2, id3"
              />
            </div>
          </div>

          <button className="action-button" disabled={loading || !query.trim()} type="submit">
            {loading ? "Searching..." : "Run Search"}
          </button>
          {message ? <p className="text-sm text-slate-600">{message}</p> : null}
        </form>
      </SectionCard>

      <SectionCard
        title="Retrieved Chunks"
        description="Výsledek podobnostního vyhledávání připravený pro další právní analýzu a prompting."
      >
        <ChunkResults items={results} />
      </SectionCard>
    </div>
  );
}
