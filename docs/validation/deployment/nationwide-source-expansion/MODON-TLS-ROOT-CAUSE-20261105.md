# MODON TLS Root Cause — 2026-11-05

## Finding

MODON_TLS_ROOT_CAUSE = MISSING_INTERMEDIATE_CA (high confidence, reproduced with strict verification).

The API container strict Python TLS request to https://modon.gov.sa/en/InvestmentOpportunities fails with CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate. A strict openssl s_client -verify_return_error -showcerts inspection receives only the leaf certificate. The leaf identifies CN=*.modon.gov.sa, SAN covers *.modon.gov.sa and modon.gov.sa, issuer is DigiCert Global G2 TLS RSA SHA256 2020 CA1, and observed validity is 2026-07-14 through 2027-01-28. No intermediate is sent in the server presented chain. A Windows curl using Schannel completed TLS verification to the same hostname and received HTTP 404 for HEAD on the configured path. That establishes that a separate trust implementation has the chain available; it does not make the container chain valid.

The endpoint 404 on HEAD is not used as evidence of opportunity-page availability because the adapter uses GET. No TLS verification was disabled, and no certificate was accepted or added locally.

## Remediation and source status

Do not work around the invalid server chain with verify=false or a broad trust change. The required provider-side action is to configure MODON TLS endpoint/load balancer to serve the leaf plus DigiCert Global G2 TLS RSA SHA256 2020 CA1 intermediate chain. Then retry normal strict verification from the application container and verify hostname, dates, and trust path.

MODON_SOURCE_HEALTH = BLOCKED pending provider chain repair and strict GET success. Existing source records and links were left untouched; no production sync was run.
