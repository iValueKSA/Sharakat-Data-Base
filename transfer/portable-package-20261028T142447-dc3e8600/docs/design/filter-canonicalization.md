# Filter value canonicalization

## Scope

All active business filters share the rules in `app/filter_canonicalization.py`. The six filter values are read from non-merged Master records: activity/sector (`Opportunity.sector`), opportunity type, owner, source, location (`district` falling back to `city`), and status. Source values use the configured `Source.source_key`; the translated source label is presentation metadata, not a second filter value.

The Activity filter and the Dashboard Sector filter are two labels for the same Master field. The city field is also audited because it is exported and contributes to location filtering. Publication platform (`primary_publication_platform`) is an exported Master field, not a separate filter. Investment model, project stage, location scope, and source taxonomy occur in source evidence and detail summaries but are not current filter controls. Review queue states and conflict states are workflow decisions, not business filter dimensions; this change does not normalize or update them.

## Comparison and display rules

`comparison_key(value)` applies Unicode NFKC, removes zero-width/format controls, tatweel and Arabic diacritics, maps Alef variants (`أ`, `إ`, `آ`, `ٱ`) to `ا`, collapses Unicode whitespace, trims, and case-folds. It preserves `ة/ه` and `ى/ي`. The key is never displayed.

`canonical_value(dimension, value)` is dimension-specific. It returns a user-facing business label. It does not mutate the stored Master or SourceOpportunity values during reads, and it never changes `raw_data_json`, source observations, provenance, or review decisions. Decorative surrounding quotes are stripped for category dimensions only.

- **Activity / sector:** verified code labels already used by the UI taxonomy map to their existing Arabic labels (`Industrial` → `صناعي`, `Commercial` → `تجاري`, `Environment` → `البيئة`, `INVESTMENT_OPPORTUNITY` → `فرصة استثمارية`, and the other explicit labels in the registry). `Other`, `Others`, `أخري`, `غير ذلك`, Alef variants, and quoted `أخرى` map to `أخرى` in this dimension only.
- **Opportunity type:** `Other`, `Others`, `أخري`, `غير ذلك`, Alef variants, and quoted `أخرى` map to `أخرى`. Other type names remain distinct without a verified taxonomy mapping.
- **Owner:** `أمانة الأحساء`, `أمانة الاحساء`, and `أمانة محافظة الأحساء` share the official display label `أمانة الأحساء`. This uses the existing `OrganizationAlias` registry, which assigns `أمانة محافظة الأحساء` (source `furas`) and `Al Ahsa Municipality` the organization ID `al-ahsa-municipality`. `محافظة الأحساء` and `هيئة تطوير الأحساء` remain distinct. The owner value `the Ministry of Municipalities` on NCP source record `ncp:foodsafetylabs` maps to `وزارة البلديات والإسكان`: the linked [official NCP article](https://ncp.gov.sa/en/MediaCenter/News/Pages/FoodSafetyLabs.aspx) spells out “the Ministry of Municipalities and Housing (MOMAH)”. The ingestion alias lookup uses the conservative comparison key, preserving `ة/ه` and `ى/ي`.
- **Location / city:** `الأحساء`, `الاحساء`, `Al Ahsa`, `Al-Ahsa`, and `Alhasa` map to governorate label `الأحساء`. Locality labels such as `الهفوف`, `العقير`, and `العيون` remain distinct.
- **Status:** `UNKNOWN`, `غير معروف`, `غير محدد`, and `غير متوفر` map to `غير محددة`. `Announced` and `متاحة` remain separate lifecycle/business states. Expired and removed-from-source states remain distinct.
- **Source:** stable configured source keys remain the option values; each key appears once. Arabic/English source labels do not create additional source options.
- **Publication platform:** no verified alias is present in the current Master inventory; the six configured Arabic labels are kept as recorded.

Null and blank values are not turned into dropdown options. They remain missing in storage and are excluded from filter choices; analytics render a single `غير محدد` bucket where appropriate. `أخرى` is never treated as missing.

## Query, dashboard, export, and ingestion behavior

Filter selection resolves to all currently stored Master values with the same dimension-specific canonical label, then uses those raw values in SQL. Counts are summed across those aliases in `/api/filters`. Dashboard category bars group and add counts after canonicalization; clicking a canonical bar sends that canonical label through the same filter resolver. Opportunity JSON and the business-facing Master fields in CSV/XLSX use canonical display labels. CSV/XLSX accept the same sector, status, source, owner, location, and type filters as the opportunities API.

New sync records are canonicalized only in the Master projection after source normalization. The adapter payload and `SourceOpportunity.source_owner`, source status, location, raw JSON and observations retain their source values. No one-time database rewrite is performed. Existing stored values remain available to alias-aware queries and audit reports, and newly observed aliases use the same registry on future syncs.

No taxonomy conflicts, duplicate reviews, location reviews, field conflicts, or other review decisions are resolved by filter canonicalization.

## Audit disposition

Before/after counts and every observed raw label are recorded in `docs/validation/data/filter-canonicalization-validation.md` and `docs/validation/data/filter-value-duplicate-groups.csv`. The municipality alias is verified by the existing organization registry; no unresolved owner alias group remains in the observed filter inventory.


