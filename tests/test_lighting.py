import csv
import json
import math

import pytest

from app.services import lighting_ml


def route(longitude, latitude=12.97, end_offset=0.001, duration=600, distance_m=1000):
    return {
        "geometry": {
            "type": "LineString",
            "coordinates": [[longitude, latitude], [longitude + end_offset, latitude]],
        },
        "duration": duration,
        "distance": distance_m,
    }


def record(record_id, longitude, score, density=5):
    return {
        "record_id": record_id,
        "latitude": 12.97,
        "longitude": longitude,
        "city": "Test city",
        "state": "Test state",
        "road_type": "residential",
        "time_period": "night",
        "streetlight_density": density,
        "ambient_light_index": 50,
        "tree_canopy_percent": 20,
        "road_width_m": 8,
        "built_density": 60,
        "lighting_condition": "moderate",
        "lighting_score": score,
        "observation_type": "SYNTHETIC_DEMO",
    }


def save_records(path, records):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=lighting_ml.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)
    lighting_ml._read_dataset.cache_clear()


def test_dataset_generation_is_fixed_seed_complete_and_bounded():
    first = lighting_ml.generate_demo_records()
    second = lighting_ml.generate_demo_records()
    assert first == second
    assert len(first) == 180
    assert {row["state"] for row in first} == {region[0] for region in lighting_ml.REGIONS}
    assert len({row["state"] for row in first}) == 36
    assert all(row["observation_type"] == "SYNTHETIC_DEMO" for row in first)
    assert all(0 <= row["lighting_score"] <= 100 for row in first)
    assert all(row["lighting_condition"] in {"poor", "moderate", "good"} for row in first)


def test_csv_generation_is_reproducible(tmp_path):
    first_path, second_path = tmp_path / "first.csv", tmp_path / "second.csv"
    lighting_ml.write_demo_dataset(first_path)
    lighting_ml.write_demo_dataset(second_path)
    assert first_path.read_bytes() == second_path.read_bytes()
    with first_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 180
    assert all(row["observation_type"] == "SYNTHETIC_DEMO" for row in rows)


def test_feature_schema_excludes_target_labels_and_identifiers():
    features = set(lighting_ml.FEATURE_COLUMNS)
    assert lighting_ml.TARGET_COLUMN not in features
    assert "lighting_condition" not in features
    assert "record_id" not in features
    assert not {"city", "state", "latitude", "longitude"} & features
    assert lighting_ml.FEATURE_SCHEMA["target"] == "lighting_score"


def test_route_specific_weighted_fallback_and_uncovered_route(tmp_path, monkeypatch):
    dataset = tmp_path / "lighting.csv"
    save_records(dataset, [
        record("LIGHT-1", 77.59, 20, density=3),
        record("LIGHT-2", 77.63, 85, density=8),
    ])
    monkeypatch.setattr(lighting_ml, "load_model", lambda: (None, "not_trained"))

    first = lighting_ml.score_route_lighting(route(77.59), dataset)
    second = lighting_ml.score_route_lighting(route(77.63), dataset)
    uncovered = lighting_ml.score_route_lighting(route(77.70), dataset)

    assert first["lighting_score"] == 20
    assert second["lighting_score"] == 85
    assert first["lighting_score"] != second["lighting_score"]
    assert first["lighting_source"] == second["lighting_source"] == "demo_data_fallback"
    assert first["lighting_sample_count"] == second["lighting_sample_count"] == 1
    assert uncovered["lighting_score"] is None
    assert uncovered["lighting_source"] == "unavailable"
    assert uncovered["lighting_sample_count"] == 0


def test_ml_prediction_contract_and_score_bounds(tmp_path, monkeypatch):
    dataset = tmp_path / "lighting.csv"
    save_records(dataset, [
        record("LIGHT-1", 77.59, 20, density=3),
        record("LIGHT-2", 77.63, 85, density=8),
    ])

    class FittedModel:
        def predict(self, features):
            return [features.iloc[0]["streetlight_density"] * 20]

    monkeypatch.setattr(lighting_ml, "load_model", lambda: (
        {"model": FittedModel(), "metadata": {"status": "TRAINED"}}, "trained"))
    low = lighting_ml.score_route_lighting(route(77.59), dataset)
    high = lighting_ml.score_route_lighting(route(77.63), dataset)

    assert low["lighting_score"] == 60
    assert high["lighting_score"] == 100
    assert low["lighting_source"] == high["lighting_source"] == "demo_ml_estimate"
    assert 0 <= low["lighting_score"] <= 100
    assert 0 <= high["lighting_score"] <= 100


