import pytest

from app.services import demo_service


def test_demo_metrics_use_new_samples(monkeypatch):
    original = demo_service.load_demo_records
    monkeypatch.setattr(demo_service, 'load_demo_records', lambda filename, column: original(filename, column)[:2])
    result = demo_service.analyze_demo_route({
        "type": "LineString",
        "coordinates": [[78.4990, 17.4405], [78.5000, 17.4425]],
    })
    assert result["demo_safety_score"] == 73
    assert result["demo_crime_index"] == 27
    assert result["status"] == "DEMO_RECORDS_FOUND"
    assert "working_light_count" not in result


def test_no_nearby_samples_remains_unknown():
    result = demo_service.analyze_demo_route({
        "type": "LineString", "coordinates": [[0, 0], [0.01, 0.01]],
    })
    assert result["demo_safety_score"] is None
    assert result["demo_crime_index"] is None
    assert result["status"] == "NO_DEMO_RECORDS_NEAR_ROUTE"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "101"])
def test_invalid_metric_rejected(tmp_path, monkeypatch, value):
    monkeypatch.setattr(demo_service, "DEMO_FOLDER", tmp_path)
    (tmp_path / "safety.csv").write_text(
        "safety_id,latitude,longitude,safety_score,date,source\n"
        f"S-1,17.4,78.4,{value},2026-10-01,synthetic_demo\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid safety_score"):
        demo_service.load_demo_records("safety.csv", "safety_id")


def test_same_samples_weighted_by_each_route(monkeypatch):
    def records(filename, column):
        metric = 'safety_score' if filename == 'safety.csv' else 'crime_rate'
        return [
            {column: 'A', 'point': [0, 0], 'radius_meters': 2000, metric: 90},
            {column: 'B', 'point': [0, 0.01], 'radius_meters': 2000, metric: 10},
        ]
    monkeypatch.setattr(demo_service, 'load_demo_records', records)
    first = demo_service.analyze_demo_route({'type': 'LineString', 'coordinates': [[-0.01, 0], [0.01, 0]]})
    second = demo_service.analyze_demo_route({'type': 'LineString', 'coordinates': [[-0.01, 0.01], [0.01, 0.01]]})
    assert first['safety_sample_ids'] == second['safety_sample_ids']
    assert first['demo_safety_score'] > second['demo_safety_score']


def test_zero_demo_values_are_preserved(monkeypatch):
    def records(filename, column):
        metric = 'safety_score' if filename == 'safety.csv' else 'crime_rate'
        return [{column: 'ZERO', 'point': [0, 0], 'radius_meters': 250, metric: 0}]

    monkeypatch.setattr(demo_service, 'load_demo_records', records)
    result = demo_service.analyze_demo_route({
        'type': 'LineString',
        'coordinates': [[-0.001, 0], [0.001, 0]],
    })
    assert result['demo_safety_score'] == 0
    assert result['demo_crime_index'] == 0
