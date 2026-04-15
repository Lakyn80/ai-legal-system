import { NextRequest, NextResponse } from "next/server";
import { caseCache } from "@/lib/caseCache";
import { allDocuments } from "@/lib/extractionHelpers";

export async function GET(
  _req: NextRequest,
  { params }: { params: { caseId: string } },
) {
  const { caseId } = params;
  const cached = caseCache.get(caseId);

  if (!cached) {
    return NextResponse.json({ error: "Case not loaded." }, { status: 404 });
  }

  return NextResponse.json(allDocuments(cached));
}
