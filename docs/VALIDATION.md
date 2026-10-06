# Validation

## Checks performed

- Python backend workflow suite: 24 passing cases on disposable in-memory SQLite.
- Admin bootstrap, login/logout, CSRF, review reasons/status restrictions and audit persistence.
- Report submission, owner isolation/deletion, invalid coordinate rejection and escaped admin rendering.
- Mocked autocomplete, nearby-help normalization, distinct route handling, equivalent routes with different vertex density, step coordinates and optional-route failure.
- Missing API-key error and security response headers.
- JavaScript syntax check with `node --check app/static/app.js`.
- Node client-logic checks with `node tests/client_logic.cjs` (no extra Node packages required).
- Python source compilation and local HTTP startup smoke check.
- ZIP integrity and exclusion of secrets/runtime database files.

Provider documentation was consulted for request parameters. No actual Geoapify API key was supplied, so live autocomplete/routing/places calls were not exercised. No real-browser visual test, physical-device GPS test, emergency phone call or message send was performed. Node mocks do not validate Leaflet rendering, browser APIs or CSS layout.

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
