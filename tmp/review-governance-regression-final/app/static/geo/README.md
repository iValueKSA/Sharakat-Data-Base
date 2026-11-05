# Local map data and attribution

## Al-Ahsa administrative boundary

`alahsa-governorate.geojson` contains the 2021 `Al Ahsa Governorate` ADM2 feature (`shapeID 3984122B69484211656738`) extracted from the geoBoundaries open Saudi Arabia ADM2 GeoJSON release. The release metadata identifies OpenStreetMap as its boundary source and this feature as CC BY-SA 2.0. The local file keeps the original geometry, adds an Arabic display label and provenance properties, and excludes the other Saudi governorates.

Attribution: **geoBoundaries / OpenStreetMap contributors, Al Ahsa Governorate (2021), derived from geoBoundaries gbOpen SAU ADM2, CC BY-SA 2.0.** This is a sourced administrative reference boundary, not an official cadastral or planning boundary. The current GEOSA official map is available through the National Geospatial Platform; the publicly inspected official administrative layer did not state a reuse license, so it is not redistributed here. The available Taadeen government governorate layer was used as a comparison: it independently placed 175 of the 176 current source-coordinate records inside Al-Ahsa; one source record for Salwa is outside and is excluded from the map without changing the opportunity record.

Source metadata: https://www.geoboundaries.org/api/current/gbOpen/SAU/ADM2/  
Source GeoJSON: https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/SAU/ADM2/geoBoundaries-SAU-ADM2.geojson  
License: https://creativecommons.org/licenses/by-sa/2.0/  
GEOSA official map reference: https://www.geosa.gov.sa/en/About/Pages/OfficialSaudiMap.aspx

## Coordinates and precision

Exact points are drawn only from master latitude/longitude values whose matching Furas source row retains the same original ArcGIS point geometry. Each point is checked for valid WGS84 ranges and containment in this local boundary. Coordinates are not geocoded or backfilled. A non-coordinate Furas locality is not moved to a centroid in this version; it remains unmapped until a separately sourced locality reference is established.

The map baselayer uses interactive `https://tile.openstreetmap.org/{z}/{x}/{y}.png` tiles, with visible OpenStreetMap attribution and normal browser caching. This is a runtime internet dependency; tile failure leaves the local boundary, exact points, and heat layer visible on the AHDA canvas with a clear notice. Tiles are requested only for the human-visible viewport; there is no prefetch/offline tile cache.

## Vendored mapping libraries

- Leaflet 1.9.4 — BSD-2-Clause; `vendor/leaflet-1.9.4/LICENSE`.
- Leaflet.markercluster 1.5.3 — MIT; `vendor/leaflet-markercluster-1.5.3/LICENSE`.
- Leaflet.heat 0.2.0 — BSD-2-Clause; `vendor/leaflet-heat-0.2.0/LICENSE`.

The static copies and versioned paths keep Docker builds deterministic and avoid a runtime JavaScript CDN dependency. The map's only runtime external requests are the visible basemap tiles.
