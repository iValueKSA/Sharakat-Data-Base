"""End-to-end smoke test of the native runtime on this machine.

    python scripts/native/smoke_test.py            # uses a throwaway SHARAKAT_HOME
    python scripts/native/smoke_test.py --keep     # leave the throwaway home for inspection

install --fresh -> start -> health/ready -> UI -> login -> XLSX export -> worker ping
-> stop -> start (data survives restart) -> stop. Exits non-zero on the first failure.
It never touches the real installation: it always runs with its own SHARAKAT_HOME
and its own ports.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*args: str, env: dict) -> None:
    print(f"$ sharakat {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, "-m", "sharakat_runtime", *args], cwd=ROOT, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--home")
    args = parser.parse_args()
    home = Path(args.home or tempfile.mkdtemp(prefix="sharakat-smoke-"))
    env = {**os.environ, "SHARAKAT_HOME": str(home),
           # Never touch the real installation's credentials file.
           "SHARAKAT_CREDENTIALS_FILE": str(home / "Local Admin Credentials.txt")}
    # Private ports so a real installation on this machine is never disturbed.
    (home / "config").mkdir(parents=True, exist_ok=True)
    env_file = home / "config" / "platform.env"
    if not env_file.exists():
        env_file.write_text("UI_PORT=18080\nPOSTGRES_PORT=55329\nREDIS_PORT=63791\n", encoding="utf-8")
    sys.path.insert(0, str(ROOT))
    from sharakat_runtime.config import parse_env_file
    try:
        run("install", "--fresh", "--no-start", env=env)
        run("start", "--no-browser", env=env)
        values = parse_env_file(env_file)
        base = f"http://127.0.0.1:{values['UI_PORT']}"
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

        def get(path: str):
            with opener.open(base + path, timeout=60) as response:
                return response.status, response.read()

        status, body = get("/health/ready")
        assert status == 200 and json.loads(body)["status"] == "ready", body
        status, body = get("/")
        assert status == 200 and b"<html" in body.lower(), "UI not served"
        status, _ = get("/static/app.js")
        assert status == 200
        login = urllib.request.Request(base + "/api/auth/login", method="POST",
                                       data=json.dumps({"email": values["BOOTSTRAP_ADMIN_EMAIL"],
                                                        "password": values["BOOTSTRAP_ADMIN_PASSWORD"]}).encode(),
                                       headers={"Content-Type": "application/json"})
        with opener.open(login, timeout=60) as response:
            assert response.status == 200, "admin login failed"
        status, body = get("/api/auth/me")
        assert status == 200 and json.loads(body)["user"].get("role") == "admin", body
        status, body = get("/api/export.xlsx")
        assert status == 200 and body[:2] == b"PK", "XLSX export failed"   # xlsx is a zip
        # Worker ping, migrations at head, loopback-only checks. An empty database has
        # no data-quality baseline, so those gates are skipped here.
        run("verify", "--skip-data-quality", env=env)
        run("stop", env=env)
        run("start", "--no-browser", env=env)
        status, body = get("/health/ready")
        assert status == 200, "not ready after restart"
        run("stop", env=env)
        print("SMOKE TEST PASSED", flush=True)
        return 0
    except Exception:
        subprocess.run([sys.executable, "-m", "sharakat_runtime", "stop"], cwd=ROOT, env=env)
        for name in ("supervisor", "api", "worker", "redis", "postgres", "migrations"):
            log = home / "logs" / f"{name}.log"
            if log.is_file():
                print(f"----- {log} (tail)")
                print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]))
        raise
    finally:
        if not args.keep and not args.home:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
