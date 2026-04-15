import { NextRequest, NextResponse } from "next/server";
import { runStore } from "@/lib/runStore";

export async function GET(
  _req: NextRequest,
  { params }: { params: { caseId: string; runId: string } },
) {
  const { caseId, runId } = params;
  const record = runStore.get(runId);

  if (!record || record.caseId !== caseId) {
    return NextResponse.json({ error: `Run ${runId} not found.` }, { status: 404 });
  }

  return NextResponse.json({
    runId: record.runId,
    caseId: record.caseId,
    mode: record.mode,
    status: record.status,
    createdAt: record.createdAt.toISOString(),
    completedAt: record.completedAt?.toISOString(),
    error: record.error,
  });
}
