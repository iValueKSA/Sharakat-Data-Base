# Source assessment: Furas

**Assessment date:** 11 October 2026 (Asia/Amman)  
**Source:** فرص — البوابة الموحدة للاستثمار  
**Official GIS application:** https://gisapps.balady.gov.sa/opportunities/index.html?lang=ar

## Current findings

- The GIS application uses a public ArcGIS MapServer layer configured through `assets/config.json`; collection uses the underlying JSON REST query through the platform proxy.
- The request filters on 11 Al-Ahsa `CITY_ID` values verified against `CITYNAME` fields in the same layer. It also selects current `Announced` listings with `QualifyingOpportunity=0` and `LASTRFPSELLDATE` on or after the current date.
- Current query result: 132 feature IDs. The adapter fetched these as two feature batches of 100 or fewer after one ID query: 3 successful API requests total. Received, parsed, and unique feature counts are all 132; pagination is complete.
- Furas records use `OPPORTUNITYID` as their stable external ID and reference number. `OBJECTID` is the fallback. Detail URLs use `/ar/opportunity/{reference}?type={OPPORTUNITYTYPE}`.
- Records are tagged `SOURCE_FILTER`; raw city fields, geometry, ID list, and exact `where` clause are retained. Eastern Province text is not used as the geographic classifier.
- Four previously stored records now have source status `Deleted`; they were marked `REMOVED_FROM_SOURCE` after three complete scans. They remain in source/master history. Current stored Furas source records total 136: 132 in the current active result and 4 deleted records.
- A deterministic sample of 20 feature rows is saved at [furas-geographic-sample.csv](../validation/furas-geographic-sample.csv). Direct HTTP requests to the canonical detail pages timed out, so the sample validates fields against the official feature API response and documents that limitation.

## Extraction and data notes

The adapter preserves all ArcGIS attributes and geometry. Booklet price is not mapped as investment value. When `CITYNAME` is blank on an individual feature, the verified `CITY_ID` remains the classification evidence. The full count reconciliation, query, sample caveat, and duplicate review are in [first-live-integration-validation.md](../validation/first-live-integration-validation.md).

Quantitative-field review: `TOTALSPACEINMETERS` is accepted as square metres; `OPPORTUNITYID` is the official opportunity reference; `DURATION` has no documented unit or contract-term semantics in the returned layer and remains raw-only/review-required. Numeric `DURATION` values are not converted to years.
