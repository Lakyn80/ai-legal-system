import { PageHeader } from "@/components/page-header";
import { StrategyPanel } from "@/features/strategy/strategy-panel";

export default function StrategyPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="LangGraph"
        title="Generování právní strategie"
        description="Workflow propojuje intake, jurisdiction routing, retrieval, analýzu norem, judikatury a syntézu sporové strategie do strukturovaného JSON."
      />
      <StrategyPanel />
    </div>
  );
}
