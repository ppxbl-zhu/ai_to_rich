from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation


class ResearchValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    source: str
    title: str
    published_at: datetime
    captured_at: datetime
    content_hash: str


@dataclass(frozen=True, slots=True)
class ResearchCall:
    call_id: str
    provider: str
    model: str
    prompt_version: str
    requested_at: datetime
    completed_at: datetime
    input_evidence_ids: tuple[str, ...]
    raw_output: Mapping[str, object]
    input_tokens: int
    output_tokens: int
    cost_cny: Decimal


@dataclass(frozen=True, slots=True)
class ResearchHypothesis:
    summary: str
    statement: str
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    falsification_conditions: tuple[str, ...]
    risks: tuple[str, ...]
    confidence: Decimal


@dataclass(frozen=True, slots=True)
class ResearchAudit:
    provider: str
    model: str
    prompt_version: str
    requested_at: datetime
    completed_at: datetime
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_cny: Decimal


@dataclass(frozen=True, slots=True)
class ResearchRecord:
    call_id: str
    hypothesis: ResearchHypothesis
    audit: ResearchAudit


_REQUIRED_FIELDS = {
    "summary",
    "hypothesis",
    "supporting_evidence_ids",
    "contradicting_evidence_ids",
    "falsification_conditions",
    "risks",
    "confidence",
}
_EXECUTION_FIELDS = {
    "side",
    "quantity",
    "order",
    "order_intent",
    "execute",
    "limit_price",
}


def validate_research_call(
    call: ResearchCall, evidence: tuple[Evidence, ...]
) -> ResearchRecord:
    output = call.raw_output
    if _EXECUTION_FIELDS.intersection(output):
        raise ResearchValidationError("LLM output contains forbidden execution fields")
    missing = _REQUIRED_FIELDS.difference(output)
    if missing:
        raise ResearchValidationError(f"missing research fields: {sorted(missing)}")

    known_ids = {item.evidence_id for item in evidence}
    if not set(call.input_evidence_ids).issubset(known_ids):
        raise ResearchValidationError("call input contains unknown evidence")

    supporting = _string_tuple(output["supporting_evidence_ids"], "supporting")
    contradicting = _string_tuple(output["contradicting_evidence_ids"], "contradicting")
    if not supporting:
        raise ResearchValidationError("at least one supporting citation is required")
    cited = set(supporting) | set(contradicting)
    if not cited.issubset(known_ids) or not cited.issubset(call.input_evidence_ids):
        raise ResearchValidationError("research output cites unknown evidence")

    falsification = _string_tuple(output["falsification_conditions"], "falsification")
    if not falsification:
        raise ResearchValidationError("falsification conditions are required")
    risks = _string_tuple(output["risks"], "risks")
    try:
        confidence = Decimal(str(output["confidence"]))
    except (InvalidOperation, ValueError) as error:
        raise ResearchValidationError("confidence must be numeric") from error
    if not Decimal() <= confidence <= Decimal(1):
        raise ResearchValidationError("confidence must be between zero and one")

    summary = _nonempty_string(output["summary"], "summary")
    statement = _nonempty_string(output["hypothesis"], "hypothesis")
    if call.input_tokens < 0 or call.output_tokens < 0 or call.cost_cny < 0:
        raise ResearchValidationError("audit usage values cannot be negative")
    return ResearchRecord(
        call_id=call.call_id,
        hypothesis=ResearchHypothesis(
            summary=summary,
            statement=statement,
            supporting_evidence_ids=supporting,
            contradicting_evidence_ids=contradicting,
            falsification_conditions=falsification,
            risks=risks,
            confidence=confidence,
        ),
        audit=ResearchAudit(
            provider=call.provider,
            model=call.model,
            prompt_version=call.prompt_version,
            requested_at=call.requested_at,
            completed_at=call.completed_at,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            total_tokens=call.input_tokens + call.output_tokens,
            cost_cny=call.cost_cny,
        ),
    )


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ResearchValidationError(f"{field} must be a list of strings")
    return tuple(value)


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchValidationError(f"{field} must be a non-empty string")
    return value
