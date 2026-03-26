import { ReactNode } from "react";

interface SectionCardProps {
  title: string;
  description?: string;
  children: ReactNode;
}

export function SectionCard({ title, description, children }: SectionCardProps) {
  return (
    <section className="panel p-6 md:p-8">
      <div className="mb-6 flex flex-col gap-2">
        <h2 className="font-serif text-2xl text-ink">{title}</h2>
        {description ? <p className="text-sm leading-6 text-slate-600">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}
