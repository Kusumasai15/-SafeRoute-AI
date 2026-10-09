All records in this folder are fictional demo data, not verified safety information.

- `safety.csv`: editable safety scores from 0 to 100; higher means safer in the demo.
- `crime.csv`: editable crime indices in the `crime_rate` column from 0 to 100; higher means more crime in the demo. The API exposes this metric as `demo_crime_index`. These are not measured population or time-based rates.
- `lighting.csv`: 180 reproducible fictional lighting observations (five sample locations in one representative city in each of India's 28 states and 8 union territories). Every row is marked `SYNTHETIC_DEMO`; these are not measured lighting conditions and do not provide complete geographic coverage. Regenerate with `python -m scripts.train_lighting_model` or `write_demo_dataset(seed=20261009)`.
- `lighting_model.joblib`: the fitted RandomForestRegressor and its feature schema/metadata. Flask loads it; training is never done in a request.
- `lighting_model_metadata.json`: training status, held-out synthetic-data metrics, and feature schema. Metrics are explicitly not real-world accuracy.
- `incidents.csv`: fictional sample data retained for the demo; it is not displayed on route cards or used to rank routes.

Safety and crime routes show the distance-weighted average of samples within each record's `radius_meters` of selected route geometry (250 metres if omitted). Lighting is independently aggregated for each route from observations within 1,500 metres using `1 / (1 + distance_to_route / 250 metres)^2`. A route with no nearby synthetic lighting observations stays unknown.

When an offline-trained RandomForest model is available, each matching lighting row is predicted from road type, time period, streetlight density, and synthetic environmental features before distance-weighting. Without it, the application shows an explicitly labeled demo-data fallback. No rating is verified real-world information. If every route has all three scores, a documented score balances safety, lower crime risk, lighting, travel time, and distance while excluding routes over 1.5× the fastest time or shortest distance. If any rating is absent, the provider's fastest route is selected.

The safety and crime files require unique IDs, valid coordinates, ISO dates, and `synthetic_demo` as the source. Neither the `KA-` regional samples nor the lighting sample locations indicate complete or measured geographic coverage.
