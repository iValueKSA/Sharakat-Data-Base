"""Optional start-at-login integration (per user; no administrator rights).

Windows: a Task Scheduler "at logon" task.   Linux: a systemd --user unit.
macOS: a launchd LaunchAgent.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .home import IS_MACOS, IS_WINDOWS, PROJECT_ROOT, layout
from .services import PYTHON

TASK_NAME = "Sharakat Platform"
SYSTEMD_UNIT = "sharakat.service"
LAUNCHD_LABEL = "local.sharakat.platform"


def _say(message: str) -> None:
    print(message, flush=True)


def install() -> int:
    home = layout()
    if IS_WINDOWS:
        script = home.root / "autostart.cmd"
        script.write_text(f'@echo off\r\ncd /d "{PROJECT_ROOT}"\r\n"{PYTHON}" -m sharakat_runtime start --no-browser\r\n',
                          encoding="utf-8")
        result = subprocess.run(["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "ONLOGON", "/RL", "LIMITED",
                                 "/TR", f'"{script}"', "/F"], capture_output=True, text=True)
        _say(result.stdout or result.stderr)
        return result.returncode
    if IS_MACOS:
        agents = Path.home() / "Library" / "LaunchAgents"
        agents.mkdir(parents=True, exist_ok=True)
        plist = agents / f"{LAUNCHD_LABEL}.plist"
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LAUNCHD_LABEL}</string>
  <key>ProgramArguments</key><array><string>{PYTHON}</string><string>-m</string><string>sharakat_runtime</string><string>supervise</string></array>
  <key>WorkingDirectory</key><string>{PROJECT_ROOT}</string>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{home.logs_dir / 'supervisor.out.log'}</string>
  <key>StandardErrorPath</key><string>{home.logs_dir / 'supervisor.out.log'}</string>
</dict></plist>
""", encoding="utf-8")
        uid = str(os.getuid())
        result = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], capture_output=True, text=True)
        if result.returncode != 0:
            result = subprocess.run(["launchctl", "load", "-w", str(plist)], capture_output=True, text=True)
        _say(f"Installed {plist}" if result.returncode == 0 else result.stderr)
        return result.returncode
    unit_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / SYSTEMD_UNIT).write_text(f"""[Unit]
Description=Al-Ahsa investment platform (native runtime)
After=network-online.target

[Service]
Type=simple
WorkingDirectory={PROJECT_ROOT}
ExecStart={PYTHON} -m sharakat_runtime supervise
ExecStop={PYTHON} -m sharakat_runtime stop
TimeoutStopSec=300
Restart=on-failure

[Install]
WantedBy=default.target
""", encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    result = subprocess.run(["systemctl", "--user", "enable", "--now", SYSTEMD_UNIT], capture_output=True, text=True)
    _say(result.stdout or result.stderr or f"Enabled {SYSTEMD_UNIT}. "
         "To start at boot without logging in, run: loginctl enable-linger $USER")
    return result.returncode


def uninstall() -> int:
    if IS_WINDOWS:
        result = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True)
        _say(result.stdout or result.stderr)
        return result.returncode
    if IS_MACOS:
        plist = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist)], capture_output=True)
        plist.unlink(missing_ok=True)
        _say(f"Removed {plist}")
        return 0
    subprocess.run(["systemctl", "--user", "disable", "--now", SYSTEMD_UNIT], check=False)
    unit = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user" / SYSTEMD_UNIT
    unit.unlink(missing_ok=True)
    _say(f"Removed {unit}")
    return 0


# ---------------------------------------------------------------- at boot (servers)
BOOT_TASK_NAME = "Sharakat Platform (boot)"
BOOT_SYSTEMD_UNIT = "sharakat-platform.service"
BOOT_LAUNCHD_PLIST = Path("/Library/LaunchDaemons") / f"{LAUNCHD_LABEL}.plist"


def _run(args: list[str], **kwargs) -> int:
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    output = (result.stdout or "") + (result.stderr or "")
    if output.strip():
        _say(output.strip())
    return result.returncode


