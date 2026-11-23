# Platform data snapshot

`al-ahsa-platform-20261123.dump` is a PostgreSQL backup of the platform's data, taken on 2026-11-23.

SHA-256: `b38722abdd8843266bad5a46dd4defbec2a31fd771e10f0d25bab3ce740c896c`

## Restore it

1. Install the platform as described in the main [README](../README.md). This gives you an empty installation.
2. Restore the backup. The command only works on an empty installation.

   Windows:

   ```powershell
   scripts\native\bootstrap.ps1 restore data-share\al-ahsa-platform-20261123.dump
   ```

   Linux and macOS:

   ```bash
   bash sharakat.sh restore data-share/al-ahsa-platform-20261123.dump
   ```

3. Sign in. User accounts keep their original passwords. To set a new password for the local administrator, run
   `reset-admin-password`.
