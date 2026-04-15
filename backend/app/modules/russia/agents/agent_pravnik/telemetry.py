"""
Audit-friendly logging for agent_pravnik — no full case text by default.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


def _case_id_fingerprint(case_id: str) -> str:
    return hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:12]


@dataclass
class PravnikAuditRecord:
    case_id_fp: str
    jurisdiction: str
    prompt_version: str
    schema_version: str
    model_name: str
    document_kind: str
    work_mode: str
    repair_count: int
    contract_ok: bool
    contract_violation_count: int
    quality_ok: bool
    used_deterministic_fallback: bool
    started_at_iso: str
    finished_at_iso: str
    error_code: str | None = None
    input_summary: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build_input_summary(
        cls,
        *,
        facts_n: int,
        flags_n: int,
        provisions_n: int,
        summary_len: int,
    ) -> dict[str, Any]:
        return {
            "facts_count": facts_n,
            "issue_flags_count": flags_n,
            "allowed_provisions_count": provisions_n,
            "cleaned_summary_chars": summary_len,
        }


def emit_audit_log(record: PravnikAuditRecord) -> None:
    log.info(
        "agent_pravnik_audit case_id_fp=%s jurisdiction=%s prompt=%s schema=%s model=%s "
        "document_kind=%s work_mode=%s repair_count=%s contract_ok=%s contract_violations=%s "
        "quality_ok=%s fallback=%s error=%s %s",
        record.case_id_fp,
        record.jurisdiction,
        record.prompt_version,
        record.schema_version,
        record.model_name,
        record.document_kind,
        record.work_mode,
        record.repair_count,
        record.contract_ok,
        record.contract_violation_count,
        record.quality_ok,
        record.used_deterministic_fallback,
        record.error_code,
        record.input_summary,
    )


def emit_draft_rejected(case_id_fp: str, reasons: list[str]) -> None:
    log.warning("agent_pravnik_draft_rejected case_id_fp=%s reasons=%s", case_id_fp, reasons)


def emit_fallback(case_id_fp: str) -> None:
    log.warning("agent_pravnik_fallback case_id_fp=%s", case_id_fp)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint_case_id(case_id: str) -> str:
    return _case_id_fingerprint(case_id)
