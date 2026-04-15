import { NextRequest, NextResponse } from "next/server";
import { caseCache } from "@/lib/caseCache";
import { buildCaseInfo } from "@/lib/extractionHelpers";

export async function GET(
  _req: NextRequest,
  { params }: { params: { caseId: string } },
) {
  const { caseId } = params;
  const cached = caseCache.get(caseId);

  if (!cached) {
    return NextResponse.json({ caseId, status: "not_loaded" }, { status: 200 });
  }

  return NextResponse.json(buildCaseInfo(caseId, cached));
}
