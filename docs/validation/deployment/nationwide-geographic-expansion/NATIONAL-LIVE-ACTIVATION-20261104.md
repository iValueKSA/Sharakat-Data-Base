# National Live Activation Decision — 2026-11-04

## Activation result

**Not activated.** National UI/dashboard and national map remain disabled in the live configuration. The auth gate requires a current authorized account and authenticated browser evidence; the available bootstrap test credential is stale. The current administrator's password was not reset or guessed.

## Deployment target and post-deploy state

- Target: `alahsa-local`, `http://localhost:8080`, `ENVIRONMENT=local_user`.
- Rebuilt/recreated only the API and worker services to deploy the accepted geography projection and RCU lifecycle/deadline code. No migration, registry change, source sync, or national flag change occurred.
- `/health/live`: 200 (`ok`). `/health/ready`: 200 (`ready`; database, Redis, worker all `ok`). PostgreSQL and Redis containers are healthy; Celery worker responds `pong`; scheduler and worker containers are running.
- Live geography catalog: reference `READY`; `national_ui_enabled=false`, `national_dashboard_enabled=false`, `national_map_enabled=false`.
- Furas national enumeration and removal flags remain false.

## Isolated pre-activation preview

Process-local flags were enabled only inside a read-only TestClient preview; the live configuration was not changed.

- Al-Ahsa Governorate 501: API 518, dashboard aggregation 518, CSV 518, XLSX 518. The sample API result renders confirmed geography.
- All Saudi and representative region/governorate/source filters, including Eastern Province, Riyadh, Makkah, Al-Madinah, Al-Ahsa, RCJY, RCU, NCP, and Ta'adeen, matched in the earlier isolated acceptance. Ta'adeen remains at 0 current Masters.
- National map recomputation: 5,889 unique Masters with verified direct-source coordinates; 0 outside-boundary markers. No centroids were generated. National map browser interaction and map-to-list drilldown were not tested because authentication acceptance is unavailable.
- See [blocker remediation report](NATIONAL-GO-LIVE-BLOCKER-REMEDIATION-20261104.md) and [Al-Ahsa record reconciliation](ALAHSA-84-GEOGRAPHY-RECONCILIATION-20261104.json) for detailed evidence.

## Browser gate

Authenticated login, dashboard and opportunities access, national controls, exports in the signed-in UI, all five responsive viewports, JavaScript/5xx monitoring under authenticated use, and map drilldown are **NOT VALIDATED**. The previous unauthenticated shell probe's expected `401` responses do not count as authenticated acceptance.

To complete activation review, an authorized administrator must sign in through the normal login form at `http://localhost:8080` with the current account password. Then rerun the authenticated Playwright cases. Do not reset the actual account password as part of this go-live workflow.

## Flag decision

| Feature | Live state | Decision |
|---|---|---|
| `NATIONAL_UI_ENABLED` | `FALSE` | Keep disabled until authenticated browser gates pass |
| `NATIONAL_DASHBOARD_ENABLED` | `FALSE` | Keep disabled with national UI |
| `NATIONAL_MAP_ENABLED` | `FALSE` | Keep disabled until UI activation and authenticated map drilldown/responsive gates pass |
| `FURAS_NATIONAL_ENUMERATION_ENABLED` | `FALSE` | Unchanged |
| `FURAS_REMOVALS_ENABLED` | `FALSE` | Unchanged |

No remaining RCU canonical-integrity defect or Al-Ahsa membership defect blocks the data preview. The only activation blocker is missing authenticated browser validation.
