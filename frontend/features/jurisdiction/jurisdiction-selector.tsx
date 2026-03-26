import { Country } from "@/types";

const options: Array<{ value: Country; label: string; note: string }> = [
  {
    value: "russia",
    label: "Russia",
    note: "Ruské soudní spisy, zákony a judikatura.",
  },
  {
    value: "czechia",
    label: "Czechia",
    note: "České soudní spisy, předpisy a rozhodnutí.",
  },
];

interface JurisdictionSelectorProps {
  value: Country;
  onChange: (value: Country) => void;
}

export function JurisdictionSelector({ value, onChange }: JurisdictionSelectorProps) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`rounded-3xl border p-4 text-left transition ${
              active
                ? "border-ink bg-ink text-white"
                : "border-slate-200 bg-white/80 text-slate-700 hover:border-slate-300"
            }`}
          >
            <div className="mb-1 text-sm font-semibold uppercase tracking-[0.25em]">
              {option.label}
            </div>
            <div className={`text-sm leading-6 ${active ? "text-slate-200" : "text-slate-500"}`}>
              {option.note}
            </div>
          </button>
        );
      })}
    </div>
  );
}
