import csv
import math
from datetime import date
from pathlib import Path

from .geoapify import point_segment_distance


DEMO_FOLDER = Path(__file__).resolve().parents[2] / "demo_data"


def load_demo_records(filename, id_column):
    """Read demo data; reject missing or invalid records."""
    path = DEMO_FOLDER / filename

    if not path.is_file():
        raise ValueError(f"Demo file missing: {filename}")

    records = []
    seen_ids = set()

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for line_number, row in enumerate(csv.DictReader(file), start=2):
            try:
                record_id = row[id_column].strip()

                if not record_id or record_id in seen_ids:
                    raise ValueError("Missing or duplicate ID")

                if row["source"].strip() != "synthetic_demo":
                    raise ValueError("Only synthetic demo records are allowed")

                date.fromisoformat(row["date"].strip())

                latitude = float(row["latitude"])
                longitude = float(row["longitude"])

                if (
                    not math.isfinite(latitude)
                    or not math.isfinite(longitude)
                    or not -90 <= latitude <= 90
                    or not -180 <= longitude <= 180
                ):
                    raise ValueError("Invalid coordinates")

                metric = {
                    "safety.csv": "safety_score",
                    "crime.csv": "crime_rate",
                }.get(filename)
                if metric:
                    value = float(row[metric])
                    if not math.isfinite(value) or not 0 <= value <= 100:
                        raise ValueError(f"Invalid {metric}: expected 0 to 100")
                    row[metric] = value

                radius = float(row.get("radius_meters") or 250)
                if not math.isfinite(radius) or not 0 < radius <= 8000:
                    raise ValueError("Invalid sample radius")
                row["radius_meters"] = radius

                row["point"] = [longitude, latitude]
                records.append(row)
                seen_ids.add(record_id)

            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid demo record in {filename}, "
                    f"line {line_number}: {error}"
                ) from error

    if not records:
        raise ValueError(f"No demo records found in {filename}")

    return records


def route_segments(geometry):
    """Keep separate route parts separate."""
    if geometry["type"] == "LineString":
        parts = [geometry["coordinates"]]
    elif geometry["type"] == "MultiLineString":
        parts = geometry["coordinates"]
    else:
        raise ValueError("Unsupported route geometry")

    return [
        (start, end)
        for part in parts
        for start, end in zip(part, part[1:])
    ]


def analyze_demo_route(geometry):
    """Average fictional samples within their declared matching radii."""
    segments = route_segments(geometry)

    if not segments:
        raise ValueError("Route has no usable segments")

    incidents = load_demo_records("incidents.csv", "incident_id")
    safety_records = load_demo_records("safety.csv", "safety_id")
    crime_records = load_demo_records("crime.csv", "crime_id")

    points = [point for segment in segments for point in segment]
    min_lon, max_lon = min(p[0] for p in points), max(p[0] for p in points)
    min_lat, max_lat = min(p[1] for p in points), max(p[1] for p in points)

    def is_near_route(record):
        lon, lat = record["point"]
        padding_lat = record["radius_meters"] / 111320
        padding_lon = padding_lat / max(abs(math.cos(math.radians(lat))), 0.000001)
        if not (min_lat - padding_lat <= lat <= max_lat + padding_lat
                and min_lon - padding_lon <= lon <= max_lon + padding_lon):
            return False
        record["route_distance_meters"] = min(
            point_segment_distance(record["point"], start, end)
            for start, end in segments
        )
        return record["route_distance_meters"] <= record["radius_meters"]

    nearby_incidents = [
        record for record in incidents if is_near_route(record)
    ]

    nearby_safety = [record for record in safety_records if is_near_route(record)]
    nearby_crime = [record for record in crime_records if is_near_route(record)]
    has_matches = bool(nearby_incidents or nearby_safety or nearby_crime)

    # Nearby samples carry more weight; missing data stays unknown.
    def average(records, metric):
        if not records:
            return None
        weights = [1 / (1 + record["route_distance_meters"] / 250) ** 2 for record in records]
        return round(sum(record[metric] * weight for record, weight in zip(records, weights)) / sum(weights), 1)

    demo_safety_score = average(nearby_safety, "safety_score")
    demo_crime_rate = average(nearby_crime, "crime_rate")

    return {
        "is_demo": True,
        "scoring_method": "Distance-weighted fictional samples; closer samples have more influence.",
        "safety_sample_ids": [record["safety_id"] for record in nearby_safety],
        "crime_sample_ids": [record["crime_id"] for record in nearby_crime],
        "demo_safety_score": demo_safety_score,
        "demo_crime_rate": demo_crime_rate,
        "label": "Synthetic demo â€” not verified safety information",
        "radius_meters": max(
            (record["radius_meters"] for record in nearby_safety + nearby_crime),
            default=250,
        ),
        "incident_count": len(nearby_incidents),
        "status": (
            "DEMO_RECORDS_FOUND"
            if has_matches
            else "NO_DEMO_RECORDS_NEAR_ROUTE"
        ),
        "message": (
            "Nearby fictional records are shown for demonstration only."
            if has_matches
            else "No sample records near this route. Safety is unknown."
        ),
        "safety_score": None,
        "recommendation": None,
    }
