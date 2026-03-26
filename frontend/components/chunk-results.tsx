import { SearchResultItem } from "@/types";

interface ChunkResultsProps {
  items: SearchResultItem[];
  emptyLabel?: string;
}

export function ChunkResults({
  items,
  emptyLabel = "No chunks available for the current query.",
}: ChunkResultsProps) {
  if (!items.length) {
    return (
      <div className="rounded-3xl border border-dashed border-slate-300 bg-white/60 p-6 text-sm text-slate-500">
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((item) => (
        <article key={item.chunk_id} className="rounded-3xl border border-slate-200 bg-white/80 p-5">
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
            <span>{item.country}</span>
            <span>{item.domain}</span>
            <span>Chunk {item.chunk_index}</span>
            <span>Score {item.score.toFixed(3)}</span>
          </div>
          <p className="mb-3 text-sm font-semibold text-ink">{item.filename}</p>
          <p className="text-sm leading-7 text-slate-700">{item.text}</p>
          <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500">
            {item.case_id ? <span>Case: {item.case_id}</span> : null}
            {item.tags.map((tag) => (
              <span key={`${item.chunk_id}-${tag}`} className="rounded-full bg-slate-100 px-3 py-1">
                {tag}
              </span>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}
