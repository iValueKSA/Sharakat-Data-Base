# GEOSA Authoritative Administrative Boundaries — Acquisition and CRS Plan

**Prepared:** 2026-11-09  
**Status:** `AUTHORITATIVE_BOUNDARY_REFERENCE = NOT_ACQUIRED`; `CRS_VERIFICATION = PARTIAL`; `BOUNDARY_REPLACEMENT_READINESS = NOT_READY`; `GEOGRAPHIC_CORRECTION_AUTHORIZATION = NOT_AUTHORIZED`; `PRODUCTION_DATA_MUTATIONS = 0`.

## Purpose and scope

This is a read-only acquisition and validation plan. It does not repeat the completed Al-Ahsa record-level audit, submit a GEOSA request, replace geometry, alter map rules, or correct opportunity records. Prior findings are carried forward by reference: 518 current Al-Ahsa Masters; 27 eligible; 421 scope-UNSPECIFIED (119 explicit-location candidates and 302 needing manual review); 55 parent-boundary conflicts; 15 outside saved boundaries; and 5 eligible records with possible Governorate 501 assignment errors. See [previous reconciliation](ALAHSA-GEOGRAPHIC-BOUNDARY-RECONCILIATION-20261109.md).

## Existing reference and CRS verification

The saved `saudi_administrative_units` reference is version `taadeen-public-gis-20261102-v3`, SHA-256 `ec0f22308cc4b6960c5c39aad416f7d7dafa5c13d5b2c7afd56a13f9dc634b8b`. Its 2026-11-02 date is the capture date; no publisher-issued release/effective date was retained. It has 13 regions and 149 governorates, but no country polygon. The governorate layer is Ta’adeen ArcGIS MapServer layer 2, `Governorate_المحافظات_2023`, code field `Governorate_Code`; the region layer is layer 3, `Emirates_الحدود_الإدارية`, code field `Emirate_Code`. The snapshot maps governorates 501 (Al-Ahsa) and 511 (Al Udayd) to region 5 (Eastern).

These are separate source feature classes with differing edit histories. The saved parent relationship was constructed by matching governorate `Emirates_Ar/Emirates_En` labels to region labels; it is not a native, stable parent foreign key. Stable administrative codes exist at each level, but the current cross-layer parent relationship is label-derived. This is consistent with the previously measured parent-containment defect.

A fresh read-only REST metadata check on 2026-11-09 returned HTTP 200 for layers 2 and 3. Both report native `wkid=4204`, `latestWkid=4204`; service version is 11.5. Layer 2 exposes `Governorate_Code`; layer 3 exposes `Emirate_Code`. Both advertise `supportsQueryWithDatumTransformation=true`. No service/layer `datumTransformations` definition or historic release version was returned in the inspected metadata. A machine-readable capture is saved at [Ta’adeen REST CRS metadata evidence](evidence/geosa-boundary-acquisition-20261109/taadeen-rest-crs-metadata-20261109.json).

