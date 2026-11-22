# Running the platform on a server (any OS)

The same installer runs the platform on a workstation and on a server, on Windows Server, Linux or macOS. Docker
is not used. On a server, three extra things are configured: the **server mode**, **start at boot**, and the
**firewall**.

## 1. Choose a setup

| Situation | Mode | How users reach it |
|---|---|---|
| Office or intranet server, users on the same network | `internal` | `http://<server-name>:8080` |
| Internet-facing or company production, the platform serves HTTPS itself | `production` with `--tls-cert/--tls-key` | `https://platform.example.org` |
| HTTPS terminated by an existing reverse proxy (IIS, nginx, a load balancer) | `production --behind-proxy` | the proxy's HTTPS address |
| Pre-production copy | `staging`, configured like `production` | its own HTTPS address |
| Linux fleet managed with systemd and a separate database team | none (systemd units) | see [deployment.md](deployment.md) |

`staging` and `production` turn on the application's own hardening:

* Secure, HttpOnly session cookies
* HSTS
* generic error messages
* startup refusal of wildcard CORS, non-HTTPS addresses, missing secrets or wildcard proxy trust

`internal` keeps workstation behaviour but listens on the network.

## 2. Install (same on every OS)

| OS | Command |
|---|---|
| Windows Server | `Install Platform Requirements.bat` (or `scripts\native\bootstrap.ps1 install --no-start`) |
| Linux | `bash sharakat.sh install --no-start` |
| macOS | `bash sharakat.sh install --no-start` |

This installs Python 3.12, PostgreSQL 16 and the Redis-protocol server for the service account, and loads data from
a transfer package if one is present (see [native-runtime.md](native-runtime.md)). Use a dedicated, non-admin
account to run the platform.

The examples below use `sharakat` as shorthand for `scripts\native\bootstrap.ps1` on Windows and
`bash sharakat.sh` on Linux/macOS.

## 3. Configure the server mode

```text
# Intranet (HTTP on the LAN)
sharakat server --mode internal --public-url http://srv-platform:8080

# HTTPS served by the platform (certificate from your CA or Let's Encrypt, PEM files)
sharakat server --mode production --public-url https://platform.example.org --port 443 \
    --tls-cert C:\certs\platform-fullchain.pem --tls-key C:\certs\platform-key.pem

# Behind an existing HTTPS reverse proxy on 10.0.0.5
sharakat server --mode production --public-url https://platform.example.org \
    --behind-proxy --trusted-proxies 10.0.0.5 --bind 0.0.0.0

# Optional: use existing database / cache services instead of the bundled ones
sharakat server --database-url postgresql://app:***@db01:5432/platform --redis-url rediss://:***@cache01:6380/0
```

`server` validates everything before saving. For example, production must use `https://`, the certificate files must
exist, and a proxy must be named exactly. With no options, `server` shows the current configuration. Run
`server --mode off` to go back to workstation mode. Settings are kept in `<home>/config/platform.env`.

Notes:

* **Port 443 or 80 on Linux or macOS** needs the privilege to bind low ports. Use a port ≥1024 behind a proxy, or
  grant it with `sudo setcap 'cap_net_bind_service=+ep' <venv python>` on Linux.
* **External PostgreSQL** must be version 16 or newer. The database must exist and be owned by the application
  user, with `CREATE EXTENSION pg_trgm` already run by a DBA. Restores and backups use the same URL.
* **Certificate renewal:** replace the PEM files, then run `sharakat restart`.

## 4. Open the firewall

`server` prints the exact command for the OS. For example:

* Windows: `netsh advfirewall firewall add rule name="Sharakat Platform" dir=in action=allow protocol=TCP localport=8080`
* Linux: `sudo ufw allow 8080/tcp`, or `sudo firewall-cmd --permanent --add-port=8080/tcp && sudo firewall-cmd --reload`

Only the platform port is opened. PostgreSQL and Redis always stay on `127.0.0.1`.

## 5. Start at boot

```text
sharakat service install --at-boot      # administrator terminal (Windows) or sudo (Linux/macOS)
sharakat restart
```

| OS | What is installed |
|---|---|
| Windows | Task Scheduler task "Sharakat Platform (boot)" that runs at system start-up as the service account, with no time limit and automatic restart. Windows asks for that account's password once; it is passed to Task Scheduler only. |
| Linux | systemd system unit `sharakat-platform.service` (`User=` the service account, `Restart=on-failure`) |
| macOS | LaunchDaemon `/Library/LaunchDaemons/local.sharakat.platform.plist` (`UserName` the service account) |

Run `sharakat service uninstall --at-boot` to remove it.

## 6. Check

```text
sharakat status       # mode, address, components
sharakat verify       # health, worker, migrations, data quality, network exposure
```

On a server, `verify` expects the UI port to be reachable on the network and warns about the firewall if it isn't.
It still requires PostgreSQL and Redis to be reachable only locally.

## Operations

Backups, restores, moving to another server (`export-transfer`), logs and troubleshooting work exactly as described
in [native-runtime.md](native-runtime.md).
