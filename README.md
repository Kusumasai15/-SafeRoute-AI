# SafeWalk

SafeWalk is a Flask web application for planning a journey, comparing route options with clearly labeled synthetic demo metrics, following a route with browser GPS, and finding nearby hospital, police, and pharmacy listings.

**Public site:** [https://safewalk-eosin.vercel.app/](https://safewalk-eosin.vercel.app/)

## Features

- Search for starting points and destinations, or use the device's current location.
- Request walking, cycling, motorcycle, or driving routes from Geoapify. Up to three distinct options are shown; overlapping routes or provider failures can result in fewer.
- Compare route distance, estimated travel time, DEMO safety and crime-risk ratings, and a numeric 0–100 route-specific lighting rating. Nearby synthetic samples use the fitted model; routes without sample coverage get a stable geometry/mode-based synthetic profile for the same model. A deterministic rule-based DEMO fallback is labeled if the model is unavailable. See [synthetic lighting and ML details](docs/LIGHTING.md).
- Show a ★ Demo Recommended route using the documented safety/crime/lighting/time/distance formula. Missing ratings select the provider's fastest route instead; excessive detours are excluded.
- Start GPS navigation with a moving position arrow, accuracy display, map-follow and recenter controls, provider turn instructions, remaining distance and estimated time, off-route feedback, and a manual arrival check-in.
- Find Geoapify listings for hospitals, police stations, and pharmacies within 5 km. Filter categories, view distinct map markers, and inspect straight-line distances. Results are cached briefly by the running server process.
- Save up to five emergency contacts in the browser, choose a primary contact, and use user-initiated call actions.
- Prepare an emergency call link and shareable journey or location summaries. Messages and location snapshots are not sent automatically.
- Submit location-based reports, review reports submitted by the current browser, and delete those reports. An authenticated admin can review or dismiss reports with a recorded reason.

## Safety and data limitations

The bundled `demo_data/safety.csv`, `demo_data/crime.csv`, and `demo_data/lighting.csv` contain fictional synthetic samples. The lighting dataset has five generated sample locations in each of India's 28 states and 8 union territories. It does not provide complete geographic coverage. An uncovered route receives a stable generated synthetic feature profile; this is a simulated estimate, not a nearby observation. The route-specific safety, crime-risk, and lighting ratings are **not verified real-world measurements**. In particular, a crime index out of 100 is an index, **not a crime percentage or a population crime rate**.

Missing safety/crime demo samples remain unavailable and are displayed as “—”. Lighting ratings are always numeric and bounded 0–100, but are simulation-only. The separate synthetic incidents CSV is retained as sample data but is not displayed on route cards or used to select routes.

Lighting labels are generated from synthetic road/time/environment features using a fixed, documented formula with Gaussian noise. `lighting_score` is the target, and `lighting_condition`, IDs, coordinates, city/state, and all label-derived fields are excluded from model inputs. The offline `RandomForestRegressor` is trained, saved in `demo_data/lighting_model.joblib`, and loaded for per-route estimates; Flask never trains inside a request. Held-out metrics are MAE **8.74**, RMSE **10.73**, and R² **0.627** on **SYNTHETIC DEMO DATA only**, not real-world accuracy. Recreate the dataset, metrics, model, and metadata with `python -m scripts.train_lighting_model`.

Nearby facility distances are straight-line distances, not walking or driving distances. Geoapify/OSM-based listings do not establish that a facility is open, staffed, or operational. Check facilities independently.

GPS navigation requires browser location permission, a supported device, and sufficiently accurate location updates. Turn guidance and the moving arrow can be inaccurate when GPS reception is poor. Browser-based simulated GPS tests are not real-device GPS tests. Automatic rerouting is not provided.

## Technology and architecture

- **Backend and ML:** Python, Flask, Flask-SQLAlchemy, Pandas, NumPy, scikit-learn, Joblib, Requests, and Psycopg 3 for PostgreSQL.
- **Map and client:** Leaflet 1.9.4, OpenStreetMap tiles, HTML, CSS, and browser JavaScript without a frontend framework.
- **External services:** Geoapify Geocoding, Routing, and Places APIs. The Geoapify API key is used by Flask and is not sent to browser JavaScript.
- **Storage:** SQLite for local development; PostgreSQL for Vercel deployments. Emergency contacts are stored in browser `localStorage`.

The Flask app factory in `app/__init__.py` configures security and database access. `app/routes.py` implements the HTML pages and HTTP API. `app/services/geoapify.py` calls the map provider and normalizes routes and facility listings; `app/services/demo_service.py` calculates synthetic safety/crime metrics; `app/services/lighting_ml.py` generates the lighting CSV, scores route-local samples, loads a pre-trained artifact, and ranks fully covered routes. The browser renders routes and obtains GPS updates directly through the browser Geolocation API.

## Project structure

```text
.
├── app/
│   ├── __init__.py           # Flask app factory, configuration, security
│   ├── models.py             # Admin, report, and audit database models
│   ├── routes.py             # Pages and JSON API endpoints
│   ├── services/
│   │   ├── demo_service.py   # Synthetic safety/crime route metrics
│   │   ├── lighting_ml.py    # Synthetic lighting, model loading and recommendation
│   │   └── geoapify.py       # Provider requests and normalization
│   ├── static/               # Browser JavaScript and CSS
│   └── templates/            # Traveller and admin HTML templates
├── demo_data/                # Fictional safety, crime, lighting and incident data
├── scripts/                  # Reproducible ML training command
├── docs/                     # Architecture, validation, sources, Vercel notes
├── public/static/            # Static assets copied for Vercel deployment
├── tests/                    # Pytest API/service tests and Node client checks
├── build.py                  # Copies app/static assets into public/static
├── main.py                   # Vercel Flask entry point
├── run.py                    # Local Flask entry point
├── requirements.txt          # Flask and ML runtime dependencies
├── requirements-dev.txt      # Test dependency
└── vercel.json               # Vercel build and function configuration
```

## Local setup on Windows

Use Python 3.11 or newer. From PowerShell, change to the project folder containing `run.py` and run:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Edit `.env` and replace the placeholders:

```dotenv
FLASK_SECRET_KEY=<at-least-32-random-characters>
GEOAPIFY_API_KEY=<your-Geoapify-API-key>
DATABASE_URL=sqlite:///safewalk.db
PORT=5000
COOKIE_SECURE=false
```

Use the generated random value for `FLASK_SECRET_KEY`. Obtain `GEOAPIFY_API_KEY` from Geoapify; routing, geocoding, and facility search require a valid key. Keep `.env` private and do not commit it. Keep `COOKIE_SECURE=false` only for local HTTP development.

Start the local server:

```powershell
.\.venv\Scripts\python.exe run.py
```

Open [http://127.0.0.1:5000/](http://127.0.0.1:5000/). With the default SQLite URL, the app creates its database tables on local startup. The database file is stored under Flask's `instance` directory (normally `instance/safewalk.db`).

To create or reset an administrator account locally:

```powershell
.\.venv\Scripts\python.exe -m flask --app run:app create-admin
```

Follow the prompts. The username must be 1–80 characters and the password at least 12 characters.

## Database configuration

### Local SQLite

The local default is:

```dotenv
DATABASE_URL=sqlite:///safewalk.db
```

The application creates the local `instance` directory and tables automatically when it starts outside Vercel. Do not point this app at a different project's database.

### Neon or another hosted PostgreSQL database

The application includes `psycopg[binary]` and accepts PostgreSQL URLs beginning with `postgres://` or `postgresql://`, normalizing them to the Psycopg SQLAlchemy driver. Configure `DATABASE_URL` with the provider's connection string and required TLS/SSL options, for example:

```dotenv
DATABASE_URL=postgresql://<user>:<password>@<host>/<database>?sslmode=require
```

Never put a real connection string in source control. When `VERCEL=1`, the app requires PostgreSQL and does **not** call `db.create_all()`. This project has no migration scripts or automatic remote schema initialization. Before using a new hosted database, provision the tables defined in `app/models.py` using a reviewed schema/migration process and a database role with suitable permissions. Existing SQLite data is not copied to PostgreSQL.

## Deploy to Vercel

The deployment configuration is [vercel.json](./vercel.json):

- `main.py` exports the Flask application as `app`.
- The configured build command is `python build.py`.
- `build.py` copies `app/static/` into `public/static/`.
- The Python function is configured with a 60-second maximum duration and includes `app/templates/`, `app/static/`, and `demo_data/`.

Deployment steps:

1. Push this project to a Git repository and import it into Vercel. Set the Vercel project root to the directory containing `vercel.json`. Leave Output Directory unset and use the configured build command.
2. Provision a hosted PostgreSQL database, such as Neon. Initialize its schema from the models in `app/models.py` before serving requests; automatic schema creation is disabled when `VERCEL=1`.
3. Add these environment variables to the Vercel project for the environments you deploy:

   | Variable | Value |
   | --- | --- |
   | `FLASK_SECRET_KEY` | A stable random secret of at least 32 characters |
   | `GEOAPIFY_API_KEY` | Your Geoapify key |
   | `DATABASE_URL` | The hosted PostgreSQL URL, including required SSL options |
   | `COOKIE_SECURE` | `true` |

   Vercel sets `VERCEL=1` for its deployment environment. Do not set a SQLite URL for the deployed app. Generate a secret locally with:

   ```powershell
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
   ```

4. Deploy. Verify the deployment at [https://safewalk-eosin.vercel.app/](https://safewalk-eosin.vercel.app/) and check `/health`. Test provider-dependent features with valid Geoapify credentials and verify reports persist across requests.

Vercel function instances are ephemeral. SQLite files are not durable there. The in-memory facility cache and request limiter are per process and are not shared among separate function instances.

## Tests and build

Run these commands from the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check app\static\app.js
node --check tests\client_logic.cjs
node tests\client_logic.cjs
.\.venv\Scripts\python.exe build.py
```

The pytest suite exercises Flask routes, validation, CSRF, reports/admin workflows, route normalization, demo calculations, and mocked Geoapify provider responses, including facility radius filtering, deduplication, and caching. The Node client checks use mocked Leaflet and synthetic GPS positions for route selection, zero and missing score display, maneuver progression, GPS heading/jitter/errors/cleanup, map-follow controls, facility category toggles, and overlay layout contracts. They do not simulate movement in normal app operation and are not real-device GPS tests.

`build.py` should be run before deploying if static assets have changed. Vercel runs it through the configured `buildCommand`.

## Data attribution

- Route, geocoding, and Places data are requested from **Geoapify**. Consult Geoapify's current terms, quotas, and attribution requirements.
- The basemap uses **OpenStreetMap** standard tiles and displays OpenStreetMap attribution. Follow the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/); these public tiles are not an offline or bulk-download service.
- The safety, crime, and incident CSV files under `demo_data/` are synthetic project demo data, not verified external datasets.
- Facility listings may be based on OpenStreetMap data. Their presence does not establish opening hours, staffing, or operational status.
