import { redirect } from "next/navigation";

const DEFAULT_CASE_ID =
  process.env.NEXT_PUBLIC_DEFAULT_CASE_ID ??
  "2f393699-ebaa-4c79-b84c-ad9af75d0bcf";

// Default route → open configured case
export default function Home() {
  redirect(`/case/${DEFAULT_CASE_ID}`);
}
