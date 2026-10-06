# SafeWalk Simple

A fresh, simplified Flask journey companion. This ZIP is a new application, not a patch or database migration for your previous SafeWalk project.

## Included features

- Leaflet/OpenStreetMap map with responsive desktop/mobile layout.
- India-filtered place autocomplete and current-location selection.
- Walk, Cycle, Motorcycle and Car routing through Geoapify.
- Up to **three** distinct route candidates: balanced, short, and an alternative avoiding a point midway along the balanced route. Fewer are shown if routes overlap or optional requests fail. Route numbers are not safety rankings.
- A demo recommendation compares fictional safety/crime indices (80% combined), travel time (10%), and distance (10%). When any route lacks demo metrics, shortest travel time is recommended instead; distance breaks ties. The recommended route is selected by default.
- Route-specific distance, estimated travel time and provider turn instructions.
- Fullscreen map with GPS guidance, approximate remaining distance/time and off-route notices.
- Nearby police/hospital listings within 5 km, using Geoapify Places (OSM-based).
- Up to five browser-stored emergency contacts, primary-contact selection, edit/delete and explicit call actions.
- Explicit 112 call link, current-location snapshot sharing, journey summary sharing and manual arrival check-in.
- Reports with coordinates and a browser-owned status list; owner deletion.
- Separate authenticated admin report-review page with required reasons and an audit trail.
- Input validation, CSRF checks, hashed admin passwords and bounded process-level rate limits.

There is **no safety score, crime-risk estimate, safest-route label, verified lighting layer or automatic emergency dispatch**. Reports stay unverified even after review. Facility presence does not establish route safety.

## Start on Windows (PowerShell)

Extract the ZIP into a new folder. Keep your old project as a backup. Open PowerShell in the extracted `safewalk-simple` folder (the one containing `run.py`).

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Open `.env` in VS Code or Notepad:

1. Replace `FLASK_SECRET_KEY` with the random string printed by the last command.
2. Replace `GEOAPIFY_API_KEY` with your Geoapify key.
3. Leave `DATABASE_URL=sqlite:///safewalk.db` for local use.
4. Keep `COOKIE_SECURE=false` for localhost.

Then start:

```powershell
.\.venv\Scripts\python.exe run.py
```

Open **http://127.0.0.1:5000**. No PowerShell activation-policy change is necessary because these commands use the virtual environment's Python directly.

## Start on Linux/macOS

