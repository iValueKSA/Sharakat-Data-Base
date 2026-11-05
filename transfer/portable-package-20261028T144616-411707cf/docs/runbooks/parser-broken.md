# Parser broken

1. Identify `PARSER_WARNING`, `PARSER_BROKEN`, unexpected zero records, route inventory changes, and the source's last successful count.
2. Pause the affected source from Operations if the data could be misleading. Preserve source observations and the last-good run.
3. Inspect the stored source response/observation metadata and official public page. Do not query authenticated/private routes.
4. Update the adapter and a sanitized fixture. Run the source fixture tests without network access.
5. Trigger one manual sync, inspect parsed/accepted/rejected counts and coverage status, and review unexpected master changes.
6. Resume scheduled operation after validation; retain the alert and remediation notes.
