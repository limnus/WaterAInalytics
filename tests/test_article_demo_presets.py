from core.article_demo.presets import get_article_demo_profile


def test_article_demo_profile_from_env(monkeypatch):
    monkeypatch.setenv("ARTICLE_DEMO_ENABLED", "1")
    monkeypatch.setenv("ARTICLE_DEMO_NAME", "Paper demo")
    monkeypatch.setenv("ARTICLE_DEMO_STATION_IDS", "USGS-1, USGS-2,USGS-3")
    monkeypatch.setenv("ARTICLE_DEMO_STATION_LABELS", "Upstream, Midstream, Downstream")
    monkeypatch.setenv("ARTICLE_DEMO_PARAMETER_CODE", "00065")
    monkeypatch.setenv("ARTICLE_DEMO_HISTORY_DAYS", "7")
    monkeypatch.setenv("ARTICLE_DEMO_HORIZON_H", "24")
    monkeypatch.setenv("ARTICLE_DEMO_MODEL_KEY", "ridge")

    profile = get_article_demo_profile()

    assert profile is not None
    assert profile.enabled is True
    assert profile.name == "Paper demo"
    assert profile.station_ids == ["USGS-1", "USGS-2", "USGS-3"]
    assert profile.station_labels["USGS-2"] == "Midstream"
    assert profile.parameter_code == "00065"
    assert profile.history_days == 7
    assert profile.horizon_h == 24
    assert profile.model_key == "ridge"


def test_article_demo_profile_none_when_disabled(monkeypatch):
    monkeypatch.delenv("ARTICLE_DEMO_ENABLED", raising=False)
    monkeypatch.delenv("ARTICLE_DEMO_STATION_IDS", raising=False)
    assert get_article_demo_profile() is None
