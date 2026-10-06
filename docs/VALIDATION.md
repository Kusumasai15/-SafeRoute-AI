# Validation

## Checks performed

- Python backend suite: 48 passing tests, including disposable in-memory SQLite workflows and mocked route/Places providers.
- Admin bootstrap, login/logout, CSRF, review reasons/status restrictions and audit persistence.
- Report submission, owner isolation/deletion, invalid coordinate rejection and escaped admin rendering.
- Mocked autocomplete and route/Places providers; facility category normalization, five-kilometre filtering, duplicate removal, empty/missing-name handling and caching; travel-time-only route choice; route normalization and optional-route failure.
- Missing API-key error and security response headers.
- JavaScript syntax check with `node --check app/static/app.js`.
- Node client-logic checks with `node tests/client_logic.cjs` exercise mocked Leaflet and synthetic GPS positions for route selection, zero/missing metrics, maneuver progression, stationary jitter, arrow heading, map follow, off-route/accuracy/permission errors, GPS cleanup, facility toggles/throttling and fullscreen/mobile overlay structure. Simulated coordinates are not real-device GPS testing.
- Python source syntax checks, local HTTP startup and desktop/mobile overlay-geometry inspection.
- `python build.py` asset generation and app/deployment asset parity verification.

Provider documentation was consulted for request parameters. No actual Geoapify API key was supplied, so live autocomplete/routing/places calls were not exercised. No physical-device GPS test, emergency phone call or message send was performed. Mocked Leaflet/GPS checks do not confirm real browser permission behavior or facility coverage.

## Manual checks after you add your key

1. Start the app and confirm that the map loads on desktop and mobile.
2. Search for a real starting point and destination; explicitly select each suggestion.
3. Find routes. Check distance/time and select another candidate if returned. One candidate is valid when routes overlap.
4. Change the travel mode or edit an address. Confirm that the old route cannot still be navigated.
5. Allow current-location permission. Verify that the position shown matches your actual location.
6. Start navigation during a safe walking test. Check fullscreen turns, distance/time, GPS accuracy and End cleanup. GPS must also work over HTTPS on a phone.
7. View Nearby help and confirm source/operational-status limitations are visible. Check local facilities independently.
8. Add/edit/delete a contact and make one primary. Check call links without making an unnecessary emergency call.
9. Share a journey/location and confirm that the share sheet or copyable message is correct. It must not send silently.
10. Confirm arrival and check its message. This is a manual check-in.
11. Submit a test report, inspect My reports, and sign in as admin to mark it reviewed with a reason. Confirm it never becomes verified or changes routing.
12. Open another browser/profile and confirm that it cannot see or delete the first browser's reports. Delete test reports when finished.
13. Disable location permission/network temporarily and check readable errors/retry behavior.

Retest actual provider responses and mobile navigation before describing this as a deployed or production-ready safety service.
