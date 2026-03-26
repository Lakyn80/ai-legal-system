import type { Metadata } from "next";

import { Navigation } from "@/components/navigation";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Legal System",
  description: "AI legal workspace for judicial files, statutes, case law and litigation strategy.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="font-sans">
        <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-8 px-4 py-6 md:px-8">
          <Navigation />
          <main className="pb-10">{children}</main>
        </div>
      </body>
    </html>
  );
}