Use Python 3.11 or newer (recommended 3.12).

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -c "import secrets; print(secrets.token_hex(32))"
# Edit .env as described above.
.venv/bin/python run.py
```

SQLite is created in `instance/safewalk.db` automatically. No PostGIS setup is needed for this simplified version. Do not point it at your old database. `create_all()` is for this fresh schema only; future schema changes need reviewed migrations.

## Set up the administrator

Windows:

```powershell
.\.venv\Scripts\python.exe -m flask --app run:app create-admin
```

Linux/macOS:

```bash
.venv/bin/python -m flask --app run:app create-admin
```

Enter a username and a password of at least 12 characters when prompted. Visit **http://127.0.0.1:5000/admin/login**. There is no default admin password. Running the command again for the same username resets its password.

## Your API settings

The API key is read only by Flask; it is not embedded in HTML or JavaScript. The server needs access to `api.geoapify.com`. Enable/check autocomplete, reverse geocoding, routing and places services for your account. If you restrict a key, account for server-side requests; browser-referrer-only restrictions may reject them.

One route search makes three provider requests when balanced succeeds: balanced, short, and a balanced alternative avoiding the first route's midpoint. Autocomplete is debounced; nearby help makes additional Places requests. Provider quotas/credits apply. No automatic retries or background sync workers are included.

The browser loads Leaflet from unpkg, OSM raster tiles and optional Google Fonts (system-font fallback). An internet connection is required. This is not an offline navigation app.

## Navigation and sharing boundaries

GPS requires browser permission and HTTPS or localhost. Opening a phone at a laptop's plain HTTP LAN address may block GPS; use HTTPS when testing on another device. `127.0.0.1` on a phone refers to the phone, not your laptop.

Navigation uses projection onto the selected route for approximate progress. Next-turn distances are straight-line estimates; remaining distance follows route geometry. ETA scales the original provider duration by remaining distance; it is not live traffic or a reliable countdown. GPS loops/parallel roads can make progress inaccurate. Guidance runs only while the page is active; no screen-lock/background guarantee, voice navigation, automatic rerouting or native-app functionality is claimed.

Fullscreen uses an in-page expanded map, keeping turns, distance/time and emergency actions visible. The browser may retain its own address bar. Location sharing requests a fresh GPS fix and includes a timestamp/accuracy. It shares a snapshot, **not live tracking**. Sharing uses the device share sheet when supported and otherwise a copyable message. Arrival is user-confirmed, not automatically detected or sent.

## Reports and privacy

Reports are non-emergency submissions. They are not displayed as public incident markers or used to calculate risk. Admin states are `pending`, `reviewed`, and `dismissed`; there is no `verified` state. Do not submit personal details. Photos are intentionally omitted from the first version.

There are no traveller accounts. A signed HttpOnly browser cookie owns the report list; the database stores a hash of its visitor token. Reports cannot be accessed from another browser. Clearing cookies or changing the Flask secret removes access to that list. Delete reports before clearing cookies if removal is desired. Contacts are stored in localStorage on that device; use Privacy → Delete all saved contacts to remove them. Shared-device users may see contacts.

Routes and GPS history are not stored in the database. Autocomplete queries/endpoints and requested help coordinates are sent to Geoapify. GPS watch updates stay in the browser. Report coordinates/text are saved on the server. Admin review history persists after report deletion and contains the report ID, reviewer, states and reason, not the report's coordinates/text; admins should avoid copying personal details into reasons. Review reasons/history are private to admins.

## Test

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

On Linux/macOS use `.venv/bin/python` instead. Tests use disposable in-memory SQLite and mocked Geoapify data. They do not use your database, spend API credits or establish real safety evidence. See `docs/VALIDATION.md` for checks performed on this package and a manual browser checklist.

## Deployment later

For Vercel, follow [the deployment steps](docs/VERCEL.md). The project includes
a Flask entry point, static asset build, and hosted PostgreSQL support.

This is a runnable local project, not an already hosted service. The development server binds to localhost. For a simple deployment install the included Waitress dependency and use:

```bash
waitress-serve --listen=127.0.0.1:8000 run:app
```

Put it behind a properly configured HTTPS reverse proxy, set `COOKIE_SECURE=true`, use a persistent volume for `instance/`, and keep `.env`/database files private. Do not expose Flask's development server. Configure infrastructure-level rate limits, request logging without sensitive query contents and appropriate backups. The built-in limiter is per process/IP and bounded to 4096 keys; it is not a distributed abuse-control system. Proxy IP handling must be configured only for a trusted proxy. Large public deployments need shared rate limiting, durable hosted storage and reviewed database migrations.

## Documentation

- `docs/ARCHITECTURE.md`: modules, data flow and feature decisions.
- `docs/VALIDATION.md`: automated checks and manual verification.
- `docs/SOURCES.md`: provider documentation and emergency-number source.
- `.env.example`: settings to replace; no real credentials are included.

## Troubleshooting

| Issue | What to do |
|---|---|
| Secret-key error at startup | Generate a random secret of at least 32 characters; replace the example in `.env`. |
| No autocomplete | Check key/account restrictions and internet; read the message under the field. Choose a suggestion, rather than just typing. |
| No route | Check locations/mode. Some mapped areas do not have a routable connection. |
| One route only | Both optimization requests may return the same road geometry. This is expected. |
| GPS unavailable | Allow browser location permission; use HTTPS or localhost. |
| Nearby help empty | Local mapping may be incomplete; this does not establish that help is absent. |
| Form token error | Reload the page and retry. Signing in/out rotates the form token. |
| Port 5000 in use | Set `PORT=5001` in `.env`, restart and open the matching address. |
| Cannot sign in | Run `create-admin` again to reset the account password. |

Keep secrets out of source control and do not upload `.env`, `instance/` or browser contact data.
