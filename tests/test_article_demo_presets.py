from core.article_demo.presets import get_article_demo_profile, get_article_demo_profiles


def test_article_demo_profiles_from_env_include_core_and_supplement(monkeypatch):
    monkeypatch.setenv("ARTICLE_DEMO_ENABLED", "1")
    monkeypatch.setenv("ARTICLE_DEMO_NAME", "Paper Core — Flow (00060)")
    monkeypatch.setenv("ARTICLE_DEMO_STATION_IDS", "USGS-1, USGS-2,USGS-3")
    monkeypatch.setenv("ARTICLE_DEMO_STATION_LABELS", "Upstream, Midstream, Downstream")
    monkeypatch.setenv("ARTICLE_DEMO_PARAMETER_CODE", "00060")
    monkeypatch.setenv("ARTICLE_DEMO_HISTORY_DAYS", "7")
    monkeypatch.setenv("ARTICLE_DEMO_HORIZON_H", "24")
    monkeypatch.setenv("ARTICLE_DEMO_MODEL_KEY", "ridge")

    profiles = get_article_demo_profiles()

    assert len(profiles) == 2
    core = profiles[0]
    supplement = profiles[1]

    assert core.enabled is True
    assert core.key == "paper-core-flow"
    assert core.name == "Paper Core — Flow (00060)"
    assert core.station_ids == ["USGS-1", "USGS-2", "USGS-3"]
    assert core.station_labels["USGS-2"] == "Midstream"
    assert core.parameter_code == "00060"
    assert core.history_days == 7
    assert core.horizon_h == 24
    assert core.model_key == "ridge"

    assert supplement.key == "paper-supplement-turbidity"
    assert supplement.parameter_code == "63680"
    assert supplement.station_ids == ["USGS-07374525"]
    assert supplement.model_key == "ridge"


def test_article_demo_profile_can_be_selected_by_key(monkeypatch):
    monkeypatch.setenv("ARTICLE_DEMO_ENABLED", "1")
    monkeypatch.setenv("ARTICLE_DEMO_STATION_IDS", "USGS-1")

    profile = get_article_demo_profile("paper-supplement-turbidity")

    assert profile is not None
    assert profile.key == "paper-supplement-turbidity"
    assert profile.parameter_code == "63680"


def test_article_demo_profile_none_when_disabled(monkeypatch):
    monkeypatch.delenv("ARTICLE_DEMO_ENABLED", raising=False)
    monkeypatch.delenv("ARTICLE_DEMO_STATION_IDS", raising=False)
    assert get_article_demo_profile() is None
