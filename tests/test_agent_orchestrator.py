"""Unit coverage for the deep-agents orchestration layer."""

from types import SimpleNamespace

from app.services.agent_orchestrator import (
    SECTION_GROUPS_MAX,
    _section_groups,
    _UsageCollector,
)


def test_section_groups_split_by_source_and_stem():
    references = {
        "evidence": {
            "E0": {"text": "a", "source": "resume", "path": "summary"},
            "E1": {"text": "b", "source": "resume", "path": "experiences.0.bullets.0"},
            "E2": {"text": "c", "source": "answer", "path": "answers.0"},
            "E3": {"text": "d", "source": "answer", "path": "answers.1"},
        },
        "requirements": {},
        "targets": {},
    }
    groups = _section_groups(references)
    assert set(groups) == {
        "resume:summary",
        "resume:experiences",
        "answer:answers.0",
        "answer:answers.1",
    }


def test_section_groups_merge_tail_beyond_cap():
    references = {"requirements": {}, "targets": {}, "evidence": {}}
    total = SECTION_GROUPS_MAX + 4
    for index in range(total):
        references["evidence"][f"E{index}"] = {
            "text": "x",
            "source": "answer",
            "path": f"answers.{index}",
        }
    groups = _section_groups(references)
    assert len(groups) == SECTION_GROUPS_MAX
    merged = groups["merged:tail"]
    assert len(merged) == 5


def test_usage_collector_reads_langchain_metadata():
    message = SimpleNamespace(
        usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150}
    )
    response = SimpleNamespace(generations=[[SimpleNamespace(message=message)]])
    collector = _UsageCollector()
    collector.on_llm_end(response)
    assert collector.total == 150
    assert collector.calls == [
        {"total": 150, "input": 120, "output": 30, "outcome": "returned"}
    ]


def test_usage_collector_records_provider_errors():
    collector = _UsageCollector()
    collector.on_llm_error(Exception())
    assert collector.calls == [
        {"total": None, "input": None, "output": None, "outcome": "provider_error"}
    ]
    assert collector.total == 0


def test_orchestrator_flag_defaults_off(app):
    assert not app.config.get("DIAGNOSIS_AGENT_ENABLED")


def test_extract_structured_validates_writer_output():
    from langchain_core.messages import ToolMessage

    from app.services.agent_orchestrator import SectionFindings, _extract_structured

    payload = '{"findings": []}'
    state = {
        "messages": [
            "human: plan",
            ToolMessage(content=payload, tool_call_id="x"),
        ]
    }
    output = _extract_structured(state, SectionFindings)
    assert output.findings == []


def test_extract_structured_ignores_non_json_messages():
    from langchain_core.messages import ToolMessage

    from app.services.agent_orchestrator import SectionFindings, _extract_structured

    state = {
        "messages": [
            ToolMessage(content="plain text reply", tool_call_id="x"),
        ]
    }
    assert _extract_structured(state, SectionFindings) is None
