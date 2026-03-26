"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Overview" },
  { href: "/upload", label: "Upload" },
  { href: "/documents", label: "Documents" },
  { href: "/search", label: "Search" },
  { href: "/strategy", label: "Strategy" },
];

export function Navigation() {
  const pathname = usePathname();

  return (
    <nav className="panel sticky top-6 z-20 flex flex-wrap items-center gap-3 px-4 py-3">
      <div className="mr-4">
        <div className="text-xs uppercase tracking-[0.3em] text-slate-500">AI Legal System</div>
        <div className="font-serif text-2xl text-ink">Litigation Workspace</div>
      </div>
      {links.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`rounded-2xl px-4 py-2 text-sm font-semibold transition ${
              active ? "bg-ink text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
