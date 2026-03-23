from core.ui.agentic_flow import AgenticExecutionPlan, build_execution_plan_lines, llm_request_is_runnable


def test_llm_request_is_runnable_only_when_complete():
    assert not llm_request_is_runnable(enabled=False, provider="ollama", model="llama3.2")
    assert not llm_request_is_runnable(enabled=True, provider="off", model="llama3.2")
    assert not llm_request_is_runnable(enabled=True, provider="ollama", model="")
    assert not llm_request_is_runnable(enabled=True, provider="ollama", model="llama3.2", provider_available=False)
    assert llm_request_is_runnable(enabled=True, provider="ollama", model="llama3.2", provider_available=True)


def test_build_execution_plan_lines_reflects_unified_pipeline():
    plan = AgenticExecutionPlan(
        include_station_context=True,
        llm_enabled=True,
        llm_provider="ollama",
        llm_model="gemma3:1b",
    )
    lines = build_execution_plan_lines(plan)
    assert lines[0].startswith("1. Build forecast context")
    assert any("official station context" in line for line in lines)
    assert any("gemma3:1b" in line for line in lines)
    assert lines[-1].startswith("4. Persist artifacts")
