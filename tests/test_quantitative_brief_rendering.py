from core.llm_analysis.llm_agent.quantitative_brief import render_quantitative_brief_markdown


BRIEF = {
    "executive_summary": "Station behavior is stable and the forecast is slightly increasing.",
    "observed_facts": ["Recent variability is low.", "The latest observation is close to the recent mean."],
    "inferences": ["The next predicted value is slightly above the latest observation."],
    "alerts": ["Only short history was available."],
    "limitations": ["No local watershed context was incorporated."],
    "open_questions": ["Would local rainfall data change the interpretation?"],
    "history_stats": {"history_points": 48, "recent_mean": 10.0, "recent_std": 0.5, "trend_label": "roughly stable"},
    "forecast_stats": {"horizon_count": 24, "first_pred": 10.4, "uncertainty_label": "moderate"},
}


def test_render_quantitative_brief_narrative_is_flowing_text():
    md = render_quantitative_brief_markdown(BRIEF, format_style="narrative", focus_text="emphasize uncertainty")
    assert "#### Narrative Summary" in md
    assert "Requested focus: emphasize uncertainty." in md
    assert "Observed facts:" in md
    assert "Interpretive inferences:" in md
    assert "Alerts:" in md
    assert "- Recent variability" not in md


def test_render_quantitative_brief_structured_keeps_bullets_and_focus_section():
    md = render_quantitative_brief_markdown(BRIEF, format_style="structured", focus_text="operations")
    assert "#### Requested Focus" in md
    assert "#### Observed Facts" in md
    assert "#### Interpretive Inferences" in md
    assert "#### Alerts" in md
    assert "- Recent variability is low." in md


def test_render_quantitative_brief_technical_adds_diagnostics():
    md = render_quantitative_brief_markdown(BRIEF, format_style="technical")
    assert "#### Technical Summary" in md
    assert "#### Diagnostics" in md
    assert "- History points = 48" in md
