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


def test_nearby_observations_use_route_specific_ml_and_uncovered_profile(tmp_path, monkeypatch):
    dataset = tmp_path / "lighting.csv"
    save_records(dataset, [
        record("LIGHT-1", 77.59, 20, density=3),
        record("LIGHT-2", 77.63, 85, density=8),
    ])

    class FittedModel:
        def predict(self, features):
            return features["streetlight_density"].to_numpy() * 10

    monkeypatch.setattr(lighting_ml, "load_model", lambda: (
        {"model": FittedModel(), "metadata": {"status": "TRAINED"}}, "trained"))
    first = lighting_ml.score_route_lighting(route(77.59), dataset_path=dataset)
    second = lighting_ml.score_route_lighting(route(77.63), dataset_path=dataset)
    uncovered = lighting_ml.score_route_lighting(
        route(90.0, latitude=20.0), dataset_path=dataset)

    assert first["lighting_score"] == 30
    assert second["lighting_score"] == 80
    assert first["lighting_score"] != second["lighting_score"]
    assert first["lighting_source"] == second["lighting_source"] == "demo_ml_nearby"
    assert first["lighting_sample_count"] == second["lighting_sample_count"] == 1
    assert uncovered["lighting_score"] is not None
    assert 0 <= uncovered["lighting_score"] <= 100
    assert uncovered["lighting_source"] == "demo_ml_synthetic_profile"
    assert uncovered["lighting_sample_count"] == 0


def test_synthetic_profile_is_stable_and_changes_with_geometry_mode_and_seed():
    geometry = route(77.59)["geometry"]
    profile = lighting_ml.synthetic_route_profile(geometry, "walk", 20261009)
    assert profile == lighting_ml.synthetic_route_profile(geometry, "walk", 20261009)
    assert profile != lighting_ml.synthetic_route_profile(geometry, "drive", 20261009)
    assert profile != lighting_ml.synthetic_route_profile(geometry, "walk", 20261010)
    assert profile != lighting_ml.synthetic_route_profile(
        route(90.0, latitude=20.0)["geometry"], "walk", 20261009)
    assert 1 <= profile["streetlight_density"] <= 24
    assert 0 <= profile["ambient_light_index"] <= 100


def test_no_model_uses_stable_bounded_route_specific_rule_fallback(tmp_path, monkeypatch):
    lighting_ml._read_dataset.cache_clear()
    monkeypatch.setattr(lighting_ml, "load_model", lambda: (None, "unavailable"))
    first_route = route(90.0, latitude=20.0)
    second_route = route(90.2, latitude=20.0)
    first = lighting_ml.score_route_lighting(first_route, "walk", tmp_path / "absent.csv")
    refresh = lighting_ml.score_route_lighting(first_route, "walk", tmp_path / "absent.csv")
    second = lighting_ml.score_route_lighting(second_route, "walk", tmp_path / "absent.csv")

    assert first["lighting_source"] == "demo_rule_fallback"
    assert first["lighting_score"] == refresh["lighting_score"]
    assert first["lighting_score"] != second["lighting_score"]
    assert first["lighting_sample_count"] == second["lighting_sample_count"] == 0
    assert all(0 <= result["lighting_score"] <= 100 for result in (first, refresh, second))


@pytest.mark.parametrize("route_count", [1, 2, 3])
def test_one_two_and_three_routes_all_get_numeric_lighting(tmp_path, monkeypatch, route_count):
    lighting_ml._read_dataset.cache_clear()
    class FittedModel:
        def predict(self, features):
            return features["streetlight_density"].to_numpy() * 4

    monkeypatch.setattr(lighting_ml, "load_model", lambda: (
        {"model": FittedModel(), "metadata": {"status": "TRAINED"}}, "trained"))
    routes = [route(90.0 + index * 0.1, latitude=20.0) for index in range(route_count)]
    results = [lighting_ml.score_route_lighting(item, "bicycle", tmp_path / "absent.csv")
               for item in routes]
    assert len(results) == route_count
    assert all(isinstance(result["lighting_score"], float) for result in results)
    assert all(0 <= result["lighting_score"] <= 100 for result in results)
    assert all(result["lighting_source"] == "demo_ml_synthetic_profile" for result in results)
    if route_count > 1:
        assert len({result["lighting_score"] for result in results}) > 1


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
            route(records[0]["longitude"], records[0]["latitude"]), dataset_path=dataset_path)
        assert loaded_score["lighting_source"] == "demo_ml_nearby"
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
    result = lighting_ml.score_route_lighting(route(77.59), dataset_path=tmp_path / "absent.csv")
    assert isinstance(result["lighting_score"], float)
    assert 0 <= result["lighting_score"] <= 100
    assert result["lighting_source"] == "demo_rule_fallback"
    lighting_ml.load_model.cache_clear()
