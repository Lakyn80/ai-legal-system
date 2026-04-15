import { NextRequest, NextResponse } from "next/server";
import { runStore } from "@/lib/runStore";
import type { AnalysisOutput } from "@/lib/types";

export async function GET(
  _req: NextRequest,
  { params }: { params: { caseId: string; runId: string } },
) {
  const { caseId, runId } = params;
  const record = runStore.get(runId);

  if (!record || record.caseId !== caseId) {
    return NextResponse.json({ error: `Run ${runId} not found.` }, { status: 404 });
  }

  if (record.status === "running") {
    return NextResponse.json({ error: "Run still in progress." }, { status: 202 });
  }

  if (record.status === "failed") {
    return NextResponse.json(
      { error: record.error ?? "Run failed." },
      { status: 500 },
    );
  }

  const output = record.output!;

  // Map extraction output → AnalysisOutput for the frontend
  const issueSummary = output.issues
    .slice(0, 3)
    .map((i) => `${i.issue_title}: ${i.problem_description}`)
    .filter(Boolean)
    .join(" · ");

  const legalOptions = output.issues
    .map((i) => i.defense_argument)
    .filter(Boolean);

  const applicableLaws = [
    ...new Set(
      output.issues.flatMap((i) =>
        i.legal_basis.map((lb) => `${lb.law} čl. ${lb.provision}`),
      ),
    ),
  ];

  const risks = output.issues
    .flatMap((i) => i.evidence_gaps)
    .filter(Boolean);

  const nextSteps = output.issues
    .map((i) => i.requested_consequence)
    .filter(Boolean);

  const result: AnalysisOutput = {
    runId,
    caseId,
    issueSummary: issueSummary || "Analýza dokončena.",
    legalOptions: legalOptions.length ? legalOptions : ["Žádné konkrétní možnosti nebyly identifikovány."],
    applicableLaws: applicableLaws.length ? applicableLaws : [],
    risks: risks.length ? risks : [],
    nextSteps: nextSteps.length ? nextSteps : [],
    defenseBlocks: output.defense_blocks,
  };

  return NextResponse.json(result);
}