EPSG:4204 identifies the geographic CRS Ain el Abd / Ain el Abd 1970. The prior snapshot was requested/exported as longitude-latitude EPSG:4326 (`outSR=4326`), and the earlier comparison found matching sample vertices. That confirms the requested output CRS and coordinate order for those samples; it **does not prove the geodetic transformation was correct**. No explicit `datumTransformation` ID/WKT, direction, grid, software version, or operation accuracy was recorded. ArcGIS supports an explicit transformation parameter; the live service advertises that capability, but capability alone does not show which transformation the previous query used. Therefore prior comparisons did not fully verify datum handling. See [Esri query transformation parameter](https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/) and GEOSA’s [geodetic reference guidance](https://geosa.gov.sa/en/mediacenter/Pages/faq.aspx).

GEOSA identifies KSA-GRF17 as the national geodetic frame and provides a reference-frame transformation tool. Its FAQ reports an approximate 93 m offset for ARAMCO-AAA relative to KSA-GRF17. Do not apply that as a blanket correction to this boundary data: GEOSA must identify the exact source realization, transformation operation/direction, area of use, and accuracy for the supplied files. Request original source coordinates unchanged alongside any converted delivery.

## GEOSA availability and reuse status

No suitable, legally reusable vector package containing all 13 region polygons, all governorate polygons, stable codes, and stable parent IDs was verified as anonymously downloadable in the official resources checked:

- GEOSA’s [Open Data catalogue](https://geosa.gov.sa/en/Pages/Open_data.aspx) lists “Geographical Names,” whose description includes regions and governorates. The prior project review of its available workbook found aggregate feature-type rows rather than complete per-governorate polygons or a parent-child boundary register. GEOSA’s catalogue requires use under the dataset’s specific open-data license and retention of its copyright/license notice.
- The GEOSA [National Geospatial Platform](https://geosa.gov.sa/en/Pages/nationalgeospatialplatform.aspx) lists “Administrative regions” as a fundamental layer, but says national data are shared under a defined publication policy protecting rights and security. Public page visibility does not establish download access, dataset version, geometry completeness, or this platform’s reuse rights.
- The 2026 [Official Saudi Map product](https://geoportal.geosa.gov.sa/Geoportal/GeospatialOpenData/OfficialSaudiMap) is an authoritative cartographic reference in KSA-GRF17; the product listing describes GeoPDF/GeoTIFF outputs on request. Those map formats are not by themselves a suitable, topology-preserving governorate polygon dataset.
- The [GEOSA Digital Geospatial Services Portal](https://www.geosa.gov.sa/en/Pages/GEOSAServicesPortal.aspx) provides geospatial product requests. The listed National Platform [Geospatial Data Request service](https://my.gov.sa/en/services/319418) says GEOSA reviews requests and communicates the data electronically. The request was not submitted.

**Availability decision:** `GEOSA_DATA_AVAILABILITY = NOT_PUBLICLY_VERIFIED_AS_A_REUSABLE_VECTOR_BOUNDARY_PACKAGE`. An official administrative-regions layer may be available through the authenticated National Geospatial Platform or by request. Legal and operational reuse terms remain an external dependency. Do not use the Ta’adeen snapshot as production authority until its cross-layer integrity, released version, and reuse rights are resolved.

## Required GEOSA delivery

Request one coherent, same-release package containing:

1. The 13 region polygons and every governorate polygon, including Al-Ahsa (501) and Al Udayd (511); include holes and multipart geometry without generalization or display-only simplification.
2. Stable region and governorate identifiers, Arabic and English official names, and explicit stable `parent_region_id` values. Include a crosswalk for any code/name changes and clarify whether administrative centers are included as separate units.
3. The complete geometry, native spatial reference identifier and WKT, datum/realization and epoch, axis order and units, and any vertical reference if present.
4. The approved transformation from the delivered CRS to KSA-GRF17 and EPSG:4326: transformation name/authority ID or WKT, direction, grid files and checksums, required software/runtime, area of use, stated accuracy, and any fallback restrictions.
5. Dataset title, custodian/provenance, capture and publication dates, effective date, revision identifier, change log, feature counts, and a cryptographic checksum or signed manifest.
6. Geometry QA and hierarchy expectations: polygon validity, ring/part conventions, topology rules, boundary tolerances, permitted overlaps/gaps, and documented exceptions.
7. Written license/authorization covering internal storage and processing, use in an investment-opportunity platform, derived geometry/attributes, browser display, user access, caching, backup, exports, attribution, redistribution (if any), and term/update obligations.
8. GIS-ready digital formats: preferably GeoPackage or File Geodatabase plus GeoJSON for interchange; Shapefile only as a secondary compatibility format. Include UTF-8 Arabic names and a data dictionary. Do not accept only raster/map tiles, screenshots, or a generalized map image as the adjudication geometry.

## Isolated validation procedure for receipt

1. **Quarantine and provenance:** receive to a new isolated evidence directory; do not overwrite the active boundary table/files. Save the original delivery, request/response, license, data dictionary, manifest, file hashes, receipt timestamp, and custodian/release identifiers. Make the original package immutable.
2. **CRS and transformation:** parse each file’s embedded CRS and WKT; compare with the supplied manifest. Preserve native coordinates. Use only GEOSA-specified transformations and required grids. Record library/version, transformation ID/direction, grid hashes, and output CRS. Test published control/check points and round-trip behavior with tolerances supplied by GEOSA; do not choose an undocumented blanket shift. Verify axis order and units explicitly.
3. **Geometry validity:** validate every polygon/multipolygon for finite coordinates, ring closure, self-intersection, shell/hole nesting, empty parts, duplicate vertices, and valid coordinate ranges. Record every defect. Do not silently repair source geometry; if repair is needed, create a separate derived copy and retain the original plus the exact repair method.
4. **Topology and hierarchy:** test all 13 regions for overlap and coverage gaps using GEOSA’s declared topology rules and a suitable equal-area/geodesic method. Verify each governorate lies within exactly its declared parent except for explicit documented coastal/offshore exceptions. Check sibling overlaps/gaps and Al-Ahsa/Al Udayd membership. Apply only GEOSA-approved tolerances; report anomalies before any geometry edit.
5. **Identity compatibility:** match by stable identifiers first, never by name alone. Produce a read-only crosswalk from current IDs/names to GEOSA IDs, parent IDs, and release. Flag code reuse, splits/merges, renames, and unmatched units for human review. Preserve existing source provenance and historical geographic decisions; append a new reference-versioned assessment instead of rewriting old evidence.
6. **Evidence-based impact:** only after validation, re-evaluate the existing 55 conflicts, 5 eligible assignment candidates, 15 outside-boundary records, then the 119 explicit-location scope candidates. Keep the 302 manual-review records unchanged and pending evidence. Compare both old and new decisions per Master ID with geometry version and transformation evidence. Do not auto-change scope, coordinates, identity, production maps, or current records. Do not set a target map count.
7. **Acceptance gate:** require GEOSA reuse authorization, CRS/operation approval, complete topology/parent checks, code crosswalk sign-off, and independent evidence review before a separate production change proposal is even prepared. This plan grants no production authorization.

## Prioritized adjudication plan (future, no changes now)

1. **55 boundary conflicts:** resolve against same-release GEOSA region and governorate geometry first; retain all previous source/master evidence and record the exact reference version and transformation.
2. **5 currently eligible:** check Governorate 501 versus 511 assignment by stable ID and geometry; assess map-filter false-positive status separately from national-map eligibility.
3. **15 outside-boundary:** test membership against the validated national package; preserve outside-Saudi review unless the official reference and source evidence support reclassification.
4. **119 explicit-location candidates:** review the explicit Arabic location signal, source point semantics, governing scope policy, and boundary membership per record. A matching point alone is not approval.
5. **302 manual-review cases:** leave `UNSPECIFIED` until a source owner or authoritative record supports an individual classification.

## Draft formal Arabic data request (not submitted)

**الموضوع: طلب تزويد ببيانات الحدود الإدارية للمملكة العربية السعودية وبيانات نظام الإسناد المكاني**

سعادة/ الهيئة العامة للمساحة والمعلومات الجيومكانية،

السلام عليكم ورحمة الله وبركاته،

نأمل التكرم بإفادتنا وتزويدنا بمرجع جغرافي رسمي ومتكامل للحدود الإدارية للمملكة العربية السعودية، لاستخدامه في التحقق المكاني وعرض الفرص الاستثمارية ضمن منصة رقمية. ونرجو أن يشمل التسليم نسخة واحدة متسقة الإصدار من جميع المناطق الإدارية الثلاث عشرة وجميع حدود المحافظات، بما في ذلك محافظتا الأحساء والعديد، مع المعرّفات الرسمية المستقرة للأقاليم والمحافظات والعلاقة الصريحة بين كل محافظة ومنطقتها الأم.

ولضمان سلامة الاستخدام، نرجو تزويدنا بما يلي:

1. المضلعات الجغرافية الكاملة لكل منطقة ومحافظة، بما يشمل الأجزاء المتعددة والثقوب، وبيان ما إذا كانت المراكز الإدارية وحدات مستقلة.
2. المعرّفات والرموز الرسمية، والأسماء العربية والإنجليزية، ومعرّف المنطقة الأم لكل محافظة، وجدول ربط لأي تغييرات في الرموز أو الأسماء.
3. نظام الإحداثيات المرجعي الأصلي وملف تعريفه (WKT)، والمرجع الجيوديسي وإصداره/حقبته، وترتيب المحاور ووحداتها.
4. طريقة التحويل المعتمدة إلى KSA-GRF17 وإلى EPSG:4326، متضمنة اسم/رمز عملية التحويل واتجاهها، وملفات الشبكة المطلوبة وإصداراتها وبصماتها الرقمية، والدقة المعلنة ومجال صلاحية التحويل وأي قيود على التحويل البديل.
5. تاريخ الإصدار وتاريخ النفاذ وتاريخ المراجعة، ورقم الإصدار وسجل التغييرات، ومصدر البيانات والجهة المسؤولة عنها، وأعداد المعالم وبصمة رقمية أو بياناً موثقاً لمحتويات الحزمة.
6. قواعد سلامة الهندسة والطوبولوجيا وعلاقة الاحتواء بين المحافظة والمنطقة، والتداخلات أو الفجوات المقبولة والاستثناءات والتفاوتات المكانية المعتمدة.
7. شروط الترخيص والاستخدام كتابةً، بما يوضح السماح بالتخزين والمعالجة الداخلية والاستخدام في منصة فرص استثمارية والعرض للمستخدمين والتخزين المؤقت والتصدير والنسخ الاحتياطي والإسناد إلى المصدر والتوزيع، إن وجد، والتزامات التحديث ومدة الإذن.
8. تسليم البيانات بصيغ مكانية قابلة للمعالجة، ويفضل GeoPackage أو File Geodatabase مع GeoJSON للتبادل، وإرفاق قاموس البيانات مع دعم الأسماء العربية بترميز UTF-8. كما نرجو عدم الاكتفاء بصورة خريطة أو بلاطات أو بيانات مبسطة مخصصة للعرض.

كما نرجو إفادتنا بالإجراء الصحيح لتقديم طلب البيانات عبر المنصة الجيومكانية الوطنية أو بوابة الخدمات الجيومكانية، والمتطلبات والرسوم أو التصاريح إن وجدت، وما إذا كانت شروط الاستخدام تسمح بالغرض الموضح أعلاه.

شاكرين لكم تعاونكم، وتفضلوا بقبول فائق الاحترام والتقدير.

**بيانات مقدم الطلب:** [اسم الجهة] — [اسم المفوض] — [البريد الإلكتروني] — [رقم التواصل] — [رابط المنصة أو وصف الاستخدام]

## Final status and next action

- `AUTHORITATIVE_BOUNDARY_REFERENCE = NOT_ACQUIRED` — no verified same-release polygon package and reuse grant is currently in project evidence.
- `CRS_VERIFICATION = PARTIAL` — native EPSG:4204 and `outSR=4326` are verified; the previous datum operation is not recorded or independently verified.
- `GEOSA_DATA_AVAILABILITY = REQUEST_REQUIRED_OR_AUTHENTICATED_ACCESS` — public catalog evidence is insufficient to establish a reusable polygon package.
- `BOUNDARY_REPLACEMENT_READINESS = NOT_READY` — await package, transformation specification, topology/parent rules, and written usage rights.
- `GEOGRAPHIC_CORRECTION_AUTHORIZATION = NOT_AUTHORIZED`.
- `PRODUCTION_DATA_MUTATIONS = 0`.

**Single next action:** submit the attached Arabic request through GEOSA’s official [Geospatial Data Request service](https://my.gov.sa/en/services/319418) or the [Digital Geospatial Services Portal](https://www.geosa.gov.sa/en/Pages/GEOSAServicesPortal.aspx), with an authorized requestor account. No request was sent by this investigation.