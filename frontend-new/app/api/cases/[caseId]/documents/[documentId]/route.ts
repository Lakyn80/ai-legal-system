import { NextRequest, NextResponse } from "next/server";
import { caseCache } from "@/lib/caseCache";
import { findDocument } from "@/lib/extractionHelpers";

export async function GET(
  _req: NextRequest,
  { params }: { params: { caseId: string; documentId: string } },
) {
  const { caseId, documentId } = params;
  const cached = caseCache.get(caseId);

  if (!cached) {
    return NextResponse.json({ error: "Case not loaded." }, { status: 404 });
  }

  const doc = findDocument(cached, documentId);
  if (!doc) {
    return NextResponse.json({ error: `Document ${documentId} not found.` }, { status: 404 });
  }

  return NextResponse.json(doc);
}
