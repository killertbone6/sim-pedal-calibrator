#!/usr/bin/env bash
# macOS / Linux launcher.  Usage:  ./run.sh  [--port /dev/ttyACM0]
set -e
cd "$(dirname "$0")"

python3 -c "import serial" 2>/dev/null || {
    echo "Installing pyserial (once)..."
    python3 -m pip install --user pyserial
}

exec python3 run_app.py "$@"
