"""Launching the app when the user logs in.

Windows only for now: one value under the per-user Run key, which needs no
administrator rights and is trivially reversible. Everything is wrapped
because a locked-down machine can refuse registry writes, and failing to set
a convenience toggle must never take the app down with it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Lord3DPedalCalibrator"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def supported() -> bool:
    return os.name == "nt"


def launch_command() -> str:
    """What Windows should run at login."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'          # the packaged .exe
    # Running from source: prefer pythonw so no console window flashes up.
    interpreter = Path(sys.executable)
    windowed = interpreter.with_name("pythonw.exe")
    if windowed.exists():
        interpreter = windowed
    return f'"{interpreter}" -m pedalcal'


def is_enabled() -> bool:
    if not supported():
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except Exception:  # noqa: BLE001 - missing value is the normal case
        return False


def set_enabled(enabled: bool) -> bool:
    """Returns True if the registry now matches what was asked for."""
    if not supported():
        return False
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                                  launch_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:  # noqa: BLE001
        return False
