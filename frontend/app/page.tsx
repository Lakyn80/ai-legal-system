import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { SectionCard } from "@/components/section-card";

const cards = [
  {
    title: "Upload Pipeline",
    description: "Nahraj soudní spisy, zákony a rozhodnutí a pošli je do parsing + embedding pipeline.",
    href: "/upload",
  },
  {
    title: "Document Registry",
    description: "Kontroluj uložené dokumenty, ingest stav a připravenost pro retrieval a strategy engine.",
    href: "/documents",
  },
  {
    title: "Semantic Search",
    description: "Vyhledávej relevantní chunky v Qdrant nad Russia a Czechia moduly odděleně.",
    href: "/search",
  },
  {
    title: "Strategy Engine",
    description: "Spusť LangGraph workflow a získej strukturovaný návrh procesní a argumentační strategie.",
    href: "/strategy",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-8">
      <section className="panel overflow-hidden p-8 md:p-12">
        <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-6">
            <PageHeader
              eyebrow="Monorepo Workspace"
              title="AI právní systém pro soudní spisy, zákony a sporovou strategii"
              description="Základ aplikace je rozdělený na backend ve FastAPI, frontend v Next.js, Qdrant pro vektorové vyhledávání a LangGraph workflow pro tvorbu strategie nad jurisdikcemi Russia a Czechia."
            />
            <div className="flex flex-wrap gap-3">
              <Link className="action-button" href="/upload">
                Start Upload
              </Link>
              <Link className="secondary-button" href="/strategy">
                Open Strategy Engine
              </Link>
            </div>
          </div>

          <div className="rounded-[2rem] bg-ink p-6 text-white">
            <p className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-300">Jurisdictions</p>
            <div className="mt-6 space-y-4">
              <div className="rounded-3xl bg-white/10 p-5">
                <p className="font-serif text-3xl">Russia</p>
                <p className="mt-2 text-sm leading-7 text-slate-300">
                  Courts, law, prompts a workflow připravené jako oddělený plug-in styl modul.
                </p>
              </div>
              <div className="rounded-3xl bg-white/10 p-5">
                <p className="font-serif text-3xl">Czechia</p>
                <p className="mt-2 text-sm leading-7 text-slate-300">
                  Samostatná větev pro české právní dokumenty, judikaturu a tvorbu strategie.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        {cards.map((card) => (
          <SectionCard key={card.href} title={card.title} description={card.description}>
            <Link className="secondary-button" href={card.href}>
              Open Section
            </Link>
          </SectionCard>
        ))}
      </section>
    </div>
  );
}
