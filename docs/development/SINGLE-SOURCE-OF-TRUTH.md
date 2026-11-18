# Development Source of Truth and Worktree Retirement

Date: 2026-11-18

## Canonical source

All future source changes, tests, migrations, documentation, and release preparation must happen in the official project directory:

`C:\Users\QusaiAbdElhalim\OneDrive - iValue\Desktop\الشراكات - الأحساء\Sharakat-Data-Base`

Run builds and test commands from this directory. Isolated runtime containers and disposable databases remain allowed, but their source must come from this directory. Do not create another source project or Git worktree.

## Retired recovery worktree

`C:\Users\QusaiAbdElhalim\.codex\worktrees\opportunity-documents-mvp\Sharakat-Data-Base`

This directory was the source of the accepted development changes consolidated here. It is retired from development use and retained temporarily as recovery evidence. Do not continue development there and do not delete it automatically.

## Consolidated implementation

The official project now includes the Documents MVP and published-document API/UI; migrations 0027 and 0028; the KFU parser correction `2026.11.16-kfu-2`; the document collection engine, Furas adapter, private candidate staging, review APIs, Celery tasks, retry/concurrency safeguards, tests, fixtures, reports, release artifacts, and manifests. Existing official-project audit evidence was preserved; deletion-only worktree differences were not carried over.

Migration 0028 is source-only and remains unapplied in production. This consolidation did not deploy images, run migrations, restart services, synchronize sources, or mutate production/business data.

## Runtime separation

At consolidation time, the local production Compose services used image-baked application code. Their only API/Worker host bind mount was backup storage; no project source directory was mounted. Editing this checkout therefore did not live-reload or alter the running containers. Runtime image contents and IDs were recorded read-only during verification.

## Verification

The consolidation acceptance report is maintained alongside this record under `docs/validation/development/`. It records the official source checks, regression results, runtime image comparison, and production safety outcome for this consolidation.
