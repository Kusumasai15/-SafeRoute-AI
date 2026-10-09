"""Synthetic India-wide lighting data and its optional supervised demo model."""
import csv
import json
import logging
import math
import platform
from functools import lru_cache
from pathlib import Path

import numpy as np

from .demo_service import route_segments
from .geoapify import point_segment_distance

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "demo_data" / "lighting.csv"
MODEL_PATH = ROOT / "demo_data" / "lighting_model.joblib"
METADATA_PATH = ROOT / "demo_data" / "lighting_model_metadata.json"
DATASET_SEED = 20261009
OBSERVATION_RADIUS_METERS = 1500

CATEGORICAL_FEATURES = ("road_type", "time_period")
NUMERIC_FEATURES = (
    "streetlight_density",
    "ambient_light_index",
    "tree_canopy_percent",
    "road_width_m",
    "built_density",
)
FEATURE_COLUMNS = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET_COLUMN = "lighting_score"
FEATURE_SCHEMA = {
    "categorical": list(CATEGORICAL_FEATURES),
    "numeric": list(NUMERIC_FEATURES),
    "target": TARGET_COLUMN,
    "excluded": ["record_id", "city", "state", "latitude", "longitude", "lighting_condition"],
}

REGIONS = (
    ("Andhra Pradesh", "Visakhapatnam", 17.6868, 83.2185),
    ("Arunachal Pradesh", "Itanagar", 27.0844, 93.6053),
    ("Assam", "Guwahati", 26.1445, 91.7362),
    ("Bihar", "Patna", 25.5941, 85.1376),
    ("Chhattisgarh", "Raipur", 21.2514, 81.6296),
    ("Goa", "Panaji", 15.4909, 73.8278),
    ("Gujarat", "Ahmedabad", 23.0225, 72.5714),
    ("Haryana", "Gurugram", 28.4595, 77.0266),
    ("Himachal Pradesh", "Shimla", 31.1048, 77.1734),
    ("Jharkhand", "Ranchi", 23.3441, 85.3096),
    ("Karnataka", "Bengaluru", 12.9716, 77.5946),
    ("Kerala", "Kochi", 9.9312, 76.2673),
    ("Madhya Pradesh", "Bhopal", 23.2599, 77.4126),
    ("Maharashtra", "Mumbai", 19.0760, 72.8777),
    ("Manipur", "Imphal", 24.8170, 93.9368),
    ("Meghalaya", "Shillong", 25.5788, 91.8933),
    ("Mizoram", "Aizawl", 23.7271, 92.7176),
    ("Nagaland", "Kohima", 25.6751, 94.1086),
    ("Odisha", "Bhubaneswar", 20.2961, 85.8245),
    ("Punjab", "Ludhiana", 30.9010, 75.8573),
    ("Rajasthan", "Jaipur", 26.9124, 75.7873),
    ("Sikkim", "Gangtok", 27.3389, 88.6065),
    ("Tamil Nadu", "Chennai", 13.0827, 80.2707),
    ("Telangana", "Hyderabad", 17.3850, 78.4867),
    ("Tripura", "Agartala", 23.8315, 91.2868),
    ("Uttar Pradesh", "Lucknow", 26.8467, 80.9462),
    ("Uttarakhand", "Dehradun", 30.3165, 78.0322),
    ("West Bengal", "Kolkata", 22.5726, 88.3639),
    ("Andaman and Nicobar Islands", "Port Blair", 11.6234, 92.7265),
    ("Chandigarh", "Chandigarh", 30.7333, 76.7794),
    ("Dadra and Nagar Haveli and Daman and Diu", "Daman", 20.3974, 72.8328),
    ("Delhi", "New Delhi", 28.6139, 77.2090),
    ("Jammu and Kashmir", "Srinagar", 34.0837, 74.7973),
    ("Ladakh", "Leh", 34.1526, 77.5771),
    ("Lakshadweep", "Kavaratti", 10.5667, 72.6417),
    ("Puducherry", "Puducherry", 11.9416, 79.8083),
)

