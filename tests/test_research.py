from datetime import datetime
from decimal import Decimal

import pytest

from quantagent.research import (
    Evidence,
    ResearchCall,
    ResearchValidationError,
    validate_research_call,
)

NOW = datetime.fromisoformat("2026-07-29T15:30:00+08:00")


def evidence() -> tuple[Evidence, ...]:
    return (
        Evidence(
            evidence_id="announcement-1",
            source="exchange_announcement",
            title="2026 half-year results",
            published_at=NOW,
            captured_at=NOW,
            content_hash="sha256:abc",
        ),
        Evidence(
            evidence_id="sector-1",
            source="sector_snapshot",
            title="Bank sector breadth",
            published_at=NOW,
            captured_at=NOW,
            content_hash="sha256:def",
        ),
    )


def call(**output_overrides: object) -> ResearchCall:
    output: dict[str, object] = {
        "summary": "Profit improved while the sector retained breadth.",
        "hypothesis": "Earnings momentum may support relative strength.",
        "supporting_evidence_ids": ["announcement-1", "sector-1"],
        "contradicting_evidence_ids": [],
        "falsification_conditions": ["Sector breadth falls below its threshold."],
        "risks": ["Margin improvement may not persist."],
        "confidence": "0.68",
    }
    output.update(output_overrides)
    return ResearchCall(
        call_id="call-1",
        provider="offline-test",
        model="deterministic-fixture",
        prompt_version="research-v1",
        requested_at=NOW,
        completed_at=NOW,
        input_evidence_ids=("announcement-1", "sector-1"),
        raw_output=output,
        input_tokens=120,
        output_tokens=80,
        cost_cny=Decimal("0"),
    )


def test_research_output_is_structured_cited_and_auditable() -> None:
    record = validate_research_call(call(), evidence())

    assert record.call_id == "call-1"
    assert record.hypothesis.confidence == Decimal("0.68")
    assert record.hypothesis.supporting_evidence_ids == (
        "announcement-1",
        "sector-1",
    )
    assert record.audit.total_tokens == 200
    assert record.audit.prompt_version == "research-v1"


def test_research_rejects_unknown_citation_and_missing_falsification() -> None:
    with pytest.raises(ResearchValidationError, match="unknown evidence"):
        validate_research_call(
            call(supporting_evidence_ids=["invented-source"]), evidence()
        )

    with pytest.raises(ResearchValidationError, match="falsification"):
        validate_research_call(call(falsification_conditions=[]), evidence())


def test_research_rejects_execution_instructions_and_invalid_confidence() -> None:
    with pytest.raises(ResearchValidationError, match="execution"):
        validate_research_call(call(quantity=100, side="buy"), evidence())

    with pytest.raises(ResearchValidationError, match="confidence"):
        validate_research_call(call(confidence="1.20"), evidence())
