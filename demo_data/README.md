All records in this folder are fictional demo data, not verified safety information.

- `safety.csv`: editable safety scores from 0 to 100; higher means safer in the demo.
- `crime.csv`: editable crime indices in the `crime_rate` column from 0 to 100; higher means more crime in the demo. The API exposes this metric as `demo_crime_index`. These are not measured population or time-based rates.
- `incidents.csv`: fictional sample data retained for the demo; it is not displayed on route cards or used to rank routes.

Routes show the distance-weighted average of safety and crime samples within each record's `radius_meters` of the selected route geometry (250 metres if omitted). Weights are 1 / (1 + distance_to_route / 250 metres)^2. A metric with no nearby samples stays unknown. Identical or overlapping routes can still have identical scores.

Demo safety and crime values are never used to recommend or rank routes. Route selection is based only on estimated travel time, with distance breaking ties. This does not verify real-world safety. Each file requires unique IDs, valid coordinates, ISO dates, and `synthetic_demo` as the source.

The `KA-` records provide a synthetic regional grid from latitude 11.5 to 18.5 and longitude 74.0 to 78.5, spaced 0.1 degrees apart. Their 8 km matching radius covers routes between grid points across Karnataka. This rectangular grid also includes adjacent areas; it is not an administrative boundary dataset. The values are randomly generated demo indices, not actual local crime or safety measurements.
