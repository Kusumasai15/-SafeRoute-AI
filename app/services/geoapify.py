"""Fixed-host provider adapter. Never expose request URLs or API keys in errors."""
import json
import math
import threading
import time
import requests
from flask import current_app

class ProviderError(Exception):
    def __init__(self, message, status=502):
        self.status = status
        super().__init__(message)

PLACE_CATEGORIES = {
    'service.police': 'Police station',
    'healthcare.hospital': 'Hospital',
    'healthcare.pharmacy': 'Pharmacy',
}
PLACE_CACHE_TTL = 300
PLACE_CACHE_LIMIT = 256
PLACE_QUERY_RADIUS = 5100
_places_cache = {}
_places_cache_lock = threading.Lock()

def fetch(path, params):
    key = current_app.config['GEOAPIFY_API_KEY']
    if not key or key.startswith('replace-'):
        raise ProviderError('Add your Geoapify API key to .env, then restart SafeWalk.', 503)
    try:
        with requests.get('https://api.geoapify.com/' + path,
                          params={**params, 'apiKey': key}, timeout=(5, 20),
                          stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                raise ProviderError('Map provider unavailable or key/quota rejected. Check your Geoapify account.')
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > 5*1024*1024:
                    raise ProviderError('Provider response too large. Try a shorter journey.')
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ProviderError('Unexpected map-provider response.')
            return result
    except (requests.RequestException, ValueError):
        raise ProviderError('Map provider could not be reached. Please retry.') from None

def distance(a, b):
    """Haversine meters, coordinates [longitude, latitude]."""
    lon1, lat1, lon2, lat2 = map(math.radians, [*a, *b])
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))

def nearby_places(latitude, longitude, category=None):
    """Return deduplicated Geoapify facilities no farther than five kilometres."""
    categories = (category,) if category else tuple(PLACE_CATEGORIES)
    cache_latitude, cache_longitude = round(latitude, 3), round(longitude, 3)
    cache_key = (cache_latitude, cache_longitude, category)
    now = time.monotonic()
    with _places_cache_lock:
        cached = _places_cache.get(cache_key)
        if cached and cached[0] > now:
            candidates = cached[1]
        else:
            _places_cache.pop(cache_key, None)
            candidates = None

    if candidates is None:
        params = dict(
            categories=','.join(categories),
            # Pad the rounded cache cell; every returned place is rechecked at the exact center below.
            filter=f'circle:{cache_longitude},{cache_latitude},{PLACE_QUERY_RADIUS}',
            bias=f'proximity:{cache_longitude},{cache_latitude}',
            limit=100,
        )
        result = fetch('v2/places', params)
        candidates = []
        seen = set()
        features = result.get('features')
        if not isinstance(features, list):
            raise ProviderError('Unexpected Places response.')
        for feature in features:
            if not isinstance(feature, dict):
                continue
            properties = feature.get('properties')
            geometry = feature.get('geometry')
            if not isinstance(properties, dict) or not isinstance(geometry, dict):
                continue
            coordinates = geometry.get('coordinates')
            provider_categories = properties.get('categories')
            if (geometry.get('type') != 'Point'
                    or not isinstance(coordinates, list) or len(coordinates) < 2
                    or not isinstance(provider_categories, list)):
                continue
            try:
                place_longitude, place_latitude = map(float, coordinates[:2])
            except (TypeError, ValueError):
                continue
            if (not math.isfinite(place_longitude) or not math.isfinite(place_latitude)
                    or not -180 <= place_longitude <= 180
                    or not -90 <= place_latitude <= 90):
                continue
            place_category = next(
                (item for item in categories if item in provider_categories),
                None,
            )
            if place_category is None:
                continue
            name = properties.get('name') or properties.get('formatted')
            name = name.strip() if isinstance(name, str) else ''
            name = name or f"Unnamed {PLACE_CATEGORIES[place_category].lower()}"
            provider_id = properties.get('place_id')
            identity = (
                ('provider', provider_id) if isinstance(provider_id, str) and provider_id
                else ('location', place_category, round(place_longitude, 5),
                      round(place_latitude, 5), name.casefold())
            )
            if identity in seen:
                continue
            seen.add(identity)
            candidates.append(dict(
                name=name,
                lat=place_latitude,
                lng=place_longitude,
                category=place_category,
                category_label=PLACE_CATEGORIES[place_category],
            ))
        with _places_cache_lock:
            if len(_places_cache) >= PLACE_CACHE_LIMIT:
                oldest = min(_places_cache, key=lambda key: _places_cache[key][0])
                _places_cache.pop(oldest, None)
            _places_cache[cache_key] = (now + PLACE_CACHE_TTL, candidates)

    places = []
    for candidate in candidates:
        meters_away = distance(
            [longitude, latitude],
            [candidate['lng'], candidate['lat']],
        )
        if meters_away <= 5000:
            places.append({
                **candidate,
                'distance': round(meters_away),
                'distance_label': 'straight-line distance',
            })
    return sorted(places, key=lambda place: place['distance'])