def _windows_is_admin() -> bool:
    import ctypes
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def install_at_boot() -> int:
    """Run the platform from machine start-up as the current account, without
    anyone signing in. Needs administrator (Windows) or sudo (Linux/macOS)."""
    import getpass
    home = layout()
    account = getpass.getuser()
    if IS_WINDOWS:
        if not _windows_is_admin():
            _say("Run this from a terminal opened with 'Run as administrator'.")
            return 1
        wrapper = home.root / "boot.cmd"
        wrapper.write_text(f'@echo off\r\ncd /d "{PROJECT_ROOT}"\r\nset "SHARAKAT_HOME={home.root}"\r\n'
                           f'"{PYTHON}" -m sharakat_runtime supervise\r\n', encoding="utf-8")
        domain = os.environ.get("USERDOMAIN", "")
        user = f"{domain}\{account}" if domain else account
        _say(f"The task runs as {user}. Windows needs that account's password to start it before sign-in;")
        _say("it is handed to Task Scheduler only and never stored by the platform.")
        password = getpass.getpass(f"Password for {user}: ")
        script = (
            "$ErrorActionPreference='Stop';"
            "$a=New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/d /c \"' + $env:SH_WRAPPER + '\"') -WorkingDirectory $env:SH_ROOT;"
            "$t=New-ScheduledTaskTrigger -AtStartup;"
            "$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 "
            "-RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries;"
            "Register-ScheduledTask -TaskName $env:SH_TASK -Action $a -Trigger $t -Settings $s "
            "-User $env:SH_USER -Password $env:SH_PASS -RunLevel Limited -Force | Out-Null;"
            "Write-Output ('Registered task ' + $env:SH_TASK)")
        env = dict(os.environ, SH_WRAPPER=str(wrapper), SH_ROOT=str(PROJECT_ROOT), SH_TASK=BOOT_TASK_NAME,
                   SH_USER=user, SH_PASS=password)
        code = _run(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script], env=env)
        if code == 0:
            _say("The platform now starts with Windows. Remove the at-login task if you had one: service uninstall")
        return code
    if IS_MACOS:
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LAUNCHD_LABEL}</string>
  <key>UserName</key><string>{account}</string>
  <key>ProgramArguments</key><array><string>{PYTHON}</string><string>-m</string><string>sharakat_runtime</string><string>supervise</string></array>
  <key>WorkingDirectory</key><string>{PROJECT_ROOT}</string>
  <key>EnvironmentVariables</key><dict><key>SHARAKAT_HOME</key><string>{home.root}</string><key>HOME</key><string>{Path.home()}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>{home.logs_dir / 'supervisor.out.log'}</string>
  <key>StandardErrorPath</key><string>{home.logs_dir / 'supervisor.out.log'}</string>
</dict></plist>
"""
        staged = home.run_dir / "launchd-daemon.plist"
        staged.write_text(plist, encoding="utf-8")
        _say("sudo may ask for your password.")
        for step in (["sudo", "cp", str(staged), str(BOOT_LAUNCHD_PLIST)],
                     ["sudo", "chown", "root:wheel", str(BOOT_LAUNCHD_PLIST)],
                     ["sudo", "chmod", "644", str(BOOT_LAUNCHD_PLIST)]):
            if subprocess.run(step).returncode != 0:
                return 1
        if subprocess.run(["sudo", "launchctl", "bootstrap", "system", str(BOOT_LAUNCHD_PLIST)]).returncode != 0:
            return subprocess.run(["sudo", "launchctl", "load", "-w", str(BOOT_LAUNCHD_PLIST)]).returncode
        _say(f"Installed {BOOT_LAUNCHD_PLIST}; the platform starts when the Mac boots.")
        return 0
    unit = f"""[Unit]
Description=Al-Ahsa investment platform (native runtime, server mode)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={account}
WorkingDirectory={PROJECT_ROOT}
Environment=SHARAKAT_HOME={home.root}
ExecStart={PYTHON} -m sharakat_runtime supervise
ExecStop={PYTHON} -m sharakat_runtime stop
TimeoutStopSec=300
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    staged = home.run_dir / BOOT_SYSTEMD_UNIT
    staged.write_text(unit, encoding="utf-8")
    _say("sudo may ask for your password.")
    for step in (["sudo", "install", "-m", "0644", str(staged), f"/etc/systemd/system/{BOOT_SYSTEMD_UNIT}"],
                 ["sudo", "systemctl", "daemon-reload"],
                 ["sudo", "systemctl", "enable", "--now", BOOT_SYSTEMD_UNIT]):
        if subprocess.run(step).returncode != 0:
            return 1
    _say(f"Enabled {BOOT_SYSTEMD_UNIT}; the platform starts when the server boots.")
    return 0


def uninstall_at_boot() -> int:
    if IS_WINDOWS:
        if not _windows_is_admin():
            _say("Run this from a terminal opened with 'Run as administrator'.")
            return 1
        return _run(["schtasks", "/Delete", "/TN", BOOT_TASK_NAME, "/F"])
    if IS_MACOS:
        subprocess.run(["sudo", "launchctl", "bootout", "system", str(BOOT_LAUNCHD_PLIST)])
        return subprocess.run(["sudo", "rm", "-f", str(BOOT_LAUNCHD_PLIST)]).returncode
    subprocess.run(["sudo", "systemctl", "disable", "--now", BOOT_SYSTEMD_UNIT])
    code = subprocess.run(["sudo", "rm", "-f", f"/etc/systemd/system/{BOOT_SYSTEMD_UNIT}"]).returncode
    subprocess.run(["sudo", "systemctl", "daemon-reload"])
    return code
