# Opportunity Documents MVP — Implementation Specification

**Status:** Data-readiness specification only; no code or schema changes.

## First release

An official-source link-out section titled “مستندات الفرصة الاستثمارية”. Display only reviewed records with exact Master and SourceOpportunity provenance, a reviewed official destination, verified link rights, and separately recorded access and participation conditions. Open official sources directly. Never host, proxy, mirror, cache, or copy files.

## Minimum data model

- Source ID/key, SourceOpportunity ID, provider opportunity reference, MasterOpportunity ID.
- Official source opportunity page URL, document URL or attachment ID, original title, document category, source attribution.
- Association classification and evidence; reviewer and decision history.
- Access status: PUBLIC_DIRECT_DOWNLOAD, PUBLIC_OFFICIAL_DOCUMENT_PAGE, LOGIN_REQUIRED, PAYMENT_REQUIRED_FOR_DOCUMENT_ACCESS, RESTRICTED_ACCESS, ACCESS_UNKNOWN, UNAVAILABLE.
- Participation status: PURCHASE_REQUIRED_FOR_PARTICIPATION, PURCHASE_NOT_REQUIRED_CONFIRMED, PARTICIPATION_REQUIREMENT_UNKNOWN.
- Price amount and currency as independent fields; unknown remains null/unknown.
- Rights/link disposition: DIRECT_LINK_SUPPORTED, SOURCE_PAGE_LINK_ONLY, REUSE_OR_LINKING_TERMS_UNCLEAR, RESTRICTED_DO_NOT_EXPOSE.
- Link verification result, observed content type, last verified timestamp, evidence URL, source version/last-seen state, stale/deactivation reason.

## Import and validation

1. Accept only separately approved candidate records; never auto-promote scraped fields.
2. Require exact SourceOpportunity and Master identity; reject absent/conflicting links for the MVP seed.
3. Allowlist registered official HTTPS hosts; reject credentials, unexpected schemes, loopback/private destinations and signed/session URLs.
4. Revalidate redirects against the host allowlist; no general server-side fetch/proxy.
5. Require separate human decisions for document category, exact association, access, participation, rights and price/currency.
6. Deduplicate only on stable provider document identity or canonical URL scoped to one source publication; preserve every occurrence and its audit history.
7. Store source evidence, reviewer, timestamp and version. Never store document bytes.
8. Use bounded public metadata rechecks. Stop on 401/403, payment/login wall, throttling or unexpected redirects; these are not automatically broken-link findings.

## API contract

A reviewed document response should include source ID/key, SourceOpportunity ID, provider opportunity reference, Master ID, source page URL, approved link URL, title, category, attribution, access status, login requirement, document-access payment requirement, participation requirement, amount/currency, rights status, link verification status, last-verified time, display eligibility and display reason. Omit restricted, stale, unreviewed, conflicting or otherwise ineligible URLs from ordinary client responses. Do not return internal review notes or private URLs.

## Arabic UI rendering rules

- Approved verified public document: “تحميل الكراسة”.
- Public booklet where buying is required to bid: “تحميل الكراسة” plus “يلزم شراء الكراسة للتقديم على المنافسة”.
- Restricted or purchase-gated file: “الحصول على الكراسة من المصدر الرسمي”, using only an approved official page destination.
- Verified official purchase action: “شراء الكراسة عبر المصدر الرسمي”.
- No verified document: “لا توجد كراسة متاحة حاليًا”.
- Unknown price/currency: omit the amount; do not imply access is free.
- Other attachments retain their source category and must not be labeled as booklets.

## Refresh, versioning and acceptance

No source synchronization is part of the MVP. Use a separately authorized review cadence, record immutable evidence snapshots/decisions, and mark stale links ineligible after the approved freshness interval. Acceptance requires exact identity, verified destination and rights, independent access/participation/price states, safe URL validation, restricted-link exclusion, audit provenance, duplicate occurrence preservation, Arabic RTL review, link behavior checks, and a demonstrated zero-write seed-generation path.