ROAD_ADJUSTMENT = {
    "residential": 2,
    "collector": 4,
    "arterial": 1,
    "highway": 3,
    "market": 0,
    "rural": -6,
}
TIME_ADJUSTMENT = {"day": 12, "dusk": 0, "night": -12}
CSV_FIELDS = (
    "record_id",
    "latitude",
    "longitude",
    "city",
    "state",
    "road_type",
    "time_period",
    *NUMERIC_FEATURES,
    "lighting_condition",
    "lighting_score",
    "observation_type",
)


def generate_demo_records(seed=DATASET_SEED, observations_per_region=5):
    """Generate fictional labels from a documented formula plus Gaussian noise."""
    if observations_per_region < 1:
        raise ValueError("At least one synthetic observation per region is required.")
    rng = np.random.default_rng(seed)
    road_types = tuple(ROAD_ADJUSTMENT)
    time_periods = tuple(TIME_ADJUSTMENT)
    records = []
    for state, city, center_latitude, center_longitude in REGIONS:
        for _ in range(observations_per_region):
            road_type = str(rng.choice(road_types))
            time_period = str(rng.choice(time_periods))
            density = round(float(rng.uniform(1, 24)), 1)
            ambient = round(float(rng.uniform(0, 100)), 1)
            canopy = round(float(rng.uniform(0, 75)), 1)
            width = round(float(rng.uniform(3, 20)), 1)
            built = round(float(rng.uniform(0, 100)), 1)
            noise = float(rng.normal(0, 5.5))

            # Formula: 30 + 2.2*density + .25*ambient - .18*canopy
            # + .35*width + .12*built + road/time adjustments + N(0, 5.5).
            score = round(min(100, max(0, 30 + 2.2 * density + 0.25 * ambient
                                       - 0.18 * canopy + 0.35 * width + 0.12 * built
                                       + ROAD_ADJUSTMENT[road_type]
                                       + TIME_ADJUSTMENT[time_period] + noise)), 1)
            condition = "poor" if score < 35 else "moderate" if score < 65 else "good"
            latitude = center_latitude + float(rng.uniform(-0.008, 0.008))
            longitude = center_longitude + float(rng.uniform(-0.010, 0.010))
            records.append({
                "record_id": f"LIGHT-{len(records) + 1:04d}",
                "latitude": round(latitude, 6),
                "longitude": round(longitude, 6),
                "city": city,
                "state": state,
                "road_type": road_type,
                "time_period": time_period,
                "streetlight_density": density,
                "ambient_light_index": ambient,
                "tree_canopy_percent": canopy,
                "road_width_m": width,
                "built_density": built,
                "lighting_condition": condition,
                "lighting_score": score,
                "observation_type": "SYNTHETIC_DEMO",
            })
    return records


def write_demo_dataset(path=DATASET_PATH, seed=DATASET_SEED):
    records = generate_demo_records(seed=seed)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)
    return records


@lru_cache(maxsize=4)
def _read_dataset(path):
    dataset = Path(path)
    if not dataset.is_file():
        logger.warning("Synthetic lighting dataset is missing: %s", dataset)
        return ()
    with dataset.open("r", newline="", encoding="utf-8-sig") as source:
        return tuple(dict(row) for row in csv.DictReader(source))


@lru_cache(maxsize=1)
def load_model():
    """Load only a trusted, pre-trained artifact; never train in a web request."""
    if not MODEL_PATH.is_file():
        return None, "not_trained"
    try:
        import joblib
        import pandas as pd
        import sklearn

        artifact = joblib.load(MODEL_PATH)
        metadata = artifact["metadata"]
        if artifact.get("feature_schema") != FEATURE_SCHEMA:
            raise ValueError("Lighting model feature schema does not match this application.")
        if metadata.get("status") != "TRAINED":
            raise ValueError("Lighting model metadata does not mark a fitted model as trained.")
        if metadata.get("scikit_learn_version") != sklearn.__version__:
            raise ValueError("Lighting model scikit-learn version does not match the runtime.")
        if metadata.get("numpy_version") != np.__version__:
            raise ValueError("Lighting model NumPy version does not match the runtime.")
        if metadata.get("pandas_version") != pd.__version__:
            raise ValueError("Lighting model Pandas version does not match the runtime.")
        if metadata.get("joblib_version") != joblib.__version__:
            raise ValueError("Lighting model Joblib version does not match the runtime.")
        if not hasattr(artifact.get("model"), "predict"):
            raise ValueError("Lighting model artifact has no prediction interface.")
        return artifact, "trained"
    except (ImportError, OSError, EOFError, ValueError, KeyError, AttributeError) as error:
        logger.warning("Pre-trained lighting model unavailable; using labeled demo-data fallback: %s", error)
        return None, "unavailable"


