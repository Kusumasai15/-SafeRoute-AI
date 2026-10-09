# Synthetic lighting demo and ML

## Dataset

`demo_data/lighting.csv` contains 180 fictional observations: five generated
sample roads/locations in one representative city from each of India's 28 states
and 8 union territories. It is a set of sample points, not complete geographic
coverage of India, and does not represent measured lighting conditions.

The CSV includes coordinates, city/state, road type, time period, streetlight
density, ambient-light index, tree-canopy percentage, road width, built density,
a lighting-condition label, and a 0–100 lighting score. Every row is marked
`SYNTHETIC_DEMO`. `python -m scripts.train_lighting_model` regenerates the file
from seed `20261009`.

The synthetic target is generated as:

```text
clip(30 + 2.2*density + 0.25*ambient - 0.18*canopy + 0.35*road_width
     + 0.12*built_density + road adjustment + time adjustment
     + Gaussian noise N(0, 5.5), 0, 100)
```

Road and time adjustments are fixed mappings in `app/services/lighting_ml.py`.
The `lighting_condition` text is derived from the generated target and is
explicitly excluded, along with the score, IDs, coordinates, city, and state,
from the predictive features.

## Model and evaluation

The offline training command uses Pandas, NumPy, scikit-learn's
`RandomForestRegressor`, and Joblib. Road type and time period are one-hot
encoded; streetlight density and synthetic environmental features are numeric
inputs. The records are split into training and test sets with a fixed split
seed. MAE, RMSE, and R² are calculated on the held-out test records and written
to `demo_data/lighting_model_metadata.json`.

Every metric is performance on **SYNTHETIC DEMO DATA**, not real-world accuracy.
Model inputs deliberately exclude the target, label-derived `lighting_condition`,
and all identifiers or location fields. A fitted artifact is stored at
`demo_data/lighting_model.joblib`; Flask only loads this pre-trained artifact and
never trains inside a request. Vercel bundles this directory with the app.

Current repository state: **TRAINED**. The configured local `.venv` command
successfully imported scikit-learn and trained the artifact without changing or
bypassing Windows Application Control. The held-out results are:

| Metric | Value |
|---|---:|
| MAE | 8.7432 |
| RMSE | 10.7297 |
| R² | 0.6265 |

These are performance on **SYNTHETIC DEMO DATA only**, not real-world accuracy.
Reproduce the dataset, metrics, model artifact, and metadata with:

```bash
python -m pip install -r requirements.txt
python -m scripts.train_lighting_model
```

The command prints actual metrics and saves the model and metadata. Train with
the same Python major/minor version selected for the production Flask runtime;
the loader checks the pinned ML dependency versions before trusting the artifact.
If no usable model artifact exists, each covered route uses
an explicitly labeled distance-weighted synthetic-data fallback; uncovered
routes display `—/100`.

## Route ratings and recommendation

Each returned route is matched independently against synthetic point
observations using its Geoapify route geometry. Samples within 1,500 m receive
weight `1 / (1 + distance_m / 250)^2`. A loaded model predicts each matching
sample and those estimates are aggregated with the weights. When no model is
available, the synthetic labels are aggregated the same way and marked as
`DEMO data fallback`. With no nearby samples, no lighting rating is invented.

Safety, crime risk, and lighting are calculated independently per route. The
demo recommendation score is:

```text
35% safety + 25% (100 - crime risk) + 25% lighting
     + 10% relative travel-time score + 5% relative distance score
```

Travel-time and distance components are normalized against the fastest route and
shortest route respectively. Routes taking more than 1.5× the fastest time or
more than 1.5× the shortest distance are excluded to avoid excessive detours.
If any required rating is unavailable, the provider's fastest route is
recommended instead. The label is `★ Demo Recommended` when demo scoring is
used; none of these values are verified real-world safety or lighting ratings.

The app retains Geoapify for route/places requests, Leaflet, and OpenStreetMap
map tiles. It does not make Overpass/OSM street-lighting requests, cache live
lighting evidence, or render real street-lamp overlays.
