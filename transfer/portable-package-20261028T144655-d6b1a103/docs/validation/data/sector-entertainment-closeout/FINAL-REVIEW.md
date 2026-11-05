# Focused review: four entertainment records currently classified as Other

**Review scope:** Masters 22, 29, 68, and 127 only.  
**Live read captured:** 2026-10-21 11:58 UTC.  
**Business-data changes:** none. No sector classification, source payload, inference provenance, or review queue entry was changed.

## Canonical taxonomy

`ENTERTAINMENT_IS_CANONICAL_SECTOR = FALSE`

The runtime canonical sector registry (`app/standardization.py`, `_SECTOR_LABELS`) and the live `/api/filters` sector list contain Environment, Tourism, Agriculture, Healthcare, Education, Logistics, Industrial, Commercial, Real Estate, Energy, Culture, Sports, Financial Services, Technology, Other, and Unspecified. They contain neither `Entertainment` nor `الترفيه`; `canonical_id("sector", "Entertainment")` returns an unmapped identity.

This is case **B**: explicit public amusement attractions are intentionally covered by `Other` under the accepted taxonomy. The current controlled-relaxation policy says that entertainment has no dedicated canonical ID and maps only explicit entertainment attractions to Other; a park or generic leisure location alone is insufficient. These four titles explicitly name children's amusement rides or play activities, so Other is supported by positive purpose evidence rather than used for missing data. Four individual municipal park concessions do not justify adding a new canonical sector or changing the accepted taxonomy.

## Record audit

### Master 22

- **Title:** تاجير مؤقت لموقع من نوع الحدائق بحي  العمران الشمالية لنشاط قطار ترفيهي للأطفال
- **Activity / sub-activity:** Not supplied.
- **Asset type:** الحدائق.
- **Relevant description:** Same as the title; explicitly states a children's entertainment train.
- **Raw source classification:** Furas; source sector, normalized sector, activity, and sub-activity are null; no source taxonomy classification is present. Raw fields say `OPPORTUNITYTYPE=TemporaryRental` and `LOCATIONTYPE=الحدائق`, which describe the lease and venue rather than the sector.
- **Current inferred sector:** `أخرى` (`sector:other`), `MEDIUM_CONFIDENCE`, confidence 0.852.
- **Current inference rule:** `MED_TITLE_CHILD_ENTERTAINMENT_TRAIN`.
- **Evidence:** Title phrase `قطار ترفيهي للأطفال`; no negative or competing sector evidence.
- **Decision:** Correctly Other under the accepted taxonomy.

### Master 29

- **Title:** تاجير مؤقت لموقع من نوع الحدائق بحي  منتزه جبل الشعبة منتزه جبل الشعبة - قطار أطفال و اسكوتر - موقف رقم 51
- **Activity / sub-activity:** Not supplied.
- **Asset type:** الحدائق.
- **Relevant description:** Same as the title; explicitly lists a children's train and scooter concession.
- **Raw source classification:** Furas; source sector, normalized sector, activity, and sub-activity are null; no source taxonomy classification is present. Raw fields say `OPPORTUNITYTYPE=TemporaryRental` and `LOCATIONTYPE=الحدائق`, which describe the lease and venue rather than the sector.
- **Current inferred sector:** `أخرى` (`sector:other`), `MEDIUM_CONFIDENCE`, confidence 0.852.
- **Current inference rule:** `MED_TITLE_CHILD_TRAIN`.
- **Evidence:** Title phrase `قطار أطفال`; description adds the associated scooter activity; no competing sector evidence.
- **Decision:** Correctly Other under the accepted taxonomy.

### Master 68

- **Title:** تاجير مؤقت لموقع من نوع الحدائق بحي  منتزه جبل الشعبة قطار أطفال واسكوترات - موقف 72
- **Activity / sub-activity:** Not supplied.
- **Asset type:** الحدائق.
- **Relevant description:** Same as the title; explicitly lists children's trains and scooters.
- **Raw source classification:** Furas; source sector, normalized sector, activity, and sub-activity are null; no source taxonomy classification is present. Raw fields say `OPPORTUNITYTYPE=TemporaryRental` and `LOCATIONTYPE=الحدائق`, which describe the lease and venue rather than the sector.
- **Current inferred sector:** `أخرى` (`sector:other`), `MEDIUM_CONFIDENCE`, confidence 0.852.
- **Current inference rule:** `MED_TITLE_CHILD_TRAIN`.
- **Evidence:** Title phrase `قطار أطفال`; scooters are additional explicit amusement context; no competing sector evidence.
- **Decision:** Correctly Other under the accepted taxonomy.

### Master 127

- **Title:** تاجير مؤقت لموقع من نوع الحدائق بحي  بلدة الطرف ركن ترفيهي يشمل العاب اطفال كهربائية و هوائية)
- **Activity / sub-activity:** Not supplied.
- **Asset type:** الحدائق.
- **Relevant description:** Same as the title; explicitly names an entertainment corner with electric and inflatable children's games.
- **Raw source classification:** Furas; source sector, normalized sector, activity, and sub-activity are null; no source taxonomy classification is present. Raw fields say `OPPORTUNITYTYPE=TemporaryRental` and `LOCATIONTYPE=الحدائق`, which describe the lease and venue rather than the sector.
- **Current inferred sector:** `أخرى` (`sector:other`), `MEDIUM_CONFIDENCE`, confidence 0.852.
- **Current inference rule:** `MED_TITLE_FAMILY_ENTERTAINMENT_CORNER` (also matched by the normalized Arabic variant).
- **Evidence:** Title phrases `ركن ترفيهي` and `العاب اطفال كهربائية و هوائية`; no competing sector evidence.
- **Decision:** Correctly Other under the accepted taxonomy.

## Final assertions

```text
ENTERTAINMENT_IS_CANONICAL_SECTOR = FALSE
OTHER_ENTERTAINMENT_RECORDS_REVIEWED = 4
OTHER_ENTERTAINMENT_CORRECTLY_OTHER = 4
OTHER_ENTERTAINMENT_SHOULD_BE_ENTERTAINMENT = 0
OTHER_ENTERTAINMENT_REVIEW_REQUIRED = 0
OTHER_USED_AS_MISSING_VALUE = 0
CLASSIFICATION_CHANGES = 0
PREEXISTING_UNRELATED_SECTOR_VALUES_CHANGED = 0
RAW_PROVENANCE_PRESERVED = TRUE
INFERENCE_PROVENANCE_PRESERVED = TRUE
MANUAL_SOURCE_SYNC_STARTED = FALSE
```

The read-only live dashboard and sector filter currently report 13 Other opportunities, with 13 returned by the canonical `sector:other` filter. The existing post-apply DQ result has zero failing gates; `P2_OTHER_USED_AS_MISSING_SECTOR` is PASS with observed value 0. Dashboard/export reconciliation was not rerun because this audit made no classification changes.

**CONTROLLED_MEDIUM_CONFIDENCE_SECTOR_CLASSIFICATION_FINAL_CLOSEOUT = COMPLETE**
