# NHC Parser Warning Remediation — 2026-11-05

## Finding

The latest production observation is job 787, completed 2026-11-05 06:24:45 UTC with warning status. It made 6 route attempts, received 0 records, parsed 0 records, and recorded parser_failures=0; all 6 routes returned HTTP 403 and were categorized ACCESS_RESTRICTED. Last successful content from 2026-10-12 was preserved. This is an access/coverage restriction, not PARSER_DEFECT or SOURCE_FORMAT_CHANGED.

A subsequent isolated unauthenticated GET check on 2026-11-05 returned HTTP 200 for https://www.nhc.sa/en/investment-opportunities/, https://www.nhc.sa/ar/investment-opportunities/, and https://nhc.sa/en/lo/. This shows the restriction is time- or route-dependent; it is not a full six-route parser acceptance, and those GETs did not invoke the parser or change production state. No login, CAPTCHA, or private API was used. NHC public investment pages do not expose a current itemized opportunity inventory; public coverage remains limited.

## Classification

- Latest recorded warning: PUBLIC_COVERAGE_LIMITED + transient ACCESS_RESTRICTED (6/6 routes 403).
- Parser failures at that job: 0.
- Later spot-check: ordinary public GETs succeed for 3 listed surfaces.
- Current root cause of previous “parser warning” wording: warning taxonomy/description was misleading for this observation; stored metrics identify access restriction. No parser repair is supported by the evidence.

The adapter guard correctly keeps the source at warning when the critical Arabic category route is restricted, preserves prior content, and does not treat an empty response as reconciliation-safe. The static limitation text in the adapter describes an older single-supporting-route case; it does not accurately summarize the 6-route job. This was reported as a diagnostics wording limitation and was not changed during this run.

## Recommendation

Retain the warning and public coverage limitation. On a future ordinary scheduled observation, check route-level HTTP status and parser failure counts separately. Accept parser health only when required critical public HTML pages return usable content and targeted fixtures confirm parsing. Do not suppress 403s or access authenticated investor inventory. No manual production sync or source data mutation was performed.