def score_route_lighting(route, dataset_path=DATASET_PATH):
    """Aggregate nearby records independently for one route using distance weights."""
    segments = route_segments(route["geometry"])
    if not segments:
        raise ValueError("Route has no usable geometry for lighting scoring.")

    nearby = []
    for row in _read_dataset(str(Path(dataset_path).resolve())):
        try:
            if row.get("observation_type") != "SYNTHETIC_DEMO":
                raise ValueError("observation_type must be SYNTHETIC_DEMO")
            if row.get("road_type") not in ROAD_ADJUSTMENT or row.get("time_period") not in TIME_ADJUSTMENT:
                raise ValueError("unknown road_type or time_period")
            point = [float(row["longitude"]), float(row["latitude"])]
            if (not all(math.isfinite(value) for value in point)
                    or not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90):
                raise ValueError("invalid coordinates")
            score = float(row["lighting_score"])
            if not math.isfinite(score) or not 0 <= score <= 100:
                raise ValueError("lighting_score must be between 0 and 100")
            for name in NUMERIC_FEATURES:
                value = float(row[name])
                if not math.isfinite(value):
                    raise ValueError(f"{name} must be finite")
            route_distance = min(point_segment_distance(point, start, end) for start, end in segments)
            if route_distance <= OBSERVATION_RADIUS_METERS:
                nearby.append((row, route_distance, 1 / (1 + route_distance / 250) ** 2))
        except (KeyError, TypeError, ValueError) as error:
            logger.warning("Ignoring invalid synthetic lighting record %s: %s",
                           row.get("record_id", "<unknown>"), error)
            continue

    result = {
        "is_demo": True,
        "lighting_score": None,
        "lighting_source": "unavailable",
        "lighting_label": "DEMO lighting unavailable",
        "lighting_sample_count": len(nearby),
        "lighting_radius_meters": OBSERVATION_RADIUS_METERS,
    }
    if not nearby:
        return result

    artifact, model_status = load_model()
    if artifact is not None:
        try:
            import pandas as pd

            feature_rows = []
            for row, _, _ in nearby:
                features = {name: row[name] for name in CATEGORICAL_FEATURES}
                features.update({name: float(row[name]) for name in NUMERIC_FEATURES})
                feature_rows.append(features)
            features = pd.DataFrame(feature_rows, columns=FEATURE_COLUMNS)
            predictions = artifact["model"].predict(features)
            values = [min(100.0, max(0.0, float(value))) for value in predictions]
            source = "demo_ml_estimate"
            label = "DEMO ML estimate"
        except (ImportError, OSError, ValueError, RuntimeError) as error:
            logger.warning("Lighting model prediction failed; using labeled demo-data fallback: %s", error)
            artifact = None
            model_status = "unavailable"

    if artifact is None:
        source = "demo_data_fallback"
        label = "DEMO data fallback"
        values = [float(row["lighting_score"]) for row, _, _ in nearby]

    total_weight = sum(weight for _, _, weight in nearby)
    result.update(
        lighting_score=round(sum(value * weight for value, (_, _, weight) in zip(values, nearby))
                             / total_weight, 1),
        lighting_source=source,
        lighting_label=label,
        model_status=model_status,
    )
    return result


