"""
Audit-friendly logging for Agent 2. Avoid dumping full case text by default.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


def _case_id_fingerprint(case_id: str) -> str:
    """Non-reversible short fingerprint for cross-log correlation (not cryptographic identity)."""
    return hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:12]


@dataclass
class Agent2AuditRecord:
    """Structured audit metadata for a single Agent 2 run."""

    case_id_fp: str
    jurisdiction: str
    prompt_version: str
    schema_version: str
    model_name: str
    validation_ok: bool
    repair_count: int
    contract_ok: bool
    contract_violation_count: int
    started_at_iso: str
    finished_at_iso: str
    error_code: str | None = None
    # Safe diagnostics only (lengths, counts — not full PII)
    input_summary: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build_input_summary(cls, *, facts_n: int, flags_n: int, provisions_n: int, summary_len: int) -> dict[str, Any]:
        return {
            "facts_count": facts_n,
            "issue_flags_count": flags_n,
            "allowed_provisions_count": provisions_n,
            "cleaned_summary_chars": summary_len,
        }


def emit_audit_log(record: Agent2AuditRecord) -> None:
    """Emit a single INFO line suitable for log aggregation."""
    log.info(
        "agent2_audit case_id_fp=%s jurisdiction=%s prompt=%s schema=%s model=%s "
        "validation_ok=%s repair_count=%s contract_ok=%s contract_violations=%s error=%s %s",
        record.case_id_fp,
        record.jurisdiction,
        record.prompt_version,
        record.schema_version,
        record.model_name,
        record.validation_ok,
        record.repair_count,
        record.contract_ok,
        record.contract_violation_count,
        record.error_code,
        record.input_summary,
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint_case_id(case_id: str) -> str:
    return _case_id_fingerprint(case_id)
