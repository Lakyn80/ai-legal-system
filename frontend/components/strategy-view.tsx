import { StrategyResult } from "@/types";

interface StrategyViewProps {
  strategy: StrategyResult | null;
}

function RenderList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white/80 p-5">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.25em] text-slate-500">{title}</h3>
      {items.length ? (
        <ul className="space-y-2 text-sm leading-7 text-slate-700">
          {items.map((item) => (
            <li key={`${title}-${item}`}>• {item}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">No items generated.</p>
      )}
    </div>
  );
}

export function StrategyView({ strategy }: StrategyViewProps) {
  if (!strategy) {
    return (
      <div className="rounded-3xl border border-dashed border-slate-300 bg-white/60 p-6 text-sm text-slate-500">
        Strategy output will appear here after generation.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-[2rem] bg-ink p-6 text-white">
        <div className="mb-3 flex flex-wrap items-center gap-3 text-xs font-semibold uppercase tracking-[0.25em] text-slate-300">
          <span>{strategy.jurisdiction}</span>
          <span>{strategy.domain}</span>
          <span>Confidence {(strategy.confidence * 100).toFixed(0)}%</span>
        </div>
        <p className="font-serif text-3xl leading-tight">{strategy.summary}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <RenderList title="Facts" items={strategy.facts} />
        <RenderList title="Relevant Laws" items={strategy.relevant_laws} />
        <RenderList title="Court Positions" items={strategy.relevant_court_positions} />
        <RenderList title="Arguments For Client" items={strategy.arguments_for_client} />
        <RenderList title="Arguments Against Client" items={strategy.arguments_against_client} />
        <RenderList title="Risks" items={strategy.risks} />
        <RenderList title="Recommended Actions" items={strategy.recommended_actions} />
        <RenderList title="Missing Documents" items={strategy.missing_documents} />
      </div>

      <div className="rounded-3xl border border-slate-200 bg-slate-950 p-5 text-sm text-slate-100">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.25em] text-slate-400">Raw JSON</h3>
        <pre className="overflow-x-auto whitespace-pre-wrap break-words">
          {JSON.stringify(strategy, null, 2)}
        </pre>
      </div>
    </div>
  );
}
