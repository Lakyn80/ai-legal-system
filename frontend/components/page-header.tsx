interface PageHeaderProps {
  eyebrow: string;
  title: string;
  description: string;
}

export function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-[0.35em] text-brass">{eyebrow}</p>
      <h1 className="font-serif text-4xl text-ink md:text-5xl">{title}</h1>
      <p className="max-w-3xl text-sm leading-7 text-slate-600 md:text-base">{description}</p>
    </div>
  );
}