def recommend_routes(routes):
    """Set one recommendation using demo scores, travel time, and route length."""
    if not routes:
        return
    fastest = min(routes, key=lambda route: (route["duration"], route["distance"]))
    required_scores = ("demo_safety_score", "demo_crime_index")
    ratings_available = all(
        isinstance(route.get("demo", {}).get(key), (int, float))
        and math.isfinite(route["demo"][key])
        and isinstance(route.get("lighting", {}).get("lighting_score"), (int, float))
        and math.isfinite(route["lighting"]["lighting_score"])
        for route in routes
        for key in required_scores
    )
    if not ratings_available:
        recommended = fastest
        basis = "provider_fastest"
        reason = "A DEMO rating is unavailable; selected the provider's fastest route."
    else:
        fastest_time = fastest["duration"]
        shortest_distance = min(route["distance"] for route in routes)
        eligible = [
            route for route in routes
            if route["duration"] <= fastest_time * 1.5
            and route["distance"] <= shortest_distance * 1.5
        ]
        if not eligible:
            eligible = [fastest]

        def score(route):
            safety = route["demo"]["demo_safety_score"]
            crime_safety = 100 - route["demo"]["demo_crime_index"]
            lighting = route["lighting"]["lighting_score"]
            time_score = 100 * fastest_time / route["duration"] if route["duration"] else 100
            distance_score = 100 * shortest_distance / route["distance"]
            return 0.35 * safety + 0.25 * crime_safety + 0.25 * lighting + 0.10 * time_score + 0.05 * distance_score

        recommended = max(eligible, key=lambda route: (score(route), -route["duration"], -route["distance"]))
        basis = "demo_balanced"
        reason = (
            "DEMO formula: 35% safety + 25% (100 − crime risk) + 25% lighting "
            "+ 10% relative travel time + 5% relative distance; routes over "
            "1.5× the fastest time or shortest distance are excluded."
        )

    for route in routes:
        route["recommended"] = route is recommended
        route["recommendation_basis"] = basis
        if route is recommended:
            route["recommendation_reason"] = reason


def train_and_evaluate(records, model_path=MODEL_PATH, metadata_path=METADATA_PATH):
    """Fit and evaluate the real scikit-learn RandomForest pipeline."""
    import joblib
    import pandas as pd
    import sklearn
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    frame = pd.DataFrame(records)
    if TARGET_COLUMN not in frame or any(column not in frame for column in FEATURE_COLUMNS):
        raise ValueError("Training data is missing required feature or target columns.")
    if any(column in FEATURE_COLUMNS for column in (TARGET_COLUMN, "record_id", "lighting_condition")):
        raise ValueError("Target, identifier, and target-derived fields cannot be model inputs.")
    if len(frame) < 20:
        raise ValueError("At least 20 synthetic records are required to split train and test data.")

    x_train, x_test, y_train, y_test = train_test_split(
        frame.loc[:, FEATURE_COLUMNS],
        frame[TARGET_COLUMN].astype(float),
        test_size=0.25,
        random_state=42,
    )
    preprocessing = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore"), list(CATEGORICAL_FEATURES)),
        ("numeric", "passthrough", list(NUMERIC_FEATURES)),
    ])
    model = Pipeline([
        ("features", preprocessing),
        ("regressor", RandomForestRegressor(
            n_estimators=250, min_samples_leaf=2, random_state=42, n_jobs=1,
        )),
    ])
    model.fit(x_train, y_train)
    predictions = np.clip(model.predict(x_test), 0, 100)
    metrics = {
        "mae": float(mean_absolute_error(y_test, predictions)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, predictions))),
        "r2": float(r2_score(y_test, predictions)),
    }
    metadata = {
        "status": "TRAINED",
        "algorithm": "RandomForestRegressor",
        "dataset": "demo_data/lighting.csv",
        "dataset_records": len(frame),
        "train_records": len(x_train),
        "test_records": len(x_test),
        "dataset_seed": DATASET_SEED,
        "split_random_state": 42,
        "feature_schema": FEATURE_SCHEMA,
        "label_generation": (
            "lighting_score = clip(30 + 2.2*streetlight_density + 0.25*ambient_light_index "
            "- 0.18*tree_canopy_percent + 0.35*road_width_m + 0.12*built_density "
            "+ road adjustment + time adjustment + Gaussian N(0, 5.5), 0, 100); "
            "lighting_condition is derived from the score and excluded from features."
        ),
        "evaluation_label": "Performance on SYNTHETIC DEMO DATA only; not real-world accuracy.",
        "metrics": metrics,
        "scikit_learn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "joblib_version": joblib.__version__,
        "python_version": platform.python_version(),
        "python_version_family": ".".join(platform.python_version_tuple()[:2]),
    }
    artifact_path = Path(model_path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": model,
        "feature_schema": FEATURE_SCHEMA,
        "metadata": metadata,
    }, artifact_path)
    metadata_file = Path(metadata_path)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    metadata_file.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    load_model.cache_clear()
    return model, metrics, metadata