def points(geometry):
    if geometry['type'] == 'LineString':
        return geometry['coordinates']
    return [p for part in geometry['coordinates'] for p in part]

def sample(line, count=80):
    """Sample by traveled distance, not by vertex count."""
    lengths = [distance(a, b) for a, b in zip(line, line[1:])]
    total = sum(lengths)
    if total == 0:
        return line[:1]
    output, index, base = [], 0, 0
    for k in range(count):
        target = total*k/(count-1)
        while index < len(lengths)-1 and base+lengths[index] < target:
            base += lengths[index]
            index += 1
        fraction = min(1, max(0, (target-base)/lengths[index])) if lengths[index] else 0
        a, b = line[index], line[index+1]
        output.append([a[0]+fraction*(b[0]-a[0]), a[1]+fraction*(b[1]-a[1])])
    return output

def point_segment_distance(p, a, b):
    scale = math.cos(math.radians(p[1]))
    ax, ay = (a[0]-p[0])*scale*111320, (a[1]-p[1])*111320
    bx, by = (b[0]-p[0])*scale*111320, (b[1]-p[1])*111320
    dx, dy = bx-ax, by-ay
    t = max(0, min(1, -(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx*dx+dy*dy else 0
    return math.hypot(ax+t*dx, ay+t*dy)

def duplicate(a, b):
    la, lb = points(a['geometry']), points(b['geometry'])
    da, db = a['distance'], b['distance']
    if max(da, db) and min(da, db)/max(da, db) < .9:
        return False
    def overlap(source, target):
        sampled = sample(source)
        hits = sum(min(point_segment_distance(p, x, y) for x, y in zip(target, target[1:])) <= 30 for p in sampled)
        return hits/len(sampled) >= .92
    return overlap(la, lb) and overlap(lb, la)

def normalize(feature, preference):
    geometry = feature.get('geometry', {})
    if geometry.get('type') not in ('LineString', 'MultiLineString'):
        raise ProviderError('No usable route geometry returned.')
    try:
        line = points(geometry)
        if not all(isinstance(p, list) and len(p) >= 2 and
                   all(isinstance(v, (int, float)) and math.isfinite(v) for v in p[:2]) and
                   -180 <= p[0] <= 180 and -90 <= p[1] <= 90 for p in line):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ProviderError('Provider returned invalid route coordinates.') from None
    if len(line) < 2 or len(line) > 20000:
        raise ProviderError('Route geometry is missing or too large.')
    props = feature.get('properties', {})
    try:
        route_distance, duration = float(props['distance']), float(props['time'])
        if not math.isfinite(route_distance) or not math.isfinite(duration) or route_distance <= 0 or duration < 0:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ProviderError('Provider returned invalid route distance or time.') from None
    steps = []
    parts = [geometry['coordinates']] if geometry['type'] == 'LineString' else geometry['coordinates']
    offset = 0
    for leg_index, leg in enumerate(props.get('legs', [])):
        part = parts[min(leg_index, len(parts)-1)]
        for step in leg.get('steps', []):
            index = max(0, min(len(part)-1, int(step.get('from_index', 0))))
            instruction = step.get('instruction', {})
            text = instruction.get('text', '') if isinstance(instruction, dict) else (
                instruction if isinstance(instruction, str) else ''
            )
            if not isinstance(text, str) or not text.strip():
                continue
            maneuver_point = part[index]
            steps.append(dict(text=text.strip(), point=maneuver_point,
                              maneuver_point=maneuver_point,
                              index=offset+index, distance=step.get('distance', 0)))
        offset += len(part)
    return dict(geometry=geometry, distance=route_distance,
                duration=duration, steps=steps, preference=preference)

def routes(start, end, mode):
    candidates, warnings = [], []
    for preference in ('balanced', 'short', 'alternative'):
        try:
            params = dict(waypoints=f'{start[0]},{start[1]}|{end[0]},{end[1]}',
                mode=mode, type=preference, details='instruction_details', units='metric', lang='en')
            if preference == 'alternative':
                # Ask the router for another path around the first route's midpoint.
                midpoint = sample(points(candidates[0]['geometry']), count=3)[1]
                params.update(type='balanced', avoid=f'location:{midpoint[1]},{midpoint[0]}')
            result = fetch('v1/routing', params)
            features = result.get('features', [])
            if not features:
                raise ProviderError('No route found for these locations and travel mode.', 404)
            candidate = normalize(features[0], preference)
            if not any(duplicate(candidate, previous) for previous in candidates):
                candidate['id'] = len(candidates)
                candidates.append(candidate)
        except ProviderError:
            if preference == 'balanced':
                raise
            label = 'shorter-route' if preference == 'short' else 'alternative-route'
            warnings.append(f'The {label} request was unavailable; your first route is still usable.')
    if len(candidates) < 3:
        warnings.append(f'Found {len(candidates)} distinct route option(s); three alternatives were not available.')
    return dict(routes=candidates, warnings=warnings)
