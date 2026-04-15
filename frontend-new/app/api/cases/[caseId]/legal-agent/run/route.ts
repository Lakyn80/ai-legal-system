import { NextRequest, NextResponse } from "next/server";
import { runStore, type RunRecord } from "@/lib/runStore";
import { caseCache } from "@/lib/caseCache";
import { backendClient, BackendClientError } from "@/lib/backendClient";
import type { BackendExtractionOutput, RunMode } from "@/lib/types";

interface RunRequestBody {
  userInput?: string;
  mode?: RunMode;
  jurisdiction?: string;
  facts?: string[];
  issueFlags?: string[];
}

interface BackendStrategyExtractionResponse {
  output: BackendExtractionOutput;
}

async function executeRun(record: RunRecord, body: RunRequestBody): Promise<void> {
  try {
    const resp = await backendClient.post<BackendStrategyExtractionResponse>(
      "/russia/strategy/extraction/from-case",
      {
        case_id: record.caseId,
        jurisdiction: body.jurisdiction ?? "Russia",
        cleaned_summary: body.userInput ?? "",
        facts: body.facts ?? [],
        issue_flags: body.issueFlags ?? [],
        claims_or_questions: body.userInput ? [body.userInput] : [],
        strict_reliability: true,
        max_repair_attempts: 1,
      },
    );

    const output = resp.output;

    // Always update the case cache on successful extraction
    caseCache.set(record.caseId, output);

    runStore.update(record.runId, {
      status: "completed",
      output,
      completedAt: new Date(),
    });
  } catch (err) {
    const message =
      err instanceof BackendClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : "Unknown error";

    runStore.update(record.runId, {
      status: "failed",
      error: message,
      completedAt: new Date(),
    });
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { caseId: string } },
) {
  const { caseId } = params;

  let body: RunRequestBody = {};
  try {
    body = await req.json();
  } catch {
    // empty body is fine — defaults apply
  }

  const mode: RunMode = body.mode ?? "analyze";
  const runId = crypto.randomUUID();

  const record: RunRecord = {
    runId,
    caseId,
    mode,
    status: "running",
    createdAt: new Date(),
  };

  runStore.set(record);

  // Fire-and-forget — do not await
  executeRun(record, body).catch(() => {
    // errors are captured inside executeRun
  });

  return NextResponse.json(
    { runId, caseId, mode, status: "running" },
    { status: 202 },
  );
}