def test_training_and_prediction_metrics_when_native_runtime_is_available(tmp_path, monkeypatch):
    try:
        from sklearn.ensemble import RandomForestRegressor
    except (ImportError, OSError) as error:
        pytest.skip(f"scikit-learn native runtime is blocked by local Application Control: {error}")
    assert RandomForestRegressor
    records = lighting_ml.generate_demo_records()
    model_path, metadata_path = tmp_path / "model.joblib", tmp_path / "metadata.json"
    dataset_path = tmp_path / "lighting.csv"
    save_records(dataset_path, records)
    model, metrics, metadata = lighting_ml.train_and_evaluate(records, model_path, metadata_path)
    assert metadata["status"] == "TRAINED"
    assert metadata["train_records"] + metadata["test_records"] == len(records)
    assert all(value >= 0 for value in (metrics["mae"], metrics["rmse"]))
    assert math.isfinite(metrics["r2"])
    assert metadata["evaluation_label"] == "Performance on SYNTHETIC DEMO DATA only; not real-world accuracy."
    assert model_path.is_file()
    assert json.loads(metadata_path.read_text(encoding="utf-8"))["metrics"] == metrics

    import pandas as pd

    feature = {name: records[0][name] for name in lighting_ml.FEATURE_COLUMNS}
    prediction = float(model.predict(pd.DataFrame([feature]))[0])
    assert 0 <= prediction <= 100
    monkeypatch.setattr(lighting_ml, "MODEL_PATH", model_path)
    lighting_ml.load_model.cache_clear()
    try:
        loaded_score = lighting_ml.score_route_lighting(
            route(records[0]["longitude"], records[0]["latitude"]), dataset_path)
        assert loaded_score["lighting_source"] == "demo_ml_estimate"
        assert 0 <= loaded_score["lighting_score"] <= 100
    finally:
        lighting_ml.load_model.cache_clear()


def rated_route(safety, crime, light, duration, distance_m):
    return {
        "duration": duration,
        "distance": distance_m,
        "demo": {"demo_safety_score": safety, "demo_crime_index": crime},
        "lighting": {"lighting_score": light},
    }


@pytest.mark.parametrize("count", [1, 2, 3])
def test_recommendation_supports_one_two_or_three_routes(count):
    routes = [rated_route(65 + index * 10, 45 - index * 10, 55 + index * 10,
                          600 + index * 30, 1000 + index * 50)
              for index in range(count)]
    lighting_ml.recommend_routes(routes)
    assert sum(route["recommended"] for route in routes) == 1
    assert all(route["recommendation_basis"] == "demo_balanced" for route in routes)


def test_missing_ratings_select_fastest_provider_route():
    slow = rated_route(100, 0, 100, 700, 900)
    fast = rated_route(None, None, None, 500, 1200)
    fast["demo"]["demo_safety_score"] = None
    routes = [slow, fast]
    lighting_ml.recommend_routes(routes)
    assert [route["recommended"] for route in routes] == [False, True]
    assert fast["recommendation_basis"] == "provider_fastest"


def test_recommendation_excludes_unreasonable_detours():
    shortest = rated_route(50, 50, 50, 600, 1000)
    balanced = rated_route(85, 15, 90, 750, 1400)
    detour = rated_route(100, 0, 100, 1200, 2500)
    routes = [shortest, balanced, detour]
    lighting_ml.recommend_routes(routes)
    assert balanced["recommended"]
    assert not detour["recommended"]
    assert "1.5×" in balanced["recommendation_reason"]


def test_missing_dataset_and_missing_artifact_are_not_fabricated(tmp_path, monkeypatch):
    lighting_ml._read_dataset.cache_clear()
    monkeypatch.setattr(lighting_ml, "MODEL_PATH", tmp_path / "missing-model.joblib")
    lighting_ml.load_model.cache_clear()
    assert lighting_ml.load_model() == (None, "not_trained")
    result = lighting_ml.score_route_lighting(route(77.59), tmp_path / "absent.csv")
    assert result["lighting_score"] is None
    assert result["lighting_label"] == "DEMO lighting unavailable"
    lighting_ml.load_model.cache_clear()
