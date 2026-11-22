#!/usr/bin/env bash
# Linux/macOS bootstrap for the native (Docker-free) runtime.
# Ensures Python >= 3.12 and a private virtual environment, then runs
# `python -m sharakat_runtime <args>` from the project root.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ -n "${SHARAKAT_HOME:-}" ]; then HOME_DIR="$SHARAKAT_HOME"
elif [ "$(uname -s)" = "Darwin" ]; then HOME_DIR="$HOME/Library/Application Support/Sharakat"
else HOME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/sharakat"; fi
VENV="$HOME_DIR/venv"
LOG_DIR="$HOME_DIR/logs"
mkdir -p "$HOME_DIR" "$LOG_DIR"

python_ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; }

find_python() {
  for candidate in python3.12 python3.13 python3 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12; do
    if command -v "$candidate" >/dev/null 2>&1 && python_ok "$(command -v "$candidate")"; then
      command -v "$candidate"; return 0
    fi
  done
  return 1
}

install_python() {
  echo "Python 3.12 was not found. Installing it (you may be asked for your password)..."
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  if [ "$(uname -s)" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then brew install python@3.12
    else echo "Install Homebrew (https://brew.sh) or Python 3.12 from python.org, then run this again." >&2; exit 1; fi
  elif command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y python3.12 python3.12-venv || {
      # Older Debian/Ubuntu releases don't ship 3.12; deadsnakes covers Ubuntu.
      if command -v add-apt-repository >/dev/null 2>&1; then
        $SUDO add-apt-repository -y ppa:deadsnakes/ppa && $SUDO apt-get update && $SUDO apt-get install -y python3.12 python3.12-venv
      else echo "Install Python 3.12 for your distribution, then run this again." >&2; exit 1; fi
    }
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y python3.12
  else
    echo "Install Python 3.12 for your distribution, then run this again." >&2; exit 1
  fi
}

PYTHON="$(find_python || true)"
if [ -z "$PYTHON" ]; then install_python; PYTHON="$(find_python || true)"; fi
[ -n "$PYTHON" ] || { echo "Python 3.12 could not be found after installation." >&2; exit 1; }

if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating the private Python environment..."
  "$PYTHON" -m venv "$VENV" || { echo "venv failed: on Debian/Ubuntu install python3.12-venv." >&2; exit 1; }
fi
REQ_HASH="$("$VENV/bin/python" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest().upper())' "$PROJECT_ROOT/requirements.txt")"
STAMP="$VENV/.requirements.sha256"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$REQ_HASH" ]; then
  echo "Installing Python packages (first run only, a few minutes)..."
  "$VENV/bin/python" -m pip install --disable-pip-version-check --upgrade pip >>"$LOG_DIR/pip.log" 2>&1
  "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$PROJECT_ROOT/requirements.txt" >>"$LOG_DIR/pip.log" 2>&1 \
    || { echo "Installing Python packages failed. See $LOG_DIR/pip.log" >&2; exit 1; }
  echo "$REQ_HASH" > "$STAMP"
fi

cd "$PROJECT_ROOT"
exec "$VENV/bin/python" -m sharakat_runtime "$@"
