# SafeWalk Simple architecture

## Goal

One complete traveller flow: choose locations → select a route → navigate → access help/share → check in. Administrative review is a separate interface.

```mermaid
flowchart TD
  Browser[Traveller browser] --> API[Flask APIs]
  Admin[Admin review page] --> API
  API --> Provider[Geoapify adapter]
  API --> Reports[Reports and audit models]
  Provider --> Geoapify[Geoapify services]
  Reports --> DB[SQLite database]
  Browser --> GPS[Device GPS and contacts]
  Browser --> Tiles[OSM map tiles]
```

## Modules

| Path | Responsibility |
|---|---|
| `run.py` | App entry point; local development server |
| `app/__init__.py` | App factory, configuration, CSRF, sessions, headers, rate limiting, admin CLI |
| `app/routes.py` | Thin HTTP handlers for places, routes, nearby help, reports and admin |
| `app/services/geoapify.py` | Bounded external requests, route normalization and geometric duplicate detection |
| `app/models.py` | Admin, Report and Audit persistence |
| `app/templates/` | Traveller and admin screens |
| `app/static/app.js` | Map, location search, GPS guidance, contact storage and explicit sharing |
| `app/static/style.css` | Responsive layout and fullscreen navigation |
| `tests/test_app.py` | Isolated workflow, ownership, validation and provider-normalization tests |

One Flask process is enough for local use. No microservices, sync jobs or safety engine are necessary for this scope. Nearby help uses the existing Geoapify provider rather than a second Overpass adapter, keeping key management and failures simpler. Leaflet/OSM still provide the base map.

## Persistence

| Data | Storage |
|---|---|
| Admin credentials | Database; password hash only |
| Reports | Database with hashed visitor ownership |
| Review actions | Database audit trail |
| Emergency contacts | Browser localStorage |
| Current journey/route candidates | Browser memory only |
| Navigation GPS fixes | Browser memory only |
| API key and Flask secret | Server `.env`/deployment environment |

Synthetic route-card metrics are calculated from the bundled safety and crime CSVs, but are not verified route evidence and never influence route selection. SQLite is deliberate: no real spatial safety analysis is implemented. Do not reuse the old project's database; this schema does not replace its migrations. If verified route analysis is added later, introduce a separate evidence module and PostgreSQL/PostGIS with reviewed migrations at that time.

## APIs

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/search?q=...` | GET | India place suggestions |
| `/api/reverse?lat=...&lng=...` | GET | Current-location label |
| `/api/routes` | POST | Up to three genuine provider candidates; fastest estimated travel time is selected by default, distance breaks ties |
| `/api/help?lat=...&lng=...` | GET | Deduplicated police, hospital and pharmacy listings within a server-enforced 5 km radius; cached for five minutes |
| `/api/reports` | GET/POST | Own reports / submit report |
| `/api/reports/<id>` | DELETE | Delete an owned report |
| `/admin/login` | GET/POST | Admin authentication |
| `/admin/` | GET | Report review and recent audit history |
| `/admin/reports/<id>` | POST | Audited moderation |
| `/admin/logout` | POST | Admin sign out |
| `/health` | GET | Process health, safety_scoring=false |

Browser mutations carry a session CSRF token. Admin HTML forms use a hidden token. Traveller cookies cannot read another traveller's reports. Forms and rendered report text are escaped; dynamic UI uses textContent rather than inserting user-provided HTML.

## Feature decisions

| Decision | Features |
|---|---|
| Keep | Map/search, current location, modes, distance/ETA, route selection, navigation, contacts, reporting |
| Simplify | Two route candidates, one Nearby help control, one admin review panel |
| Add | Share journey/location, arrival check-in, own report status/deletion, clear errors and privacy text |
| Remove from this build | Dataset registry/import, source auditing/sync, OSM replication, PostGIS queries, route history, old overview |
| Defer | Verified evidence comparison, Home/Work saved places, photos, traveller accounts, background alerts and live sharing |
| Synthetic demo data | Route-specific sample safety score and crime index, explicitly labeled synthetic and excluded from route choice |
| Disable/omit | Real safety score, crime-risk ranking, safest-route label, unverified lighting estimates |

This is a smaller release with intentionally different persistence and capabilities from the original README. It does not claim to preserve all previous functionality.
