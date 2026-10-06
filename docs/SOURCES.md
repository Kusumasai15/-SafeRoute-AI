# Implementation references

Provider documentation checked 6 October 2026:

- Geoapify Routing: https://apidocs.geoapify.com/docs/routing/
  - `walk`, `bicycle`, `motorcycle`, `drive` modes.
  - `balanced` and `short` optimization requests.
  - MultiLineString leg geometry with step `from_index` positions.
- Geoapify Autocomplete: https://apidocs.geoapify.com/docs/geocoding/address-autocomplete/
- Geoapify Reverse Geocoding: https://apidocs.geoapify.com/docs/geocoding/reverse-geocoding/
- Geoapify Places/categories: https://apidocs.geoapify.com/docs/places/
  - `service.police`, `healthcare.hospital`; circle/proximity filters.
- Leaflet documentation: https://leafletjs.com/reference.html
- OpenStreetMap attribution: https://www.openstreetmap.org/copyright
- OSM standard tile policy: https://operations.osmfoundation.org/policies/tiles/
  - Standard public tiles are for modest interactive use; assess the policy and a dedicated tile provider before large-scale deployment. No offline prefetch included.
- India Emergency Response Support System: https://112.gov.in/
  - 112 is India's unified emergency number. The UI exposes a user-initiated telephone link; it does not integrate with dispatch systems.

No live routes, incident datasets, operational facility verification or production safety evidence were obtained to build this ZIP.
