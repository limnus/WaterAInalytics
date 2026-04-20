from __future__ import annotations

from typing import Any

from core.forecast_models.paths import model_dir


def build_article_artifact_validation(*, station_id: str, parameter_code: str, model_key: str) -> dict[str, Any]:
    art_dir = model_dir(station_id, parameter=str(parameter_code), model_key=model_key)
    validation = {
        "station_id": station_id,
        "parameter": str(parameter_code),
        "model_key": model_key,
        "artifacts_dir": str(art_dir),
        "exists": art_dir.exists(),
        "required_files": [],
    }

    if model_key == "ridge":
        required = ["meta.json", "weights.npz", "training_manifest.json"]
    else:
        required = []

    validation["required_files"] = [
        {
            "name": name,
            "present": (art_dir / name).exists(),
            "path": str(art_dir / name),
        }
        for name in required
    ]
    validation["all_required_present"] = all(item["present"] for item in validation["required_files"])
    return validation


def validate_article_model_artifacts_or_raise(*, station_id: str, parameter_code: str, model_key: str) -> dict[str, Any]:
    validation = build_article_artifact_validation(
        station_id=station_id,
        parameter_code=parameter_code,
        model_key=model_key,
    )
    if validation["all_required_present"]:
        return validation

    missing = [item["name"] for item in validation["required_files"] if not item["present"]]
    missing_str = ", ".join(missing) if missing else "required model artifacts"
    raise FileNotFoundError(
        f"Article mode requires trained artifacts for model '{model_key}' on station '{station_id}' "
        f"parameter '{parameter_code}'. Missing: {missing_str}. "
        "Train and freeze the requested model before running the paper preset."
    )
