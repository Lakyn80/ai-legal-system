import { redirect } from "next/navigation";

// Default route → open the demo case
export default function Home() {
  redirect("/case/12C45-2023");
}
